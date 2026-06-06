import os
import json
# pyrefly: ignore [missing-import]
from groq import Groq
from app.services.rag_service import RAGService
from app.services.agent import SYSTEM_PROMPT_SCENARIO_DESIGNER

client = Groq(api_key=os.getenv("GROQ_API_KEY"))
rag = RAGService()

TOPIC_MAP = {
    1: "texto_plano",
    2: "http_phishing",
    3: "port_scan",
    4: "dos",
    5: "malware_c2"
}

def generate_scenario(nivel_id: int):
    topic = TOPIC_MAP.get(nivel_id, "general")
    
    # 1. Recuperar conocimiento del RAG sobre el tópico
    contexto_rag = rag.get_knowledge(f"Análisis técnico de {topic}", topic=topic)
    
    # 2. Llamar al LLM para diseñar el escenario
    prompt = SYSTEM_PROMPT_SCENARIO_DESIGNER.format(
        contexto_rag=contexto_rag if contexto_rag else "Información general de seguridad",
        nivel_id=nivel_id,
        topico=topic
    )
    
    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "system", "content": prompt}],
        temperature=0.8, # Temperatura alta para que los escenarios varíen
        response_format={"type": "json_object"}
    )
    
    return json.loads(response.choices[0].message.content)