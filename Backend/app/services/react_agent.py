import os
import json
from pathlib import Path
from typing import List, Dict, Any

try:
    from groq import Groq
except ImportError:
    Groq = None

# Intentamos importar librerías para Búsqueda Semántica
try:
    import chromadb
    from chromadb.utils import embedding_functions
except ImportError:
    chromadb = None

BASE_DIR = Path(__file__).resolve().parents[2]
from dotenv import load_dotenv
load_dotenv(BASE_DIR.parent / ".env")

# --- CONFIGURACIÓN DE BÚSQUEDA SEMÁNTICA (ChromaDB) ---
# En un entorno real, inicializarías ChromaDB una vez al arrancar la app.
if chromadb:
    chroma_client = chromadb.Client()
    # Usamos un modelo de embeddings ligero multilingüe
    emb_fn = embedding_functions.SentenceTransformerEmbeddingFunction(model_name="paraphrase-multilingual-MiniLM-L12-v2")
    collection = chroma_client.get_or_create_collection(name="registro_civil_docs", embedding_function=emb_fn)
    
    # Simulación: Agregamos documentos a la DB Vectorial si está vacía
    if collection.count() == 0:
        collection.add(
            documents=[
                "Para hacer una denuncia en el Registro Civil por pérdida de documentos, se requiere identificación oficial y comprobante de domicilio.",
                "Para el matrimonio civil, los contrayentes deben presentar cédula de identidad, certificado de soltería y dos testigos.",
                "La corrección de errores en actas de nacimiento requiere un proceso administrativo y el documento probatorio original."
            ],
            metadatas=[{"source": "denuncias.txt"}, {"source": "matrimonio.txt"}, {"source": "correcciones.txt"}],
            ids=["doc1", "doc2", "doc3"]
        )


def generar_mqr(user_query: str, client: Groq, model: str) -> List[str]:
    """Genera 3 variaciones de la consulta usando MQR."""
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
        resp = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3
        )
        texto = resp.choices[0].message.content.strip()
        variantes = [v.strip("- *").strip() for v in texto.split("\n") if v.strip()]
        # Asegurar que la original también esté
        return variantes[:3] + [user_query]
    except Exception as e:
        print(f"Error en MQR: {e}")
        return [user_query]


def busqueda_semantica(queries: List[str], k: int = 2) -> str:
    """Busca en la base de datos vectorial usando las consultas generadas."""
    if not chromadb:
        return "[Aviso] Búsqueda semántica no disponible. Instale chromadb y sentence-transformers."
    
    try:
        # Buscamos usando todas las variaciones MQR
        results = collection.query(query_texts=queries, n_results=k)
        
        # Consolidar resultados únicos
        documentos_encontrados = set()
        for doc_list in results["documents"]:
            for doc in doc_list:
                documentos_encontrados.add(doc)
                
        if not documentos_encontrados:
            return "No se encontraron documentos relevantes en la base de conocimiento."
            
        return "\n\n".join([f"- {doc}" for doc in documentos_encontrados])
    except Exception as e:
        return f"Error en búsqueda vectorial: {str(e)}"


# --- DEFINICIÓN DE HERRAMIENTAS (Function Calling) ---
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search_docs",
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


def get_response(user_message: str, history: List[Dict[str, str]] = None, max_steps: int = 3) -> Dict[str, Any]:
    """Proceso de Tool Calling nativo. Retorna respuesta limpia y un trace para la consola."""
    history = history or []
    model = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
    api_key = os.getenv("GROQ_API_KEY")

    if Groq is None or not api_key:
        return {"response": "[ERROR] Configure Groq correctamente.", "trace": []}

    client = Groq(api_key=api_key)

    system_prompt = (
        "Eres un asistente del Registro Civil. "
        "Usa las herramientas proporcionadas para buscar información antes de responder. "
        "Si el usuario pide que le recuerdes algo ('agenda eso', 'recuérdamelo'), usa la herramienta crear_recordatorio "
        "infiriendo el trámite desde el historial de la conversación. "
        "Responde de forma amable y directa al usuario sin mostrar tus pasos de pensamiento."
    )

    messages = [{"role": "system", "content": system_prompt}]
    # Cargar memoria a corto plazo (clave para "recuérdamelo")
    for m in history[-10:]:
        messages.append({"role": m.get("role", "user"), "content": m.get("content", "")})
    messages.append({"role": "user", "content": user_message})

    trace = []

    for step in range(max_steps):
        response = client.chat.completions.create(
            model=model,
            messages=messages,
            tools=TOOLS,
            tool_choice="auto",
            temperature=0.2
        )
        
        response_message = response.choices[0].message
        
        # Si el modelo decide usar una herramienta (Action)
        if response_message.tool_calls:
            messages.append(response_message) # Agregar la petición de tool_call al historial
            
            for tool_call in response_message.tool_calls:
                function_name = tool_call.function.name
                arguments = json.loads(tool_call.function.arguments)
                
                # LOG: Mostrar ejecución de herramienta
                trace.append({
                    "type": "tool_call", 
                    "function": function_name, 
                    "arguments": arguments
                })

                if function_name == "search_docs":
                    # 1. Aplicar MQR
                    variantes_mqr = generar_mqr(arguments["query"], client, model)
                    trace.append({"type": "mqr_generated", "queries": variantes_mqr})
                    
                    # 2. Búsqueda Semántica
                    observation = busqueda_semantica(variantes_mqr)
                    
                elif function_name == "crear_recordatorio":
                    # Simulación de agendar gracias a la Memoria a corto plazo
                    tramite = arguments.get("tramite", "Trámite desconocido")
                    fecha = arguments.get("fecha_hora", "Sin fecha")
                    observation = f"✅ Éxito: Recordatorio guardado en sistema para '{tramite}' ({fecha})."

                else:
                    observation = "Herramienta desconocida."

                # LOG: Mostrar resultado (Observation)
                trace.append({"type": "tool_message", "result": observation})
                
                # Devolver el resultado de la herramienta al modelo
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "name": function_name,
                    "content": observation
                })
                
            # Continuar el bucle para que el modelo lea la 'Observation' y genere la 'Final Answer'
            continue

        # Si no hay tool_calls, significa que es la respuesta final para el usuario
        final_answer = response_message.content
        trace.append({"type": "final_answer", "content": final_answer})
        
        return {"response": final_answer, "trace": trace}

    return {"response": "Lo siento, me tomó demasiados pasos procesar tu solicitud.", "trace": trace}