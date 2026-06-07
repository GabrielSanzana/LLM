import os
import json
from typing import Any, Dict, List, Optional

# pyrefly: ignore [missing-import]
from groq import Groq

# Importación relativa con '.' para evitar fallos de PYTHONPATH en Windows
from .rag_service import RAGService
from .google_calendar_service import GoogleCalendarService
from datetime import datetime

client = Groq(api_key=os.getenv("GROQ_API_KEY"))
rag: Optional[RAGService] = None
calendar_service: Optional[GoogleCalendarService] = None

# =========================
# PROMPT BASE (CHILEATIENDE)
# =========================

SYSTEM_PROMPT_GENERAL_TUTOR = """
Eres el asistente virtual experto oficial de ChileAtiende. Tu propósito es guiar de forma clara, empática y resolutiva a los ciudadanos sobre trámites, leyes, subsidios, beneficios y denuncias asociadas a las instituciones públicas del Estado de Chile.

=== REGLAS DE OPERACIÓN CON HERRAMIENTAS ===
*IMPORTANTE*: Para invocar herramientas, utiliza única y exclusivamente el mecanismo nativo de llamadas a funciones (tool calling) del sistema en formato JSON. Está ESTRICTAMENTE PROHIBIDO escribir de forma manual etiquetas de texto como `<function=...>` o marcas XML similares en el texto de tu respuesta para representar una llamada a herramienta.

1. CONSULTA OBLIGATORIA AL RAG: Ante cualquier consulta sobre requisitos, pasos, fechas o detalles de un trámite o ley, debes invocar la herramienta `search_chileatiende_knowledge` antes de responder. Está prohibido responder datos técnicos de memoria.
2. RECORDATORIOS INTELIGENTES Y GOOGLE CALENDAR: Si el usuario solicita agendar, anotar o recordar un trámite, debes:
   - Extraer la lista de requisitos y documentos necesarios desde el historial de conversación (es decir, el contexto recuperado por RAG en mensajes anteriores). Si el RAG no se ha consultado en esta conversación para este trámite, primero debes invocar la herramienta `search_chileatiende_knowledge` para buscar sus requisitos oficiales.
   - Si no tienes el correo del usuario, debes preguntarle explícitamente: "¿A qué correo electrónico te envío la invitación para el recordatorio?". No intentes invocar `crear_recordatorio` si no tienes el correo del usuario.
   - Si no tienes clara la fecha u hora en la que quiere agendar, pregúntale.
   - Una vez que tengas el trámite, los documentos, la fecha y hora calculada (convertida por ti a formato ISO 8601 YYYY-MM-DDTHH:MM:SS basándote en la fecha y hora actual del sistema que se te proporciona), y el correo del usuario, invoca la herramienta `crear_recordatorio`.

=== CLASIFICACIÓN DE RESPUESTAS SEGÚN EL CONTEXTO ===
- ESCENARIO A (Información disponible en el RAG): Sintetiza los datos entregados por la herramienta de forma clara y estructurada. Detalla canales de atención, requisitos (como ClaveÚnica) y costos.
- ESCENARIO B (Información ausente en el RAG pero de ámbito público/estatal): Si la consulta legítimamente corresponde al ecosistema público, legal o institucional chileno pero la herramienta no arrojó registros, ofrece una orientación conceptual básica basada en tu conocimiento institucional general. Identifica qué organismo del Estado podría gestionarlo y sugiere amablemente al ciudadano verificar los canales oficiales directos o llamar al Call Center 101.
- ESCENARIO C (Temáticas fuera de foco o comerciales): Si el usuario pregunta por temas recreativos, corporativos privados, entretenimiento, marcas comerciales, cultura pop o materias ajenas al servicio público (ej. videojuegos, series, bandas, etc.), debes responder de forma cortante indicando que tu rol se limita estrictamente a la orientación institucional del Estado de Chile. ESTÁ ESTRICTAMENTE PROHIBIDO definir el concepto ajeno, explicar su origen, dar ejemplos de él o continuar la conversación sobre ese tema de entretenimiento.

=== FORMATO DE ENTREGA (ESTRICTO) ===
- Redacta tu respuesta final de forma directa, natural y ciudadana, orientada al usuario.
- Está estrictamente prohibido incluir en tu mensaje final tus pasos de pensamiento interno (Thought), análisis lógicos, llamadas a funciones o marcas de procesamiento técnico. El ciudadano solo debe ver la respuesta limpia.
"""

# =========================
# LÓGICA DE MULTI-QUERY RETRIEVAL (MQR)
# =========================

def generar_mqr(user_query: str) -> List[str]:
    """
    Genera Multi-Query Rewriting (MQR):
    1 formal
    1 requisitos/documentos
    1 semántico/técnico
    """
    prompt = f"""
    Usuario: "{user_query}"

    Genera 3 variantes de búsqueda para un sistema RAG.

    Reglas:
    - 1 versión formal/institucional
    - 1 enfocada en requisitos o documentos
    - 1 versión semántica/técnica
    - Frases cortas
    - Sin numeración
    - Una por línea
    """
    try:
        model = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
        resp = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3
        )
        texto = resp.choices[0].message.content.strip()
        variantes = [v.strip("- *").strip() for v in texto.split("\n") if v.strip()]
        
        return variantes[:3] + [user_query]
    except Exception as e:
        print(f"Error en generación MQR: {e}")
        return [user_query]


def busqueda_semantica_abierta(queries: List[str], user_query: str) -> str:
    """Ejecuta la búsqueda en el RAG y retorna banderas claras al LLM."""
    global rag
    if rag is None:
        rag = RAGService()
        
    resultados_unicos = set()
    
    for q in queries:
        contexto_parcial = rag.get_knowledge(q)
        if contexto_parcial and contexto_parcial.strip():
            resultados_unicos.add(contexto_parcial.strip())
            
    # SI EL RAG ESTÁ VACÍO: Le damos un mensaje estructurado al LLM para que sepa diferenciar
    if not resultados_unicos:
        return f"""
        [SISTEMA RAG]: No se encontraron documentos exactos en ChromaDB para la consulta: "{user_query}".
        INSTRUCCIÓN PARA EL LLM: Si la consulta del usuario parece ser un trámite, ley o institución pública real (aunque no tengamos el documento), ofrece disculpas e invita al usuario a consultar directamente en los sitios web del gobierno o llamar al 101. No asumas que es un tema comercial a menos que sea explícitamente algo ajeno al Estado.
        """
        
    return "\n\n--- Información Oficial Encontrada ---\n\n".join(resultados_unicos)


# --- DEFINICIÓN DE HERRAMIENTAS (Function Calling) ---
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search_chileatiende_knowledge",
            "description": "Realiza una búsqueda semántica en la base de conocimientos del Registro Civil. Usa esta herramienta para buscar requisitos, procesos o leyes.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "La consulta principal del usuario para buscar en la documentación."
                    }
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "crear_recordatorio",
            "description": "Crea un recordatorio en Google Calendar y envía una invitación al correo del usuario. Requiere el correo, el trámite, los documentos necesarios extraídos del RAG y la fecha/hora específica.",
            "parameters": {
                "type": "object",
                "properties": {
                    "tramite": {
                        "type": "string", 
                        "description": "El nombre del trámite a recordar (ej. 'Renovación de cédula de identidad')."
                    },
                    "fecha_hora": {
                        "type": "string", 
                        "description": "La fecha y hora del evento. Debe ser convertida por ti a formato ISO 8601 (YYYY-MM-DDTHH:MM:SS) basándote en la fecha y hora actual del sistema. Si el usuario no especificó hora, asume las 09:00:00."
                    },
                    "email": {
                        "type": "string",
                        "description": "El correo electrónico del usuario al cual enviar la invitación."
                    },
                    "documentos": {
                        "type": "string",
                        "description": "La lista de documentos y requisitos necesarios para el trámite, recuperados de la base de conocimientos (RAG) en los mensajes anteriores de la conversación."
                    }
                },
                "required": ["tramite", "fecha_hora", "email", "documentos"]
            }
        }
    }
]

def _clip_text(text: str, max_len: int = 2500) -> str:
    if not text:
        return ""
    if len(text) <= max_len:
        return text
    return text[:max_len] + "\n...[TRUNCADO CONTEXTO RAG]..."


# =========================
# FUNCIÓN PRINCIPAL DE ATENCIÓN (CHAT GENERAL)
# =========================

def get_response(
    user_message: str,
    history: Optional[List[Dict[str, str]]] = None,
    max_steps: int = 2
) -> Dict[str, Any]:
    global rag, calendar_service
    if rag is None:
        rag = RAGService()
    if calendar_service is None:
        calendar_service = GoogleCalendarService()

    model = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
    
    dias_semana = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]
    ahora = datetime.now()
    nombre_dia = dias_semana[ahora.weekday()]
    current_time_str = f"{nombre_dia}, {ahora.strftime('%Y-%m-%d %H:%M:%S')}"
    system_prompt = SYSTEM_PROMPT_GENERAL_TUTOR + f"\n\n[SISTEMA]: La fecha y hora actual del sistema es: {current_time_str}. Úsala para calcular fechas relativas como 'mañana', 'lunes', etc."

    messages = [
        {"role": "system", "content": system_prompt}
    ]

    # Cargar el historial conversacional reciente
    if history:
        for m in history[-8:]:
            messages.append({
                "role": m.get("role", "user"),
                "content": m.get("content", "")
            })

    messages.append({"role": "user", "content": user_message})
    trace = []

    for step in range(max_steps):
        response = client.chat.completions.create(
            model=model,
            messages=messages,
            tools=TOOLS,
            tool_choice="auto",
            temperature=0.4
        )

        response_message = response.choices[0].message
        if not response_message.tool_calls:
            trace.append({
                "type": "final_answer",
                "content": response_message.content
            })
            return {
                "response": response_message.content,
                "trace": trace
            }

        messages.append(response_message)

        for tool_call in response_message.tool_calls:
            function_name = tool_call.function.name
            arguments = json.loads(tool_call.function.arguments)

            trace.append({
                "type": "tool_call",
                "function": function_name,
                "arguments": arguments
            })

            if function_name == "search_chileatiende_knowledge":
                queries_optimizadas = generar_mqr(arguments["query"])
                trace.append({
                    "type": "mqr_generated",
                    "queries": queries_optimizadas
                })

                observation = busqueda_semantica_abierta(queries_optimizadas, arguments["query"])
                observation = _clip_text(observation, 3000)

            elif function_name == "crear_recordatorio":
                tramite = arguments.get("tramite", "Trámite desconocido")
                fecha = arguments.get("fecha_hora", "Sin fecha")
                email = arguments.get("email")
                documentos = arguments.get("documentos", "")
                
                res = calendar_service.create_reminder_event(
                    tramite=tramite,
                    fecha_hora_str=fecha,
                    email=email,
                    documentos=documentos
                )
                observation = res.get("message", "Error al procesar recordatorio.")
            else:
                observation = "Herramienta no soportada."

            trace.append({
                "type": "tool_message",
                "result": observation
            })

            messages.append({
                "role": "tool",
                "tool_call_id": tool_call.id,
                "name": function_name,
                "content": observation
            })

    # Llamada final al LLM para responder con todo el contexto acumulado
    final_response = client.chat.completions.create(
        model=model,
        messages=messages,
        temperature=0.3
    )

    trace.append({
        "type": "final_answer",
        "content": final_response.choices[0].message.content
    })

    return {
        "response": final_response.choices[0].message.content,
        "trace": trace
    }