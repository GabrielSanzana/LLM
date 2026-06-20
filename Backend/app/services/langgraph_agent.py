import os
import sys
import re
import json
import logging
from typing import Any, Dict, List, Optional, Literal, TypedDict
from datetime import datetime
from pathlib import Path

# Add backend directory to sys.path to allow standalone execution
file_path = Path(__file__).resolve()
backend_dir = file_path.parents[2]
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

# pyrefly: ignore [missing-import]
from groq import Groq
# pyrefly: ignore [missing-import]
from langgraph.graph import StateGraph, END

# Import existing services
from app.services.rag_service import RAGService
from app.services.google_calendar_service import GoogleCalendarService, parse_fecha_hora

# Initialize logger
logger = logging.getLogger(__name__)

# Initialize clients and services
client = Groq(api_key=os.getenv("GROQ_API_KEY"))
rag_service = RAGService()
calendar_service = GoogleCalendarService()

# Helper to clean thinking tags
def clean_think_tags(text: str) -> str:
    if not text:
        return ""
    return re.sub(r'(?i)<think>.*?</think>', '', text, flags=re.DOTALL).strip()

def call_groq_with_retry(**kwargs) -> Any:
    import time
    max_retries = 4
    for attempt in range(max_retries):
        try:
            return client.chat.completions.create(**kwargs)
        except Exception as e:
            err_msg = str(e)
            if "429" in err_msg or "rate_limit" in err_msg.lower() or "rate limit" in err_msg.lower():
                wait_time = (attempt + 1) * 2
                print(f"[Groq Retry] Rate Limit (429) detectado. Reintentando en {wait_time}s... (Intento {attempt+1}/{max_retries})")
                time.sleep(wait_time)
                continue
            else:
                raise e
    return client.chat.completions.create(**kwargs)

# ==========================================
# 1. ESTADO GLOBAL (AgentState)
# ==========================================
class AgentState(TypedDict):
    user_query: str
    history: List[Dict[str, str]]
    intent: str  # "INFO_QUERY", "CREATE_REMINDER", "OUT_OF_SCOPE"
    requires_rag: bool
    rag_context: str
    reminder_details: Dict[str, Any]  # {"tramite": ..., "fecha_hora": ..., "email": ..., "documentos": ...}
    validation_status: str  # "valid", "missing_info", "invalid_format"
    validation_errors: List[str]
    retry_count: int
    feedback_message: Optional[str]
    final_response: str
    system_time: str
    trace: List[Dict[str, Any]]

def generar_mqr(user_query: str) -> List[str]:
    prompt = f"""
    Consulta original:
    {user_query}

    Genera EXACTAMENTE 3 consultas de búsqueda para un sistema RAG.

    La primera consulta debe ser:
    - Una versión formal e institucional.

    La segunda consulta debe ser:
    - Una versión enfocada en requisitos, documentos o antecedentes necesarios.

    La tercera consulta debe ser:
    - Una versión semántica o técnica utilizando términos relacionados.

    Reglas obligatorias:
    - Una consulta por línea.
    - No expliques nada.
    - No justifiques las consultas.
    - No uses numeración.
    - No uses viñetas.
    - No uses etiquetas como <think>.
    - Devuelve únicamente las 3 consultas.
    """
    try:
        model = os.environ["GROQ_MODEL"]
        resp = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3
        )
        texto = resp.choices[0].message.content.strip()

        if "</think>" in texto:
            texto = texto.split("</think>", 1)[1]

        variantes = [
            linea.strip()
            for linea in texto.splitlines()
            if linea.strip()
        ]

        variantes = variantes[:3]

        return variantes + [user_query]
    except Exception as e:
        print(f"Error en generación MQR: {e}")
        return [user_query]

# ==========================================
# 2. DEFINICIÓN DE NODOS
# ==========================================

# NODE 0: Get System DateTime (Deterministic / System Tool Node)
def get_system_datetime(state: AgentState) -> Dict[str, Any]:
    dias_semana = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]
    ahora = datetime.now()
    nombre_dia = dias_semana[ahora.weekday()]
    current_time_str = f"{nombre_dia}, {ahora.strftime('%Y-%m-%d %H:%M:%S')}"
    
    new_trace = state.get("trace", []).copy()
    new_trace.append({
        "type": "system_tool_call",
        "tool": "get_system_datetime",
        "result": f"Fecha y hora del servidor obtenida: {current_time_str}"
    })
    
    return {
        "system_time": current_time_str,
        "trace": new_trace
    }

# NODE 1: Classify Intent (LLM-based)
def classify_intent(state: AgentState) -> Dict[str, Any]:
    model = os.environ["GROQ_MODEL"]
    user_query = state.get("user_query", "")
    history = state.get("history", [])
    system_time = state.get("system_time", "")

    history_context = ""
    if history:
        history_context = "Historial conversacional reciente:\n"
        for msg in history[-5:]:
            role = "Usuario" if msg.get("role") == "user" else "Asistente"
            history_context += f"- {role}: {msg.get('content')}\n"

    system_prompt = f"""Eres el Clasificador de Intenciones y Necesidades de ChileAtiende. Tu tarea es analizar la consulta del usuario y el historial reciente para clasificar la intención actual y decidir si es obligatorio realizar una consulta a la base de conocimientos RAG.

[SISTEMA]: La fecha y hora actual del servidor es: {system_time}.

Opciones de "intent":
1. "INFO_QUERY": El usuario realiza una pregunta informativa (requisitos, costos, plazos o detalles de trámites oficiales de ChileAtiende / Registro Civil).
2. "CREATE_REMINDER": El usuario solicita agendar, anotar, recordar, programar o crear una cita en su calendario para realizar un trámite.
3. "OUT_OF_SCOPE": El usuario realiza consultas no institucionales, de entretenimiento, comerciales, pop, videojuegos, música o materias totalmente ajenas al servicio público del Estado de Chile.

Opciones de "requires_rag" (booleano):
- Debe ser true si la intención es "INFO_QUERY".
- Debe ser true si la intención es "CREATE_REMINDER" y en el historial conversacional NO se han detallado anteriormente los requisitos o documentos del trámite a recordar (o sea, es la primera vez que se habla del trámite en la sesión).
- Debe ser false si la intención es "OUT_OF_SCOPE".
- Debe ser false si la intención es "CREATE_REMINDER" y en el historial de conversación (mensajes anteriores del asistente) ya se listaron los requisitos, costos y documentos del trámite (por lo que no es necesario volver a consultar el RAG).

REGLAS DE SALIDA:
Debes responder ÚNICAMENTE con un objeto JSON válido que contenga las claves "intent" y "requires_rag". No escribas explicaciones antes ni después del JSON.

Ejemplos de salida:
{{"intent": "INFO_QUERY", "requires_rag": true}}
{{"intent": "CREATE_REMINDER", "requires_rag": true}}
{{"intent": "OUT_OF_SCOPE", "requires_rag": false}}
{{"intent": "CREATE_REMINDER", "requires_rag": false}}"""

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": f"{history_context}Consulta del usuario: {user_query}"}
    ]

    try:
        response = call_groq_with_retry(
            model=model,
            messages=messages,
            temperature=0.1,
            response_format={"type": "json_object"}
        )
        content = response.choices[0].message.content.strip()
        data = json.loads(content)
        intent = data.get("intent", "INFO_QUERY")
        requires_rag = data.get("requires_rag", True)
    except Exception as e:
        logger.error(f"Error clasificando intención: {e}")
        intent = "INFO_QUERY"  # Fallback seguro
        requires_rag = True

    # Generar plan virtual para que la consola muestre el roadmap
    plan = [{"step_id": 1, "description": "Clasificar intención del usuario", "tool_expected": "none"}]
    if intent == "OUT_OF_SCOPE":
        plan.append({"step_id": 2, "description": "Sintetizar respuesta fuera de foco", "tool_expected": "none"})
    elif intent == "INFO_QUERY":
        plan.append({"step_id": 2, "description": "Buscar en RAG requisitos oficiales", "tool_expected": "search_chileatiende_knowledge"})
        plan.append({"step_id": 3, "description": "Sintetizar respuesta final", "tool_expected": "none"})
    else:  # CREATE_REMINDER
        if requires_rag:
            plan.append({"step_id": 2, "description": "Buscar en RAG requisitos oficiales", "tool_expected": "search_chileatiende_knowledge"})
        else:
            plan.append({"step_id": 2, "description": "Ignorar RAG (información en historial)", "tool_expected": "none"})
        plan.append({"step_id": 3, "description": "Extraer detalles del recordatorio", "tool_expected": "none"})
        plan.append({"step_id": 4, "description": "Validar datos del recordatorio", "tool_expected": "none"})
        plan.append({"step_id": 5, "description": "Crear evento en Google Calendar", "tool_expected": "crear_recordatorio"})
        plan.append({"step_id": 6, "description": "Sintetizar respuesta final", "tool_expected": "none"})

    new_trace = state.get("trace", []).copy()
    new_trace.append({
        "type": "plan_generated",
        "plan": plan
    })
    new_trace.append({
        "type": "executing_step",
        "step_id": 1,
        "description": f"Clasificar intención (Resultado: {intent})",
        "tool_expected": "none"
    })
    new_trace.append({
        "type": "step_completed_text",
        "step_id": 1,
        "content": f"Intención clasificada como {intent}. Requiere RAG: {requires_rag}."
    })
    if intent == "CREATE_REMINDER" and not requires_rag:
        new_trace.append({
            "type": "executing_step",
            "step_id": 2,
            "description": "Ignorar RAG (información ya se encuentra en el historial)",
            "tool_expected": "none"
        })
        new_trace.append({
            "type": "step_completed_text",
            "step_id": 2,
            "content": "Se omitió el RAG de forma exitosa ya que la conversación contiene los requisitos."
        })

    return {
        "intent": intent,
        "requires_rag": requires_rag,
        "trace": new_trace
    }

# NODE 2: Retrieve RAG (Deterministic)
def retrieve_rag(state: AgentState) -> Dict[str, Any]:
    user_query = state.get("user_query", "")
    
    logger.info(f"Generando MQR para: {user_query}")
    queries = generar_mqr(user_query)
    logger.info(f"Queries MQR: {queries}")

    # Ejecutar búsqueda semántica para cada variante
    contexts = []

    for query in queries:
        contexto_parcial = rag_service.get_knowledge(query, k=3)

        if contexto_parcial:
            contexts.append(contexto_parcial.strip())

    rag_context = "\n\n".join(contexts)
    
    new_trace = state.get("trace", []).copy()
    new_trace.append({
        "type": "executing_step",
        "step_id": 2,
        "description": "Buscar en RAG requisitos oficiales del trámite",
        "tool_expected": "search_chileatiende_knowledge"
    })
    new_trace.append({
        "type": "mqr_generated",
        "queries": queries
    })
    new_trace.append({
        "type": "tool_call",
        "step_id": 2,
        "function": "search_chileatiende_knowledge",
        "arguments": {
            "original_query": user_query,
            "mqr_queries": queries
        }
    })
    new_trace.append({
        "type": "tool_message",
        "step_id": 2,
        "result": (
            f"MQR generó {len(queries)} consultas. "
            f"Se recuperaron {len(rag_context)} caracteres del RAG."
        )
    })
    return {
        "rag_context": rag_context,
        "trace": new_trace
    }


# NODE 3: Extract Reminder Details (LLM-based)
def extract_reminder_details(state: AgentState) -> Dict[str, Any]:
    model = os.environ["GROQ_MODEL"]
    user_query = state.get("user_query", "")
    history = state.get("history", [])
    rag_context = state.get("rag_context", "")
    feedback_message = state.get("feedback_message", "")
    current_details = state.get("reminder_details", {}) or {}

    # Formatear fecha y hora actual del sistema (desde el estado, con fallback)
    current_time_str = state.get("system_time", "")
    if not current_time_str:
        dias_semana = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]
        ahora = datetime.now()
        nombre_dia = dias_semana[ahora.weekday()]
        current_time_str = f"{nombre_dia}, {ahora.strftime('%Y-%m-%d %H:%M:%S')}"

    history_context = ""
    if history:
        for msg in history[-6:]:
            role = "Usuario" if msg.get("role") == "user" else "Asistente"
            history_context += f"- {role}: {msg.get('content')}\n"

    system_prompt = f"""Eres el Extractor de Detalles de Citas de ChileAtiende. Tu labor es analizar la conversación y los requisitos oficiales de los trámites para extraer los parámetros necesarios para agendar un recordatorio en Google Calendar.

Los campos a extraer son:
1. "tramite": Nombre del trámite del Estado de Chile (ej: 'Renovación de cédula de identidad').
2. "fecha_hora": Fecha y hora en formato ISO 8601 (YYYY-MM-DDTHH:MM:SS). Si el usuario no especificó la hora exacta, asume por defecto las 09:00:00. Usa la fecha actual del sistema para evaluar términos relativos como "mañana", "lunes", "este viernes", etc.
3. "email": Correo electrónico del usuario al cual enviar la invitación.
4. "documentos": Lista sintética de los requisitos oficiales y documentos necesarios para el trámite, extraídos de la información del RAG o del historial de la conversación (si ya se habían listado anteriormente).

=== CONTEXTO DEL SISTEMA ===
- Fecha y hora actual del servidor: {current_time_str}
- Requisitos oficiales del RAG (si están disponibles): {rag_context}
- Historial de la conversación (busca aquí los documentos y el trámite si el RAG anterior está vacío):
{history_context}

=== VALORES EXTRAÍDOS ANTERIORMENTE ===
{json.dumps(current_details, indent=2)}

=== CORRECCIONES / ERROR REPORTADO (SI HAY) ===
{feedback_message if feedback_message else "Ninguno. Extrae normalmente."}

INSTRUCCIONES DE SALIDA:
Responde EXCLUSIVAMENTE con un JSON que tenga las siguientes claves:
- "tramite": string o null (si no se especifica)
- "fecha_hora": string o null (si no se puede inferir una fecha)
- "email": string o null (si no se proporciona)
- "documentos": string o null (si no se encuentran en el RAG ni en el historial)

No agregues ninguna explicación adicional.
"""

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": f"{history_context}Mensaje actual del usuario: {user_query}"}
    ]

    try:
        response = call_groq_with_retry(
            model=model,
            messages=messages,
            temperature=0.1,
            response_format={"type": "json_object"}
        )
        content = response.choices[0].message.content.strip()
        extracted = json.loads(content)
        
        # Combinar con los detalles que ya teníamos si los nuevos vienen nulos
        merged_details = current_details.copy()
        for k in ["tramite", "fecha_hora", "email", "documentos"]:
            if extracted.get(k):
                merged_details[k] = extracted[k]
                
    except Exception as e:
        logger.error(f"Error extrayendo detalles: {e}")
        merged_details = current_details

    new_trace = state.get("trace", []).copy()
    new_trace.append({
        "type": "executing_step",
        "step_id": 3,
        "description": "Extraer detalles de agendamiento (trámite, email, fecha)",
        "tool_expected": "none"
    })
    new_trace.append({
        "type": "step_completed_text",
        "step_id": 3,
        "content": f"Detalles extraídos: {json.dumps(merged_details)}"
    })

    return {
        "reminder_details": merged_details,
        "feedback_message": None,  # Limpiar feedback tras procesar
        "trace": new_trace
    }


# NODE 4: Validate Details (Deterministic)
def validate_details(state: AgentState) -> Dict[str, Any]:
    details = state.get("reminder_details", {}) or {}
    retry_count = state.get("retry_count", 0)
    
    email = details.get("email")
    fecha_hora = details.get("fecha_hora")
    tramite = details.get("tramite")
    
    validation_errors = []
    validation_status = "valid"
    feedback_message = None

    # 1. Comprobar si faltan datos esenciales (Missing info)
    missing = []
    if not tramite:
        missing.append("tramite")
    if not fecha_hora:
        missing.append("fecha_hora")
    if not email:
        missing.append("email")
        
    if missing:
        validation_status = "missing_info"
        validation_errors = missing
    else:
        # 2. Comprobar formatos (Invalid format)
        # Validar email
        email_regex = r"^[\w\.-]+@[\w\.-]+\.\w+$"
        if not re.match(email_regex, str(email)):
            validation_errors.append("email_format")
            feedback_message = "El formato del correo electrónico es inválido. Debe tener una estructura válida como usuario@dominio.com."
            
        # Validar fecha_hora (Intentar parsear)
        try:
            # Si el parsing por defecto cae a mañana porque falla el formato, lo consideramos error de formato
            dt = parse_fecha_hora(fecha_hora)
            # Adicionalmente verifiquemos si tiene un formato de fecha ISO básico
            if not re.match(r"^\d{4}-\d{2}-\d{2}", str(fecha_hora)):
                validation_errors.append("fecha_hora_format")
                feedback_message = (feedback_message or "") + " La fecha/hora proporcionada no se pudo interpretar correctamente. Escríbela en un formato claro o indícale al usuario que la ingrese de nuevo."
        except Exception:
            validation_errors.append("fecha_hora_format")
            feedback_message = (feedback_message or "") + " Error parseando la fecha."

        if validation_errors:
            validation_status = "invalid_format"
            retry_count += 1

    new_trace = state.get("trace", []).copy()
    new_trace.append({
        "type": "executing_step",
        "step_id": 4,
        "description": f"Validar datos del recordatorio (Estado: {validation_status})",
        "tool_expected": "none"
    })
    new_trace.append({
        "type": "step_completed_text",
        "step_id": 4,
        "content": f"Resultado de validación: {validation_status}. Errores: {validation_errors}. Reintento: {retry_count}"
    })

    return {
        "validation_status": validation_status,
        "validation_errors": validation_errors,
        "retry_count": retry_count,
        "feedback_message": feedback_message,
        "trace": new_trace
    }


# NODE 5: Create Calendar Event (Deterministic/Tool)
def create_calendar_event(state: AgentState) -> Dict[str, Any]:
    details = state.get("reminder_details", {}) or {}
    
    tramite = details.get("tramite", "Trámite ChileAtiende")
    fecha_hora = details.get("fecha_hora", "")
    email = details.get("email", "")
    documentos = details.get("documentos", "Llevar su Cédula de Identidad.")
    
    logger.info(f"Insertando evento para: {email} | Trámite: {tramite}")
    res = calendar_service.create_reminder_event(
        tramite=tramite,
        fecha_hora_str=fecha_hora,
        email=email,
        documentos=documentos
    )
    
    new_trace = state.get("trace", []).copy()
    new_trace.append({
        "type": "executing_step",
        "step_id": 5,
        "description": "Crear recordatorio oficial en Google Calendar",
        "tool_expected": "crear_recordatorio"
    })
    new_trace.append({
        "type": "tool_call",
        "step_id": 5,
        "function": "crear_recordatorio",
        "arguments": {
            "tramite": tramite,
            "fecha_hora": fecha_hora,
            "email": email,
            "documentos": documentos
        }
    })
    new_trace.append({
        "type": "tool_message",
        "step_id": 5,
        "result": res.get("message", "Error al procesar recordatorio.")
    })

    return {
        "final_response": res.get("message", "Error al procesar el recordatorio en Google Calendar."),
        "trace": new_trace
    }


# NODE 6: Synthesize Response (LLM-based)
def synthesize_response(state: AgentState) -> Dict[str, Any]:
    model = os.environ["GROQ_MODEL"]
    user_query = state.get("user_query", "")
    history = state.get("history", [])
    intent = state.get("intent", "INFO_QUERY")
    rag_context = state.get("rag_context", "")
    validation_status = state.get("validation_status", "valid")
    validation_errors = state.get("validation_errors", [])
    calendar_response = state.get("final_response", "")

    # Redactar prompt del sintetizador según el escenario
    system_prompt = """Eres el asistente virtual experto oficial de ChileAtiende. Tu propósito es guiar de forma clara, empática y resolutiva a los ciudadanos sobre trámites, subsidios, beneficios y servicios del Estado de Chile.

=== REGLAS DE ENTREGA (ESTRICTAS) ===
- Redacta tu respuesta final de forma directa, natural y ciudadana, orientada al usuario en español de Chile.
- Está estrictamente prohibido incluir en tu mensaje final tus pasos de pensamiento interno (como etiquetas <think>), análisis lógicos o marcas de procesamiento técnico.
- Si el usuario pregunta por temas fuera de foco (comerciales, videojuegos, cultura pop, marcas corporativas privadas, etc.), debes indicar educadamente y de forma muy cortante que tu rol se limita estrictamente a la orientación institucional del Estado de Chile, sin dar ejemplos ni definir dichos términos ajenos.
"""

    if intent == "OUT_OF_SCOPE":
        prompt = f"""El usuario realizó una consulta fuera de ámbito o comercial: "{user_query}".
Aplica la regla de Escenario C: responde de forma educada pero cortante indicando que tu función se restringe a la asistencia sobre trámites públicos y leyes del Estado de Chile (ChileAtiende), sin extenderte en absoluto sobre el tema de entretenimiento planteado."""
    
    elif intent == "INFO_QUERY":
        prompt = f"""El usuario consulta: "{user_query}"
Responde en base a la información oficial recuperada en el RAG:
{rag_context}

Sintetiza la respuesta detallando los requisitos, canales de atención, costos y enlaces oficiales si existen. Si el RAG no arrojó información útil pero corresponde legítimamente al ámbito estatal de Chile, brinda una orientación general cordial, sugiriendo verificar en los canales directos del organismo pertinente o llamando al Call Center 101.

=== INVITACIÓN A RECORDATORIO (OBLIGATORIA) ===
Al final de tu respuesta, debes invitar de forma proactiva y cordial al usuario consultándole si le gustaría que le crees un recordatorio para realizar este trámite en su Google Calendar personal. Usa una frase similar a:
"¿Te gustaría que te cree un recordatorio para este trámite en tu Google Calendar? Solo indícame la fecha, hora y tu correo electrónico."
Esto es muy importante para incentivar el uso del asistente."""

    else:  # CREATE_REMINDER
        if validation_status == "valid":
            prompt = f"""El recordatorio ha sido agendado exitosamente.
El sistema de calendario reportó: {calendar_response}

Responde al usuario confirmando de forma amigable que el recordatorio para el trámite fue creado y que se le envió una invitación al correo electrónico provisto en los detalles. Resume brevemente los requisitos del trámite si estaban disponibles en la base de conocimientos:
{rag_context}"""
        
        elif validation_status == "missing_info":
            missing_fields_str = ", ".join(validation_errors)
            prompt = f"""El usuario desea agendar un recordatorio pero faltan datos esenciales.
Campos faltantes detectados: {missing_fields_str}
Consulta original del usuario: "{user_query}"

Pregúntale al usuario de forma muy cordial y explícita por la información faltante.
- Si falta el correo: "¿A qué correo electrónico te envío la invitación para el recordatorio?"
- Si falta la fecha/hora: solicita que te indique el día y hora preferida para agendar el recordatorio."""
        
        else:  # invalid_format (max retries reached)
            prompt = f"""Se intentó extraer y validar los datos del recordatorio para "{user_query}", pero los formatos ingresados (correo o fecha) siguen siendo inválidos tras varios intentos.
Errores detectados: {", ".join(validation_errors)}

Explica amablemente al usuario que no pudiste agendar el recordatorio en su calendario debido a inconsistencias en el correo electrónico o la fecha provista. Ofrécele resolver sus dudas sobre los requisitos del trámite de forma manual."""

    messages = [
        {"role": "system", "content": system_prompt}
    ]
    if history:
        for msg in history[-4:]:
            messages.append({"role": msg.get("role", "user"), "content": msg.get("content", "")})
    messages.append({"role": "user", "content": prompt})

    try:
        response = call_groq_with_retry(
            model=model,
            messages=messages,
            temperature=0.3
        )
        final_answer = response.choices[0].message.content.strip()
        final_answer = clean_think_tags(final_answer)
    except Exception as e:
        logger.error(f"Error en síntesis: {e}")
        final_answer = f"Lo siento, ocurrió un inconveniente al redactar la respuesta. Sin embargo, logré procesar tu solicitud."

    new_trace = state.get("trace", []).copy()
    new_trace.append({
        "type": "final_answer",
        "content": final_answer
    })

    return {
        "final_response": final_answer,
        "trace": new_trace
    }

# ==========================================
# 3. ENRUTAMIENTO Y BUCLE CÍCLICO (EDGES)
# ==========================================

def route_after_intent(state: AgentState) -> Literal["synthesize_response", "retrieve_rag", "extract_reminder_details"]:
    intent = state.get("intent", "INFO_QUERY")
    requires_rag = state.get("requires_rag", True)
    if intent == "OUT_OF_SCOPE":
        return "synthesize_response"
    if intent == "CREATE_REMINDER" and not requires_rag:
        logger.info("Saltando RAG porque la información ya existe en el historial conversacional.")
        return "extract_reminder_details"
    return "retrieve_rag"

def route_after_rag(state: AgentState) -> Literal["synthesize_response", "extract_reminder_details"]:
    intent = state.get("intent", "INFO_QUERY")
    if intent == "INFO_QUERY":
        return "synthesize_response"
    return "extract_reminder_details"

def route_after_validation(state: AgentState) -> Literal["create_calendar_event", "synthesize_response", "extract_reminder_details"]:
    status = state.get("validation_status", "valid")
    retry_count = state.get("retry_count", 0)
    
    if status == "valid":
        return "create_calendar_event"
    elif status == "missing_info":
        return "synthesize_response"
    else:  # invalid_format
        # Si no hemos superado el límite de 3 reintentos, volvemos a extraer
        if retry_count < 3:
            logger.info(f"Reintento de extracción detectado. Intento: {retry_count}")
            return "extract_reminder_details"
        else:
            logger.warning("Límite de reintentos alcanzado en validación.")
            return "synthesize_response"


# ==========================================
# 4. INSTANCIACIÓN Y COMPILACIÓN DEL GRAFO
# ==========================================
workflow = StateGraph(AgentState)

# Agregar nodos al grafo
workflow.add_node("get_system_datetime", get_system_datetime)
workflow.add_node("classify_intent", classify_intent)
workflow.add_node("retrieve_rag", retrieve_rag)
workflow.add_node("extract_reminder_details", extract_reminder_details)
workflow.add_node("validate_details", validate_details)
workflow.add_node("create_calendar_event", create_calendar_event)
workflow.add_node("synthesize_response", synthesize_response)

# Configurar punto de entrada
workflow.set_entry_point("get_system_datetime")

# Conectar primer nodo de sistema con el clasificador
workflow.add_edge("get_system_datetime", "classify_intent")

# Configurar aristas y enrutamiento dinámico
workflow.add_conditional_edges(
    "classify_intent",
    route_after_intent,
    {
        "synthesize_response": "synthesize_response",
        "retrieve_rag": "retrieve_rag",
        "extract_reminder_details": "extract_reminder_details"
    }
)

workflow.add_conditional_edges(
    "retrieve_rag",
    route_after_rag,
    {
        "synthesize_response": "synthesize_response",
        "extract_reminder_details": "extract_reminder_details"
    }
)

# Arista normal (secuencial)
workflow.add_edge("extract_reminder_details", "validate_details")

workflow.add_conditional_edges(
    "validate_details",
    route_after_validation,
    {
        "create_calendar_event": "create_calendar_event",
        "synthesize_response": "synthesize_response",
        "extract_reminder_details": "extract_reminder_details"  # Bucle de reintento (Ciclo)
    }
)

# Conectar nodos de salida hacia el sintetizador final
workflow.add_edge("create_calendar_event", "synthesize_response")
workflow.add_edge("synthesize_response", END)

# Compilar grafo
compiled_graph = workflow.compile()


# ==========================================
# 5. FUNCIÓN COMPATIBLE CON EL BACKEND API
# ==========================================
def get_response(
    user_message: str,
    history: Optional[List[Dict[str, str]]] = None
) -> Dict[str, Any]:
    """
    Función de entrada para el servidor FastAPI y pruebas.
    Ejecuta el grafo compilado y devuelve la respuesta y la traza.
    """
    initial_state: AgentState = {
        "user_query": user_message,
        "history": history or [],
        "intent": "INFO_QUERY",
        "requires_rag": True,
        "rag_context": "",
        "reminder_details": {},
        "validation_status": "valid",
        "validation_errors": [],
        "retry_count": 0,
        "feedback_message": None,
        "final_response": "",
        "system_time": "",
        "trace": []
    }
    
    # Ejecutar el grafo de forma síncrona para retornar la respuesta a la API
    final_state = compiled_graph.invoke(initial_state)
    
    return {
        "response": final_state.get("final_response", ""),
        "trace": final_state.get("trace", [])
    }


# ==========================================
# 6. EJECUCIÓN Y PRUEBAS STANDALONE (.stream)
# ==========================================
if __name__ == "__main__":
    import sys
    # Reconfigure stdout for UTF-8 compatibility
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
        
    print("=== INICIANDO PRUEBAS DEL AGENTE LANGGRAPH (STREAMING) ===\n")
    
    test_cases = [
        {
            "name": "Prueba 1: Consulta Fuera de Ámbito (Out of Scope)",
            "query": "Hola, ¿me puedes dar consejos para subir de nivel rápido en Elden Ring?"
        },
        {
            "name": "Prueba 2: Consulta de Información (RAG)",
            "query": "¿Qué papeles piden para renovar la cédula de identidad y cuánto cuesta?"
        },
        {
            "name": "Prueba 3: Recordatorio Válido (Calendario + RAG)",
            "query": "Hola, necesito renovar la cédula de identidad. Agéndame un recordatorio para mañana a las 11 AM al correo ciudadano@ejemplo.cl"
        },
        {
            "name": "Prueba 4: Recordatorio con Datos Faltantes (Falta Correo)",
            "query": "Por favor, agenda un recordatorio para renovar mi pasaporte el próximo lunes a las 10:00"
        },
        {
            "name": "Prueba 5: Recordatorio con Información ya Presente en Historial (Skipea RAG)",
            "query": "Genial, por favor agéndame el recordatorio para mañana a las 11 AM al correo ciudadano@ejemplo.cl",
            "history": [
                {"role": "user", "content": "¿Qué requisitos piden para renovar la cédula de identidad?"},
                {"role": "assistant", "content": "Para chilenos que renuevan cédula se requiere presentar la cédula anterior (si la tiene). El costo es de $3.820 pesos chilenos."}
            ]
        }
    ]
    
    for case in test_cases:
        print(f"--- {case['name']} ---")
        print(f"Query del usuario: '{case['query']}'")
        
        initial_state: AgentState = {
            "user_query": case["query"],
            "history": case.get("history", []),
            "intent": "INFO_QUERY",
            "requires_rag": True,
            "rag_context": "",
            "reminder_details": {},
            "validation_status": "valid",
            "validation_errors": [],
            "retry_count": 0,
            "feedback_message": None,
            "final_response": "",
            "system_time": "",
            "trace": []
        }
        
        # Iterar sobre la ejecución utilizando .stream() para capturar transiciones
        for output in compiled_graph.stream(initial_state):
            # Obtener el nombre del nodo ejecutado y su estado parcial
            for node_name, partial_state in output.items():
                print(f" [NODO EJECUTADO]: {node_name}")
                if "system_time" in partial_state:
                    print(f"   ↳ Hora del servidor obtenida: {partial_state['system_time']}")
                if "intent" in partial_state:
                    print(f"   ↳ Intento clasificado: {partial_state['intent']}")
                if "requires_rag" in partial_state:
                    print(f"   ↳ Requiere RAG: {partial_state['requires_rag']}")
                if "rag_context" in partial_state:
                    print(f"   ↳ RAG context: {len(partial_state['rag_context'])} caracteres recuperados.")
                if "reminder_details" in partial_state:
                    print(f"   ↳ Detalles del Recordatorio: {partial_state['reminder_details']}")
                if "validation_status" in partial_state:
                    print(f"   ↳ Estado de Validación: {partial_state['validation_status']}")
                    if partial_state.get("validation_errors"):
                        print(f"   ↳ Errores: {partial_state['validation_errors']}")
                if "final_response" in partial_state:
                    # Mostrar las primeras 120 letras de la respuesta del nodo
                    preview = partial_state['final_response'][:120].replace('\n', ' ')
                    print(f"   ↳ Respuesta: {preview}...")
        
        # Obtener resultado final de forma síncrona para imprimirlo completo
        res = get_response(case["query"], history=case.get("history", []))
        print("\n=== RESPUESTA FINAL AL CIUDADANO ===")
        print(res["response"])
        print("======================================\n")
