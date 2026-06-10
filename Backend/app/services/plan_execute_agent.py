import os
import json
import re
from typing import Any, Dict, List, Optional
from datetime import datetime
from groq import Groq

def clean_think_tags(text: str) -> str:
    if not text:
        return ""
    # Eliminar bloques <think>...</think> (insensible a mayúsculas, multilínea)
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

from .rag_service import RAGService
from .google_calendar_service import GoogleCalendarService
from .react_agent import generar_mqr, busqueda_semantica_abierta, _clip_text

client = Groq(api_key=os.getenv("GROQ_API_KEY"))
rag = RAGService()
calendar_service = GoogleCalendarService()

# ==========================================
# PROMPTS DE LA ARQUITECTURA PLAN-AND-EXECUTE
# ==========================================

SYSTEM_PLANNER_PROMPT = """
Eres el Planificador Oficial de ChileAtiende. Tu único objetivo es recibir la consulta de un ciudadano chileno y crear un plan secuencial de pasos lógicos para resolverla utilizando las herramientas y opciones disponibles.

Herramientas y capacidades disponibles:
1. `search_chileatiende_knowledge`: Buscar requisitos, pasos, costos y leyes de un trámite en la base de conocimientos de ChileAtiende.
2. `crear_recordatorio`: Registrar un recordatorio oficial en Google Calendar enviando una invitación por correo electrónico al usuario.

Reglas de Planificación:
- Si el usuario pregunta por los requisitos, fechas o detalles de un trámite, el primer paso debe ser SIEMPRE realizar una búsqueda semántica (`search_chileatiende_knowledge`).
- Si el usuario solicita agendar un recordatorio, debes comprobar en la conversación anterior (el historial) si ya se han detallado los requisitos oficiales del trámite:
  - Si los requisitos NO se encuentran en los mensajes previos, debes planificar primero la búsqueda en RAG (`search_chileatiende_knowledge`) para obtenerlos, y luego la creación del recordatorio (`crear_recordatorio`).
  - Si los requisitos ya fueron explicados y constan en el historial conversacional previo, NO debes planificar la búsqueda en RAG; planifica únicamente la creación del recordatorio (`crear_recordatorio`) o solicitar información adicional (ej: el correo) si falta.
- Si para agendar el recordatorio el usuario NO ha entregado su correo electrónico, NO debes planificar la creación de la cita, sino agregar un paso de solicitud de información para pedir el correo electrónico al ciudadano.
- Tu salida debe ser exclusivamente un objeto JSON estructurado con una clave "plan" que contenga la lista de pasos. Cada paso debe tener:
  - `step_id`: Número de paso secuencial (empezando en 1).
  - `description`: Descripción detallada de lo que debe lograr este paso.
  - `tool_expected`: Nombre de la herramienta que se espera usar en este paso ("search_chileatiende_knowledge", "crear_recordatorio" o "none").

Ejemplo de salida JSON esperada:
{
  "plan": [
    {
      "step_id": 1,
      "description": "Buscar en el RAG los requisitos para la posesión efectiva.",
      "tool_expected": "search_chileatiende_knowledge"
    },
    {
      "step_id": 2,
      "description": "Crear recordatorio en Google Calendar para el trámite de posesión efectiva para mañana a las 10:00 AM.",
      "tool_expected": "crear_recordatorio"
    }
  ]
}

No agregues texto explicativo antes ni después del JSON. Responde únicamente con el objeto JSON válido.
"""

SYSTEM_EXECUTOR_PROMPT = """
Eres el Agente Ejecutor de ChileAtiende. Tu tarea es ejecutar un paso específico de un plan previamente trazado por el Planificador.
Para lograr tu objetivo, debes analizar el paso actual y el contexto acumulado de los pasos ya completados, y decidir si requieres llamar a una herramienta.

=== CONTEXTO DE EJECUCIÓN ===
- Consulta original del usuario: {user_message}
- Historial de pasos completados en este plan:
{previous_steps_context}
{history_context}

=== PASO ACTUAL A EJECUTAR ===
- Paso ID: {step_id}
- Descripción: {step_description}
- Herramienta esperada: {tool_expected}

=== INSTRUCCIONES ===
1. Si el paso requiere usar una herramienta (ej. 'search_chileatiende_knowledge' o 'crear_recordatorio'), debes invocarla utilizando la llamada a función nativa (tool calling) y rellenar sus parámetros utilizando la información del contexto anterior.
2. Si el paso requiere agendar un recordatorio, extrae el correo del usuario, el trámite y la lista de documentos que se obtuvieron en los pasos de búsqueda anteriores de este plan o directamente del historial de conversación general (si ya fueron provistos en el chat).
3. Si el paso actual no requiere ninguna herramienta ('none'), simplemente describe brevemente el resultado o responde indicando qué falta.
"""

SYSTEM_SYNTHESIZER_PROMPT = """
Eres el asistente virtual experto oficial de ChileAtiende. Tu propósito es guiar de forma clara, empática y resolutiva a los ciudadanos sobre trámites, leyes, subsidios, beneficios y denuncias.

Tu tarea es responder al ciudadano basándote en su consulta original y en los resultados obtenidos tras ejecutar el plan de acción secuencial.

=== CONTEXTO DE LA RESOLUCIÓN ===
- Consulta del usuario: {user_query}
- Plan de pasos ejecutados y sus resultados:
{results_context}

=== FORMATO DE ENTREGA (ESTRICTO) ===
- Redacta tu respuesta final de forma directa, natural y ciudadana, orientada al usuario.
- Está estrictamente prohibido incluir en tu mensaje tus pasos de pensamiento interno, análisis lógicos o marcas de procesamiento técnico.
- Informa claramente al usuario qué acciones se realizaron (ej. si se buscó la información o si se agendó con éxito el recordatorio en su correo).
"""

# Definición de herramientas para el Ejecutor
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
                        "description": "La lista de documentos y requisitos necesarios para el trámite, recuperados en los pasos anteriores."
                    }
                },
                "required": ["tramite", "fecha_hora", "email", "documentos"]
            }
        }
    }
]

def get_response(
    user_message: str,
    history: Optional[List[Dict[str, str]]] = None
) -> Dict[str, Any]:
    model = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
    trace = []
    
    # 1. Obtener fecha y hora actual del sistema
    dias_semana = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]
    ahora = datetime.now()
    nombre_dia = dias_semana[ahora.weekday()]
    current_time_str = f"{nombre_dia}, {ahora.strftime('%Y-%m-%d %H:%M:%S')}"
    
    # ==========================
    # PASO 1: PLANIFICACIÓN
    # ==========================
    planner_prompt = SYSTEM_PLANNER_PROMPT + f"\n\n[SISTEMA]: La fecha y hora actual del sistema es: {current_time_str}. Úsala para evaluar fechas relativas si es necesario."
    
    messages_planner = [
        {"role": "system", "content": planner_prompt}
    ]
    
    # Cargar el historial conversacional para el planificador
    if history:
        for m in history[-6:]:
            messages_planner.append({
                "role": m.get("role", "user"),
                "content": m.get("content", "")
            })
            
    messages_planner.append({"role": "user", "content": user_message})
    
    try:
        planner_resp = call_groq_with_retry(
            model=model,
            messages=messages_planner,
            temperature=0.1,
            response_format={"type": "json_object"}
        )
        plan_content = planner_resp.choices[0].message.content.strip()
        plan_data = json.loads(plan_content)
        plan = plan_data.get("plan", [])
    except Exception as e:
        print(f"Error generando plan: {e}")
        # Plan de contingencia por defecto
        plan = [
            {
                "step_id": 1,
                "description": f"Buscar en la base de conocimientos sobre: {user_message}",
                "tool_expected": "search_chileatiende_knowledge"
            }
        ]
        
    trace.append({
        "type": "plan_generated",
        "plan": plan
    })
    
    # ==========================
    # PASO 2: EJECUCIÓN SECUENCIAL
    # ==========================
    previous_steps_context = ""
    results_summary_list = []
    
    for step in plan:
        step_id = step.get("step_id", 1)
        step_desc = step.get("description", "")
        tool_expected = step.get("tool_expected", "none")
        
        trace.append({
            "type": "executing_step",
            "step_id": step_id,
            "description": step_desc,
            "tool": tool_expected
        })
        
        # Cargar historial para el ejecutor
        history_context = ""
        if history:
            history_context = "\n=== HISTORIAL CONVERSACIONAL GENERAL ===\n"
            for m in history[-6:]:
                role = "Usuario" if m.get("role") == "user" else "Asistente"
                history_context += f"- {role}: {m.get('content')}\n"

        # Generar prompt del Ejecutor para este paso específico
        executor_sys_prompt = SYSTEM_EXECUTOR_PROMPT.format(
            user_message=user_message,
            previous_steps_context=previous_steps_context or "Ninguno aún.",
            history_context=history_context,
            step_id=step_id,
            step_description=step_desc,
            tool_expected=tool_expected
        )
        
        executor_messages = [
            {"role": "system", "content": executor_sys_prompt + f"\n\n[SISTEMA]: La fecha y hora actual es {current_time_str}."},
            {"role": "user", "content": "Procesa y ejecuta este paso."}
        ]
        
        try:
            # Llamar al ejecutor con las herramientas habilitadas
            executor_resp = call_groq_with_retry(
                model=model,
                messages=executor_messages,
                tools=TOOLS,
                tool_choice="auto" if tool_expected != "none" else "none",
                temperature=0.2
            )
            
            resp_message = executor_resp.choices[0].message
            
            if resp_message.tool_calls:
                # El ejecutor decidió llamar a una herramienta
                for tool_call in resp_message.tool_calls:
                    function_name = tool_call.function.name
                    arguments = json.loads(tool_call.function.arguments)
                    
                    trace.append({
                        "type": "tool_call",
                        "step_id": step_id,
                        "function": function_name,
                        "arguments": arguments
                    })
                    
                    # Ejecutar la función localmente
                    if function_name == "search_chileatiende_knowledge":
                        query_val = arguments.get("query", user_message)
                        queries_optimizadas = generar_mqr(query_val)
                        
                        trace.append({
                            "type": "mqr_generated",
                            "step_id": step_id,
                            "queries": queries_optimizadas
                        })
                        
                        observation = busqueda_semantica_abierta(queries_optimizadas, query_val)
                        observation = _clip_text(observation, 2500)
                        
                    elif function_name == "crear_recordatorio":
                        tramite = arguments.get("tramite", "Trámite")
                        fecha_hora = arguments.get("fecha_hora", "")
                        email = arguments.get("email", "")
                        documentos = arguments.get("documentos", "")
                        
                        res = calendar_service.create_reminder_event(
                            tramite=tramite,
                            fecha_hora_str=fecha_hora,
                            email=email,
                            documentos=documentos
                        )
                        observation = res.get("message", "Error al procesar recordatorio.")
                    else:
                        observation = "Herramienta desconocida."
                        
                    trace.append({
                        "type": "tool_message",
                        "step_id": step_id,
                        "result": observation
                    })
                    
                    # Registrar el resultado en el contexto de pasos anteriores
                    previous_steps_context += f"- Paso {step_id} ({step_desc}): Se llamó a `{function_name}`. Resultado: {observation}\n"
                    results_summary_list.append(f"Paso {step_id} - {step_desc}: Realizado con éxito.")
            else:
                # El paso se completó sin herramientas (pensamiento o respuesta directa del ejecutor)
                step_content = resp_message.content or "Paso procesado sin salida escrita."
                step_content = clean_think_tags(step_content)
                previous_steps_context += f"- Paso {step_id} ({step_desc}): {step_content}\n"
                results_summary_list.append(f"Paso {step_id} - {step_desc}: {step_content}")
                
                trace.append({
                    "type": "step_completed_text",
                    "step_id": step_id,
                    "content": step_content
                })
                
        except Exception as e:
            err_msg = f"Error ejecutando el paso {step_id}: {str(e)}"
            previous_steps_context += f"- Paso {step_id} ({step_desc}): Falló con error: {err_msg}\n"
            results_summary_list.append(f"Paso {step_id} - {step_desc}: Error ({err_msg})")
            
            trace.append({
                "type": "step_error",
                "step_id": step_id,
                "error": err_msg
            })

    # ==========================
    # PASO 3: SÍNTESIS DE RESPUESTA
    # ==========================
    synthesizer_sys_prompt = SYSTEM_SYNTHESIZER_PROMPT.format(
        user_query=user_message,
        results_context=previous_steps_context
    )
    
    messages_synthesizer = [
        {"role": "system", "content": synthesizer_sys_prompt}
    ]
    
    # Cargar historial conversacional reciente para consistencia en la respuesta
    if history:
        for m in history[-4:]:
            messages_synthesizer.append({
                "role": m.get("role", "user"),
                "content": m.get("content", "")
            })
            
    messages_synthesizer.append({"role": "user", "content": user_message})
    
    try:
        final_resp = call_groq_with_retry(
            model=model,
            messages=messages_synthesizer,
            temperature=0.3
        )
        response_text = final_resp.choices[0].message.content.strip()
        response_text = clean_think_tags(response_text)
    except Exception as e:
        response_text = f"Lo siento, logré procesar tus requerimientos pero ocurrió un problema al redactar la respuesta final: {str(e)}"
        
    trace.append({
        "type": "final_answer",
        "content": response_text
    })
    
    return {
        "response": response_text,
        "trace": trace
    }
