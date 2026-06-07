import os
import json
from typing import Any, Dict, List, Optional

# pyrefly: ignore [missing-import]
from groq import Groq

# Importación relativa con '.' para evitar fallos de PYTHONPATH en Windows
from .rag_service import RAGService

client = Groq(api_key=os.getenv("GROQ_API_KEY"))
rag: Optional[RAGService] = None

# =========================
# PROMPT BASE (CHILEATIENDE)
# =========================

SYSTEM_PROMPT_GENERAL_TUTOR = """
Eres el asistente virtual experto oficial de ChileAtiende. Tu propósito es guiar de forma clara, empática y resolutiva a los ciudadanos sobre trámites, leyes, subsidios, beneficios y denuncias asociadas a las instituciones públicas del Estado de Chile.

=== REGLAS DE OPERACIÓN CON HERRAMIENTAS ===
1. CONSULTA OBLIGATORIA AL RAG: Ante cualquier consulta sobre requisitos, pasos, fechas o detalles de un trámite o ley, debes invocar la herramienta `search_chileatiende_knowledge` antes de responder. Está prohibido responder datos técnicos de memoria.
2. RECORDATORIOS INTELIGENTES: Si el usuario solicita agendar, anotar o recordar un evento o trámite, invoca la herramienta `crear_recordatorio`, infiriendo el contexto y los datos necesarios a partir del historial reciente de la conversación.

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
            "description": "Crea un recordatorio en la agenda del usuario. Úsalo cuando el usuario diga 'recuérdamelo', 'agenda eso', etc.",
            "parameters": {
                "type": "object",
                "properties": {
                    "tramite": {
                        "type": "string", 
                        "description": "El trámite deducido de la memoria a corto plazo de la conversación (ej. 'Renovación de cédula')."
                    },
                    "fecha_hora": {
                        "type": "string", 
                        "description": "La fecha o momento en que se debe recordar (ej. 'Mañana a las 10am'). Si no se especifica, usa 'Próximamente'."
                    }
                },
                "required": ["tramite"]
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
    global rag
    if rag is None:
        rag = RAGService()

    model = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
    
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT_GENERAL_TUTOR}
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
            return {
                "response": response_message.content,
                "trace": trace
            }
        # Caso en que el modelo decide buscar información técnica del trámite en ChromaDB
        if response_message.tool_calls:
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
                    # Expansión MQR y búsqueda abierta
                    queries_optimizadas = generar_mqr(arguments["query"])
                    trace.append({
                        "type": "mqr_expansion",
                        "expanded_queries": queries_optimizadas
                    })

                    # Busca esta línea dentro de get_tutor_response:
                    observation = busqueda_semantica_abierta(queries_optimizadas, arguments["query"])
                    observation = _clip_text(observation, 3000)

                elif function_name == "crear_recordatorio":
                    tramite = arguments.get("tramite", "Trámite desconocido")
                    fecha = arguments.get("fecha_hora", "Sin fecha")
                    observation = f"✅ Éxito: Recordatorio guardado en sistema para '{tramite}' ({fecha})."
                else:
                    observation = "Herramienta no soportada."

                trace.append({
                    "type": "tool_response",
                    "query_usada": arguments.get("query"),
                    "longitud_resultado": len(observation)
                })

                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "name": function_name,
                    "content": observation
                })

            # Respuesta analítica final al ciudadano con los datos inyectados por el RAG
            final_response = client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=0.3
            )

            return {
                "response": final_response.choices[0].message.content,
                "trace": trace
            }

        # Caso en el que el modelo responde directamente (saludos, aclaraciones libres, etc.)
        return {
            "response": response_message.content,
            "trace": trace
        }

    return {
        "response": "Lo sentimos, ocurrió un error interno al procesar su solicitud en este momento.",
        "trace": trace
    }