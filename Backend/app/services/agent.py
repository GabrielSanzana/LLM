import os
import re
import json
from typing import Any, Dict, List, Optional

# pyrefly: ignore [missing-import]
from groq import Groq

from app.services.rag_service import RAGService

client = Groq(api_key=os.getenv("GROQ_API_KEY"))
rag: Optional[RAGService] = None

ALLOWED_TOPICS = {
    "port_scan",
    "texto_plano",
    "pop3",
    "malware_c2",
    "dos",
    "http_phishing",
    "general",
}

# =========================
# PROMPTS BASE
# =========================

SYSTEM_PROMPT_GENERAL_ROUTER = """
Eres el Router de Intenciones y Evaluador Cognitivo de NetTutor.
Tu tarea es analizar el mensaje actual del usuario en el Chat General, clasificar su intención y evaluar su nivel de conocimiento.

Si el usuario está respondiendo a una pregunta de evaluación o de diagnóstico técnico, debes analizar rigurosamente si demuestra un entendimiento correcto y suficiente del tema actual, o si por el contrario tiene dudas, conceptos erróneos o indica no saber.

Debes responder SOLO en un objeto JSON válido.

ESQUEMA JSON OBLIGATORIO:
{
  "intent": "ask_concept|answer_diagnostic|request_analysis|troubleshoot|general_chat",
  "topic": "port_scan|texto_plano|pop3|malware_c2|dos|http_phishing|general",
  "needs_rag": true,
  "summary": "Breve resumen de lo que el usuario quiere lograr o responde",
  "diagnostic_evaluation": "known|unknown",  # Pon "known" si demuestra entender o responder bien la pregunta técnica de evaluación actual. Pon "unknown" si no sabe, se equivoca gravemente o responde de forma evasiva.
  "user_demonstrates_understanding": true  # true si demuestra haber comprendido el concepto que se le está enseñando o valida correctamente la pregunta de control, false en caso contrario.
}
"""

SYSTEM_PROMPT_GENERAL_TUTOR = """
Eres un Tutor Técnico Directivo en Ciberseguridad.
A diferencia de un bot de chat común, tu objetivo es dar respuestas DIRECTAS, CLARAS y RESOLUTIVAS, pero manteniendo en todo momento tu rol de TUTOR experto guiando a un estudiante.

Cuentas con:
1. INTENCIÓN DEL USUARIO: {intent_json}
2. INFORMACIÓN DEL PCAP: Datos de la captura subida.
3. CONTEXTO TÉCNICO RAG: Documentación técnica.

REGLAS:
- Ve directo al grano. Usa un tono profesional y resolutivo.
- Si el usuario pide un concepto, defínelo claramente.
- Si pide analizar el PCAP, dale el análisis directo sin preámbulos.
- NO uses el método socrático. Si el usuario se equivoca, simplemente dale la respuesta correcta.
- Al final de tu mensaje, SIEMPRE ofrece 2 o 3 opciones cortas y numeradas para que el usuario elija hacia dónde dirigir la conversación (ej. "1. Profundizar en X", "2. Analizar el tráfico Y").
"""

SYSTEM_PROMPT_ANALYSIS_ROUTER = """
Eres el Router de Intenciones para el Chat de Análisis Forense de PCAP.
Tu tarea es analizar la consulta del usuario sobre el archivo PCAP subido y clasificarla.

Debes responder SOLO en JSON válido.

ESQUEMA JSON OBLIGATORIO:
{
  "intent": "ask_packet_detail|ask_mitigation|explain_concept|general_chat",
  "packet_id_referenced": "Número de paquete si lo menciona, o null",
  "needs_rag": true,
  "summary": "Breve resumen de lo que el usuario quiere saber sobre la captura"
}
"""

SYSTEM_PROMPT_PCAP_ANALYSIS = """
Actúa como un Tutor Proactivo de Ciberseguridad. Tu objetivo no es solo resumir, sino DIRIGIR el aprendizaje del usuario basándote en este archivo .pcap:

RESUMEN TÉCNICO DE SCAPY:
{pcap_summary}

INSTRUCCIONES DE FLUJO (Bifurcaciones Lógicas):
Analiza los datos y toma decisiones basadas en estas reglas:

1. BIFURCACIÓN DE SEGURIDAD:
   - SI detectas protocolos sin cifrar (HTTP, FTP, Telnet) o mDNS exponiendo nombres, inicia con una ALERTA proactiva.
   - SI todo es HTTPS/TLS, felicita al usuario por tener tráfico cifrado y explica por qué es importante.

2. BIFURCACIÓN DE PROTOCOLO:
   - SI hay handshakes TCP, elige un flujo y explica el proceso SYN-ACK.
   - SI hay mucho tráfico UDP/DNS, explica por qué este protocolo es "sin conexión".

3. BIFURCACIÓN DE IDENTIDAD:
   - SI ves IPs externas (Internet), identifica a qué servicio podrían pertenecer (Google, CDNs, etc.).
   - SI es solo tráfico local, explica la función del Router como Gateway.

FORMATO DE RESPUESTA (Estructura Directiva):
- Saludo de Tutor: "He analizado tu red y esto es lo que DEBES saber..."
- El Hallazgo Maestro: (Aplica las bifurcaciones arriba mencionadas).
- El "Por qué": Explica la lógica técnica detrás de tu conclusión.
- CIERRE DIRECTIVO: No esperes a que el usuario piense qué preguntar. Presenta 3 opciones numeradas de "Siguientes Pasos" (que representen nuevas intenciones de aprendizaje).

REGLA DE ORO: No seas pasivo. Tú eres el experto guiando a un novato.
"""

SYSTEM_PROMPT_ROUTER = """
Eres el Router Cognitivo de NetTutor.

Tu tarea es analizar la intención del usuario, su avance dentro del simulador, el historial breve y la memoria resumida.
Debes decidir:
1) qué quiere hacer el usuario,
2) qué tan avanzado está,
3) a qué tópico pertenece,
4) si necesita RAG,
5) cuál es la siguiente bifurcación pedagógica.

Debes responder SOLO en JSON válido.

OBJETIVO:
- Ser flexible y más potente que un clasificador rígido.
- Detectar intención, subintención y progreso.
- Inferir referencia a paquetes, observaciones previas o conceptos implícitos.
- Actualizar memoria resumida sin repetir todo el historial.

REGLAS:
- Si el usuario usa pronombres como "este", "ese", "eso", "el anterior", "el que tiene SYN", usa el historial y la memoria para inferir a qué se refiere.
- Si no puedes inferir un paquete o evento concreto, deja packet_id en null.
- Si la consulta está fuera del simulador o fuera de los 5 niveles, marca topic = "general".
- No inventes datos técnicos.
- No expliques; solo clasifica y resume.
- No uses markdown.
- No agregues texto fuera del JSON.
- Si el usuario identifica o acierta la vulnerabilidad principal del escenario, debes marcar "completed": true en progress.

ESQUEMA JSON OBLIGATORIO:
{
  "intent": "identify_attack|describe_observation|ask_concept|request_mitigation|compare_protocols|confirm_understanding|advance_level|general",
  "branch": "novice|intermediate|advanced|unclear|off_topic",
  "topic": "port_scan|texto_plano|pop3|malware_c2|dos|http_phishing|general",
  "question_focus": "resumen corto de lo que realmente pregunta",
  "packet_id": 123,
  "needs_rag": true,
  "progress": {
    "level": 1,
    "stage": "start|diagnosis|explanation|mitigation|review",
    "completed": false
  },
  "memory_update": "resumen corto y útil de lo que cambió en esta interacción",
  "confidence": 0.0
}
"""

SYSTEM_PROMPT_SIM_TUTOR = """
Eres un Tutor Proactivo de Ciberseguridad en un chat interactivo.

Tu misión es responder usando:
1) la intención estructurada del router,
2) la memoria resumida,
3) el contexto del PCAP,
4) el contexto técnico recuperado del RAG.

REGLAS ABSOLUTAS:
1. RESPUESTAS CORTAS Y CONVERSACIONALES: Eres un tutor en un chat, NO un generador de reportes. Tus respuestas deben ser breves, directas y en lenguaje natural (ej. "No es correcto, deberías enfocarte en la columna de información."). NO uses encabezados (como "Hallazgo central", "Explicación técnica"), NO uses viñetas largas, y evita párrafos extensos.

2. CONDICIÓN DE VICTORIA: Si el JSON del router indica `"completed": true` (el usuario identificó la vulnerabilidad), tu respuesta DEBE COMENZAR EXACTAMENTE CON LA FRASE: "Encontraste la vulnerabilidad, nivel completado." y a continuación, en el mismo mensaje, explica brevemente cómo resolver o mitigar esta vulnerabilidad. ESTÁ ESTRICTAMENTE PROHIBIDO hacer nuevas preguntas o incluir la sección de "Siguientes pasos" en este caso.

3. EN CUALQUIER OTRO CASO: Guía al alumno paso a paso usando el método socrático de forma muy concisa. Termina tu mensaje con UNA sola pregunta corta o sugerencia puntual que invite al alumno a pensar o investigar el siguiente paso. NO des 3 opciones largas de siguientes pasos.

4. REGLA ANTI-SPOILERS: Mientras `"completed": false`, TIENES ESTRICTAMENTE PROHIBIDO mencionar o confirmar explícitamente el nombre del ataque o vulnerabilidad (ej. "phishing HTTP", "texto plano", "port scan", "DDOS", "malware"). Refiérete al problema como "anomalía", "tráfico sospechoso", "comportamiento inusual", etc. Deja que el estudiante lo deduzca y lo nombre.
"""

SYSTEM_PROMPT_SCENARIO_DESIGNER = """
Eres el Arquitecto de Simulaciones de NetTutor.

Genera escenarios de ciberseguridad realistas basados en el tópico, el nivel y el contexto técnico recuperado del RAG.

Debes producir SOLO JSON válido.

REGLAS ABSOLUTAS PARA EL PCAP:
1. REALISMO Y RUIDO DE FONDO: Un archivo PCAP real NUNCA tiene solo paquetes maliciosos. La gran mayoría del tráfico debe ser "ruido de fondo" normal y benigno (ej. peticiones ARP, consultas DNS a dominios comunes, tráfico TLS/HTTPS normal, handshakes TCP regulares, etc.).
2. CAMUFLAJE: La vulnerabilidad o ataque (definida por el tópico y el contexto del RAG) debe estar "escondida" y dispersa lógicamente entre el tráfico normal.
3. CANTIDAD: Debes generar EXACTAMENTE 30 paquetes en total. (La mayoría deben ser tráfico normal/benigno).
4. El escenario debe ser diferente cada vez y usar detalles técnicos coherentes con el contexto recuperado.
5. Usa direcciones IP de origen y destino variadas para simular una red real, pero mantén consistencia en la dirección IP de la víctima y el atacante durante el flujo malicioso.
6. INSTRUCCIÓN ESPECÍFICA DE ESTE NIVEL: {prompt_especifico}
7. La finalidad es entrenamiento pedagógico, no explotación real.
8. REGLA ANTI-SPOILERS: En `incidente_reportado`, `objetivo_aprendizaje`, `mensaje_inicial` y `pistas_sistema`, ESTÁ ESTRICTAMENTE PROHIBIDO mencionar el nombre de la vulnerabilidad o ataque (ej. no uses palabras como "texto plano", "DDOS", "phishing", "malware", "port scan"). Solo describe los SÍNTOMAS percibidos por los usuarios o el sistema (ej. "lentitud anómala", "acceso no autorizado reportado", "tráfico inusual de red"). El estudiante DEBE descubrir qué pasa.

ENTRADA:
- tópico
- nivel
- contexto técnico RAG

SALIDA JSON:
{
  "escenario": {
    "empresa_ficticia": "...",
    "descripcion_entorno": "...",
    "incidente_reportado": "...",
    "objetivo_aprendizaje": "..."
  },
  "guia_tutor": {
    "mensaje_inicial": "...",
    "pistas_sistema": ["...", "...", "..."]
  },
  "paquetes_pcap": [
    {
      "no": 1,
      "time": "0.0000",
      "src": "IP_ORIGEN",
      "dst": "IP_DESTINO",
      "pr": "PROTOCOLO",
      "len": "LONGITUD",
      "info": "..."
    }
  ],
  "metadata_simulacion": {
    "dificultad": "Nivel X",
    "topico": "..."
  }
}
"""

# =========================
# UTILIDADES
# =========================

def _clip_text(text: str, max_len: int = 2500) -> str:
    if not text:
        return ""
    if len(text) <= max_len:
        return text
    return text[:max_len] + "\n...[TRUNCADO]..."


def _pretty(obj: Any, max_len: int = 2500) -> str:
    try:
        if isinstance(obj, (dict, list)):
            txt = json.dumps(obj, ensure_ascii=False, indent=2)
        else:
            txt = str(obj)
        return _clip_text(txt, max_len=max_len)
    except Exception:
        return _clip_text(str(obj), max_len=max_len)


def init_rag_service():
    global rag
    if rag is None:
        rag = RAGService()
    return rag


def get_rag_service():
    global rag
    if rag is None:
        rag = RAGService()
    return rag


def normalize_topic(raw: str) -> str:
    if not raw:
        return "general"

    txt = raw.strip().lower()
    txt = re.sub(r"[^a-z_]", "", txt)

    if txt in ALLOWED_TOPICS:
        return txt

    for topic in ALLOWED_TOPICS:
        if topic != "general" and topic in txt:
            return topic

    return "general"


def safe_json_loads(text: str) -> Dict[str, Any]:
    if not text:
        return {}

    text = text.strip()

    try:
        return json.loads(text)
    except Exception:
        pass

    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            return json.loads(text[start:end + 1])
        except Exception:
            return {}

    return {}


def normalize_router_output(data: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(data, dict):
        data = {}

    progress = data.get("progress", {})
    if not isinstance(progress, dict):
        progress = {}

    normalized = {
        "intent": data.get("intent", "general"),
        "branch": data.get("branch", "unclear"),
        "topic": normalize_topic(data.get("topic", "general")),
        "question_focus": str(data.get("question_focus", "")).strip(),
        "packet_id": data.get("packet_id", None),
        "needs_rag": bool(data.get("needs_rag", True)),
        "progress": {
            "level": int(progress.get("level", 0) or 0),
            "stage": progress.get("stage", "start"),
            "completed": bool(progress.get("completed", False)),
        },
        "memory_update": str(data.get("memory_update", "")).strip(),
        "confidence": float(data.get("confidence", 0.0) or 0.0),
    }

    pid = normalized["packet_id"]
    if pid in ("", "null", "None", None):
        normalized["packet_id"] = None
    else:
        try:
            normalized["packet_id"] = int(pid)
        except Exception:
            normalized["packet_id"] = None

    return normalized


def update_long_memory(memory_summary: str, router_json: Dict[str, Any]) -> str:
    current = (memory_summary or "").strip()
    update = router_json.get("memory_update", "").strip()

    if not update:
        return current

    if not current:
        return update

    merged = current + " | " + update
    return merged[-1200:]

def route_intention(
    user_message: str,
    history: Optional[List[Dict[str, str]]] = None,
    memory_summary: str = "",
    pcap_data: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    history = history or []

    pcap_context = f"PCAP: {json.dumps(pcap_data, ensure_ascii=False)}" if pcap_data else "PCAP: null"

    messages = [
        {
            "role": "system",
            "content": SYSTEM_PROMPT_ROUTER,
        },
        {
            "role": "user",
            "content": f"""
MEMORIA RESUMIDA:
{memory_summary if memory_summary else "vacía"}

HISTORIAL BREVE:
{json.dumps(history, ensure_ascii=False)}

DATOS DE PCAP:
{pcap_context}

MENSAJE ACTUAL:
{user_message}

Devuelve SOLO JSON.
""".strip(),
        },
    ]

    response = client.chat.completions.create(
        model="openai/gpt-oss-120b",
        messages=messages,
        temperature=0.1,
        response_format={"type": "json_object"},
    )

    raw = response.choices[0].message.content
    parsed = safe_json_loads(raw)
    normalized = normalize_router_output(parsed)

    return normalized

# =========================
# TUTOR SIMULADOR
# =========================

def get_simulator_response(
    user_message: str,
    pcap_data: Optional[Dict[str, Any]] = None,
    history: Optional[List[Dict[str, str]]] = None,
    memory_summary: str = "",
):
    global rag

    if rag is None:
        raise RuntimeError("RAG no inicializado todavía")

    router_json = route_intention(
        user_message=user_message,
        history=history,
        memory_summary=memory_summary,
        pcap_data=pcap_data,
    )

    topic = router_json["topic"]
    intent = router_json["intent"]
    branch = router_json["branch"]
    level = router_json["progress"]["level"]
    stage = router_json["progress"]["stage"]

    rag_context = ""
    if router_json.get("needs_rag", True):
        rag_context = rag.get_knowledge(user_message, topic=topic)

    # recorte para evitar prompts gigantes
    rag_context = _clip_text(rag_context, 3000)

    pcap_context = f"Datos de Scapy: {pcap_data}" if pcap_data else "No hay archivo subido aún."

    full_system_prompt = f"""{SYSTEM_PROMPT_SIM_TUTOR}

JSON DEL ROUTER:
{json.dumps(router_json, ensure_ascii=False, indent=2)}

MEMORIA RESUMIDA:
{memory_summary if memory_summary else "vacía"}

CONTEXTO TÉCNICO (RAG):
{rag_context if rag_context else "No se recuperó contexto técnico adicional."}

DATOS DE LA CAPTURA (SCAPY):
{pcap_context}
"""

    messages_to_send = [{"role": "system", "content": full_system_prompt}]
    if history:
        messages_to_send.extend(history)
    messages_to_send.append({"role": "user", "content": user_message})

    final_response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=messages_to_send,
        temperature=0.2,
    )

    answer = final_response.choices[0].message.content

    return {
        "response": answer,
        "router": router_json,
        "memory_next": update_long_memory(memory_summary, router_json),
        "meta": {
            "topic": topic,
            "intent": intent,
            "branch": branch,
            "level": level,
            "stage": stage,
        },
    }

# =========================
# CHAT GENERAL
# =========================

def get_tutor_response(
    user_message: str,
    pcap_data: Optional[Dict[str, Any]] = None,
    history: Optional[List[Dict[str, str]]] = None,
    id_sesion: Optional[int] = None,
):
    global rag

    if rag is None:
        raise RuntimeError("RAG no inicializado todavía")

    from app.services.chat_service import obtener_progreso_usuario, guardar_progreso_usuario

    # 1. Obtener progreso del usuario (persistencia)
    if id_sesion is not None:
        progreso = obtener_progreso_usuario(id_sesion)
    else:
        # Fallback local para desarrollo o invitados
        progreso = {
            "stage": "global_diagnostic",
            "diagnostic_step": 0,
            "completed_topics": [],
            "curriculum": [],
            "current_topic": None,
            "knowledge_level": {
                "texto_plano": "unknown",
                "http_phishing": "unknown",
                "port_scan": "unknown",
                "dos": "unknown",
                "malware_c2": "unknown"
            }
        }

    if "topic_messages_count" not in progreso:
        progreso["topic_messages_count"] = 0

    CURRICULUM_TOPICS = ["texto_plano", "http_phishing", "port_scan", "dos", "malware_c2"]
    
    TOPIC_DISPLAY_NAMES = {
        "texto_plano": "Texto Plano (Telnet/FTP sin cifrar)",
        "http_phishing": "HTTP y Cabeceras de Phishing",
        "port_scan": "Escaneo de Puertos (Tráfico SYN)",
        "dos": "Denegación de Servicio (DoS/Inundaciones)",
        "malware_c2": "Malware y Canales de Comando y Control (C2)"
    }

    # 2. Router de intención con gpt-oss-120b
    mensaje_normalizado = user_message.lower().strip()
    solicita_test = (
        mensaje_normalizado == "/iniciar_mini_test" or
        "iniciar_mini_test" in mensaje_normalizado or
        "iniciar mini-test" in mensaje_normalizado or
        "iniciar mini test" in mensaje_normalizado or
        "comenzar mini-test" in mensaje_normalizado or
        "comenzar mini test" in mensaje_normalizado or
        "realizar el mini-test" in mensaje_normalizado or
        "realizar el mini test" in mensaje_normalizado or
        "comenzar_mini_test" in mensaje_normalizado
    )

    if solicita_test:
        router_json = {
            "intent": "general_chat",
            "topic": progreso.get("current_topic", "general"),
            "needs_rag": False,
            "summary": "El usuario solicita iniciar el mini-test",
            "diagnostic_evaluation": "unknown",
            "user_demonstrates_understanding": False
        }
        diagnostic_eval = "unknown"
        user_understands = False
        topic = progreso.get("current_topic", "general")
    else:
        router_messages = [
            {"role": "system", "content": SYSTEM_PROMPT_GENERAL_ROUTER},
            {"role": "user", "content": f"MENSAJE ACTUAL:\n{user_message}"}
        ]
        if history:
            historial_breve = history[-3:] if len(history) >= 3 else history
            router_messages.insert(1, {"role": "system", "content": f"HISTORIAL RECIENTE:\n{json.dumps(historial_breve, ensure_ascii=False)}"})

        intent_response = client.chat.completions.create(
            model="openai/gpt-oss-120b",
            messages=router_messages,
            temperature=0.1,
            response_format={"type": "json_object"}
        )

        raw_router = intent_response.choices[0].message.content.strip()
        router_json = safe_json_loads(raw_router)
        
        diagnostic_eval = router_json.get("diagnostic_evaluation", "unknown")
        user_understands = router_json.get("user_demonstrates_understanding", False)

        raw_topic = router_json.get("topic", "general")
        topic = normalize_topic(raw_topic)

    # 3. Máquina de Estados Pedagógica (Ruta Adaptativa)
    DIAGNOSTIC_QUESTIONS = [
        "¿Qué riesgos de seguridad corres si utilizas protocolos sin cifrar como Telnet o FTP para transmitir credenciales en una red, y cómo podrías detectarlo en un análisis de tráfico?",
        "¿Cómo podrías identificar una solicitud maliciosa o un posible ataque de Phishing inspeccionando las cabeceras HTTP de una petición (por ejemplo, el Host, User-Agent o Referer)?",
        "¿Qué patrón de paquetes o banderas (flags) de TCP buscarías en Wireshark/Scapy para confirmar que un atacante está realizando un escaneo de puertos SYN silencioso (Half-Open Scan)?",
        "¿Qué características volumétricas y de flujo (como cantidad de paquetes por segundo, IPs de origen y puertos) diferencian el tráfico normal de un ataque de Denegación de Servicio (DoS) por inundación TCP SYN o UDP?",
        "¿Qué es una conexión de tipo 'Beacon' o baliza en malware, por qué los atacantes la usan para comunicarse con servidores de Comando y Control (C2), y cómo se detecta analizando la frecuencia o intervalos del tráfico?"
    ]

    just_completed_topic = None
    stage_instructions = ""

    # Determinar si es el primer mensaje de la sesión (cuando el tutor aún no ha hecho ninguna pregunta)
    has_assistant_messages = any(h.get("role") == "assistant" for h in (history or []))
    is_first_message = not has_assistant_messages

    if progreso["stage"] == "global_diagnostic":
        step = progreso["diagnostic_step"]
        
        if not is_first_message:
            # Evaluamos la respuesta a la pregunta formulada en el paso anterior (step)
            evaluated_topic = CURRICULUM_TOPICS[step]
            if diagnostic_eval == "known" or user_understands:
                progreso["knowledge_level"][evaluated_topic] = "known"
                if evaluated_topic not in progreso["completed_topics"]:
                    progreso["completed_topics"].append(evaluated_topic)
            else:
                progreso["knowledge_level"][evaluated_topic] = "unknown"
                if evaluated_topic not in progreso["curriculum"]:
                    progreso["curriculum"].append(evaluated_topic)
            
            # Avanzar paso
            progreso["diagnostic_step"] += 1
            step = progreso["diagnostic_step"]

        if step < 5:
            # Aún quedan preguntas de diagnóstico
            if is_first_message:
                stage_instructions = f"""
                Estás en la Bienvenida del Diagnóstico Global Inicial.
                Tu tarea es dar una cordial bienvenida al estudiante a NetTutor y explicar que realizarás un rápido test de 5 preguntas (una por tema) para evaluar qué sabe y diseñar su ruta de aprendizaje personalizada.
                
                Formula explícita y textualmente la primera pregunta:
                "**Pregunta 1: {TOPIC_DISPLAY_NAMES[CURRICULUM_TOPICS[0]]}**
                {DIAGNOSTIC_QUESTIONS[0]}"
                
                No des explicaciones adicionales ni retroalimentación técnica aún. Solo dale la bienvenida y formula la pregunta.
                """
            else:
                prev_topic_display = TOPIC_DISPLAY_NAMES[CURRICULUM_TOPICS[step - 1]]
                stage_instructions = f"""
                Estás en la prueba de Diagnóstico Global Inicial. Estás evaluando la pregunta {step} de 5.
                
                REGLAS ABSOLUTAS DE ESTA ETAPA (DIAGNÓSTICO):
                1. Da un acuse de recibo de la respuesta anterior extremadamente breve, conciso y profesional, en una sola línea o frase corta (ej: "Entendido.", "Listo, respuesta registrada.", "Perfecto, anotado.").
                2. TIENES ESTRICTAMENTE PROHIBIDO dar explicaciones técnicas, respuestas correctas, lecciones o teoría en este punto. No expliques el tema anterior bajo ninguna circunstancia. Tu respuesta debe limitarse exclusivamente a registrar la respuesta anterior y formular la siguiente pregunta.
                3. Presenta textualmente la siguiente pregunta diagnóstica:
                   "**Pregunta {step + 1}: {TOPIC_DISPLAY_NAMES[CURRICULUM_TOPICS[step]]}**
                   {DIAGNOSTIC_QUESTIONS[step]}"
                """
        else:
            # Diagnóstico terminado. Construir ruta personalizada.
            # Los temas que no domina ya están en progreso["curriculum"].
            # Si el currículum está vacío, el usuario sabe todo.
            if not progreso["curriculum"]:
                progreso["stage"] = "completed_all"
                progreso["current_topic"] = None
                stage_instructions = """
                El estudiante ha respondido correctamente a todas las preguntas del diagnóstico inicial.
                
                1. Felicítalo de forma entusiasta por demostrar un excelente nivel técnico en ciberseguridad.
                2. Explícale que su ruta adaptativa está completa de inmediato, y recomiéndale ir directamente al Simulador de Ataques y al Análisis PCAP para poner a prueba sus destrezas prácticas.
                3. DEBES incluir las marcas interactivas al final de tu mensaje:
                   `[RECOMENDACION:SIMULADOR:Nivel_1]` `[RECOMENDACION:SIMULADOR:Nivel_2]` `[RECOMENDACION:SIMULADOR:Nivel_3]` `[RECOMENDACION:SIMULADOR:Nivel_4]` `[RECOMENDACION:SIMULADOR:Nivel_5]` `[RECOMENDACION:PCAP]`
                """
            else:
                progreso["stage"] = "teaching"
                progreso["current_topic"] = progreso["curriculum"][0]
                progreso["topic_messages_count"] = 0
                
                # Explicar resultado y comenzar lección del primer tema
                display_active = TOPIC_DISPLAY_NAMES[progreso["current_topic"]]
                completed_names = [TOPIC_DISPLAY_NAMES[t] for t in progreso["completed_topics"]]
                completed_str = ", ".join(completed_names) if completed_names else "ninguno"
                
                stage_instructions = f"""
                ¡El diagnóstico global ha finalizado!
                
                REGLAS ABSOLUTAS DE ESTA ETAPA (FIN DE DIAGNÓSTICO):
                1. Informa al estudiante de forma ejecutiva sobre sus resultados: dominó los temas: **{completed_str}** (los cuales se marcan como aprobados ✓ en su panel izquierdo), pero que nos enfocaremos en sus áreas de oportunidad.
                2. Inicia INMEDIATAMENTE y de forma proactiva con la primera lección teórica del tema pendiente: **{display_active}**.
                3. Explica los conceptos clave de **{display_active}** de manera atractiva, estructurada y muy clara, apoyándote en el contexto del RAG.
                4. Haz una pregunta corta para iniciar la conversación sobre este tema activo.
                5. TIENES ESTRICTAMENTE PROHIBIDO despedirse, cerrar la conversación, recomendar ir al simulador de ataques o al análisis PCAP, o sugerir que la tutoría termina aquí. Tu deber como tutor es enganchar al estudiante activamente en su primera lección.
                6. TIENES ESTRICTAMENTE PROHIBIDO incluir marcas de recomendación como `[RECOMENDACION:...]` en esta respuesta.
                """

    elif progreso["stage"] == "teaching":
        progreso["topic_messages_count"] += 1
        current_topic = progreso["current_topic"]
        display_active = TOPIC_DISPLAY_NAMES[current_topic]
        
        # El mini-test ya no se inicia automáticamente por número de mensajes para no interrumpir al estudiante.
        # Se inicia determinísticamente cuando se solicita_test (ej. al presionar el botón)
        if solicita_test:
            progreso["stage"] = "mini_test"
            progreso["test_step"] = 0
            
            # Definir Mini-Tests de 3 preguntas rápidas
            MINI_TEST_QUESTIONS = {
                "texto_plano": [
                    "¿Por qué protocolos como FTP y Telnet se consideran inseguros y qué herramienta de sniffing se usa comúnmente para capturar sus credenciales?",
                    "Si estás analizando un paquete en texto plano en Wireshark, ¿en qué capa del modelo OSI/TCP-IP se encuentran expuestos los datos legibles del usuario?",
                    "¿Qué protocolo seguro cifrado deberías usar para reemplazar a Telnet y cuál para reemplazar a FTP?"
                ],
                "http_phishing": [
                    "Si haces clic en un enlace de phishing, ¿qué cabecera HTTP (como Host o Referer) se revelará en la petición y cómo ayuda a detectar la suplantación?",
                    "¿Qué campo de cabecera HTTP describe el navegador o agente de usuario que realiza la petición y suele ser falsificado por atacantes?",
                    "¿Cómo ayuda el cifrado y los certificados de HTTPS a mitigar que un atacante suplante por completo la identidad de un sitio web legítimo?"
                ],
                "port_scan": [
                    "¿Qué banderas (flags) TCP se envían de origen y se reciben de respuesta en un escaneo SYN (Half-Open Scan) cuando un puerto está abierto?",
                    "¿Qué respuesta (flag) TCP envía el host víctima si el puerto escaneado está cerrado?",
                    "¿Por qué un escaneo SYN se considera más silencioso y evasivo que un escaneo de conexión completa (Full Connect Scan)?"
                ],
                "dos": [
                    "¿Qué diferencia técnica principal hay entre un ataque DoS (Denegación de Servicio) y un ataque DDoS (Distribuido)?",
                    "¿Cómo satura un ataque SYN Flood la memoria del servidor víctima y qué flag TCP nunca envía el atacante para completar la conexión?",
                    "¿Menciona una medida de mitigación técnica en red para proteger a un servidor contra inundaciones masivas de tráfico SYN?"
                ],
                "malware_c2": [
                    "¿Qué es un 'C2 Server' (servidor de Comando y Control) y qué función cumple para un malware infiltrado?",
                    "¿Qué es el 'beaconing' o balizamiento en comunicaciones de malware y por qué los atacantes usan intervalos de tiempo con 'jitter' (aleatoriedad)?",
                    "Si una IP interna realiza conexiones DNS constantes a dominios extraños generados algorítmicamente (DGA), ¿qué fase del ataque se está presenciando?"
                ]
            }
            q_list = MINI_TEST_QUESTIONS.get(current_topic, ["¿Cómo mitigarías esta vulnerabilidad?"] * 3)
            
            stage_instructions = f"""
            ¡Comienza el Mini-Test de 3 preguntas para el tema '{display_active}'!
            
            REGLAS ABSOLUTAS DE ESTA ETAPA (MINI-TEST):
            1. Explica de forma directa que ha llegado el momento del Mini-Test para evaluar su comprensión de '{display_active}'.
            2. Presenta de forma clara, explícita y textualmente la **Pregunta 1 de 3** de este Mini-Test para '{display_active}':
               "**Pregunta 1 de 3:** {q_list[0]}"
            3. Indícale claramente al estudiante que debe responder correctamente 3 preguntas consecutivas para poder aprobar el tema.
            4. TIENES ESTRICTAMENTE PROHIBIDO incluir marcas de recomendación como `[RECOMENDACION:...]` en esta respuesta.
            5. TIENES ESTRICTAMENTE PROHIBIDO sugerir cambiar de tema o avanzar a otros temas como Phishing o DoS.
            """
        else:
            stage_instructions = f"""
            Estás enseñando el tema activo: '{display_active}'.
            
            REGLAS ABSOLUTAS DE ESTA ETAPA (ENSEÑANZA):
            1. Continúa explicando de forma clara, directa y práctica el concepto, basándote en la información del RAG.
            2. Corrige cualquier duda técnica o error que haya mostrado en su mensaje actual.
            3. TIENES ESTRICTAMENTE PROHIBIDO incluir marcas de recomendación como `[RECOMENDACION:SIMULADOR:...]` o `[RECOMENDACION:PCAP]`. Las recomendaciones están estrictamente prohibidas en la fase de enseñanza.
            4. TIENES ESTRICTAMENTE PROHIBIDO sugerir cambiar de tema o avanzar a otros temas (como Phishing). Concéntrate exclusivamente en '{display_active}'.
            5. Adviértele de forma amigable que cuando se sienta listo, puede iniciar el **Mini-Test de 3 preguntas rápidas** presionando el botón 'Iniciar Mini-Test' en la interfaz o pidiéndote expresamente que comience el test.
            6. Termina preguntándole si tiene alguna duda técnica sobre el concepto o si está listo para comenzar el **Mini-Test**.
            """

    elif progreso["stage"] == "mini_test":
        current_topic = progreso["current_topic"]
        display_active = TOPIC_DISPLAY_NAMES[current_topic]
        step = progreso["test_step"]
        
        # Definir Mini-Tests de 3 preguntas rápidas
        MINI_TEST_QUESTIONS = {
            "texto_plano": [
                "¿Por qué protocolos como FTP y Telnet se consideran inseguros y qué herramienta de sniffing se usa comúnmente para capturar sus credenciales?",
                "Si estás analizando un paquete en texto plano en Wireshark, ¿en qué capa del modelo OSI/TCP-IP se encuentran expuestos los datos legibles del usuario?",
                "¿Qué protocolo seguro cifrado deberías usar para reemplazar a Telnet y cuál para reemplazar a FTP?"
            ],
            "http_phishing": [
                "Si haces clic en un enlace de phishing, ¿qué cabecera HTTP (como Host o Referer) se revelará en la petición y cómo ayuda a detectar la suplantación?",
                "¿Qué campo de cabecera HTTP describe el navegador o agente de usuario que realiza la petición y suele ser falsificado por atacantes?",
                "¿Cómo ayuda el cifrado y los certificados de HTTPS a mitigar que un atacante suplante por completo la identidad de un sitio web legítimo?"
            ],
            "port_scan": [
                "¿Qué banderas (flags) TCP se envían de origen y se reciben de respuesta en un escaneo SYN (Half-Open Scan) cuando un puerto está abierto?",
                "¿Qué respuesta (flag) TCP envía el host víctima si el puerto escaneado está cerrado?",
                "¿Por qué un escaneo SYN se considera más silencioso y evasivo que un escaneo de conexión completa (Full Connect Scan)?"
            ],
            "dos": [
                "¿Qué diferencia técnica principal hay entre un ataque DoS (Denegación de Servicio) y un ataque DDoS (Distribuido)?",
                "¿Cómo satura un ataque SYN Flood la memoria del servidor víctima y qué flag TCP nunca envía el atacante para completar la conexión?",
                "¿Menciona una medida de mitigación técnica en red para proteger a un servidor contra inundaciones masivas de tráfico SYN?"
            ],
            "malware_c2": [
                "¿Qué es un 'C2 Server' (servidor de Comando y Control) y qué función cumple para un malware infiltrado?",
                "¿Qué es el 'beaconing' o balizamiento en comunicaciones de malware y por qué los atacantes usan intervalos de tiempo con 'jitter' (aleatoriedad)?",
                "Si una IP interna realiza conexiones DNS constantes a dominios extraños generados algorítmicamente (DGA), ¿qué fase del ataque se está presenciando?"
            ]
        }
        q_list = MINI_TEST_QUESTIONS.get(current_topic, ["¿Cómo mitigarías esta vulnerabilidad?"] * 3)
        
        if user_understands or diagnostic_eval == "known":
            # Pregunta contestada correctamente!
            progreso["test_step"] += 1
            new_step = progreso["test_step"]
            
            if new_step < 3:
                # Siguiente pregunta del test
                stage_instructions = f"""
                El estudiante está rindiendo el Mini-Test de '{display_active}'. Está respondiendo a la pregunta {new_step + 1} de 3.
                
                REGLAS ABSOLUTAS DE ESTA ETAPA (EVALUACIÓN):
                1. Felicítalo muy brevemente por responder correctamente a la pregunta anterior.
                2. Presenta de forma clara y destacada la siguiente pregunta del test (**Pregunta {new_step + 1} de 3**):
                   "**Pregunta {new_step + 1} de 3:** {q_list[new_step]}"
                3. TIENES ESTRICTAMENTE PROHIBIDO dar explicaciones largas o de relleno.
                4. TIENES ESTRICTAMENTE PROHIBIDO incluir marcas de recomendación como `[RECOMENDACION:...]` en esta respuesta.
                5. TIENES ESTRICTAMENTE PROHIBIDO sugerir cambiar de tema o avanzar a otros temas.
                """
            else:
                # ¡Mini-Test aprobado y completado con éxito!
                just_completed_topic = current_topic
                if just_completed_topic not in progreso["completed_topics"]:
                    progreso["completed_topics"].append(just_completed_topic)
                if just_completed_topic in progreso["curriculum"]:
                    progreso["curriculum"].remove(just_completed_topic)
                    
                # Resetear pasos del test
                progreso["test_step"] = 0
                
                # Buscar el siguiente tema
                if progreso["curriculum"]:
                    progreso["stage"] = "teaching"
                    progreso["current_topic"] = progreso["curriculum"][0]
                    progreso["topic_messages_count"] = 0
                    display_next = TOPIC_DISPLAY_NAMES[progreso["current_topic"]]
                    
                    level_map = {
                        "texto_plano": "Nivel_1",
                        "http_phishing": "Nivel_2",
                        "port_scan": "Nivel_3",
                        "dos": "Nivel_4",
                        "malware_c2": "Nivel_5"
                    }
                    rec_level = level_map.get(just_completed_topic, "Nivel_1")
                    
                    stage_instructions = f"""
                    ¡ATENCIÓN TUTOR!: El estudiante ha aprobado con éxito todas las preguntas del Mini-Test de '{display_active}', completándolo al 100%.
                    El siguiente tema a aprender es: '{display_next}'.
                    
                    DEBES HACER LO SIGUIENTE EXACTAMENTE:
                    1. Felicítalo cordialmente por aprobar el Mini-Test y dominar el tema: '{display_active}'.
                    2. Recomiéndale explícitamente poner en práctica lo aprendido en este tema específico usando las marcas interactivas del frontend al final de tu mensaje:
                       - Ir al Simulador: `[RECOMENDACION:SIMULADOR:{rec_level}]`
                       - Ir al Análisis de Capturas: `[RECOMENDACION:PCAP]`
                    3. De manera fluida en el mismo mensaje, introduce y da inicio al siguiente tema de la ruta adaptada: '{display_next}', formulando una explicación inicial o una primera pregunta para comenzar.
                    """
                else:
                    progreso["stage"] = "completed_all"
                    progreso["current_topic"] = None
                    
                    level_map = {
                        "texto_plano": "Nivel_1",
                        "http_phishing": "Nivel_2",
                        "port_scan": "Nivel_3",
                        "dos": "Nivel_4",
                        "malware_c2": "Nivel_5"
                    }
                    rec_level = level_map.get(just_completed_topic, "Nivel_1")
                    
                    stage_instructions = f"""
                    ¡ATENCIÓN TUTOR!: El estudiante ha aprobado el Mini-Test del tema '{display_active}', completándolo al 100%. Con esto, ha terminado TODOS los temas de su ruta adaptativa.
                    
                    DEBES HACER LO SIGUIENTE EXACTAMENTE:
                    1. Felicítalo calurosamente por completar de forma excelente todo el Mini-Test de '{display_active}' y finalizar con éxito toda su ruta de aprendizaje adaptada en NetTutor.
                    2. Recomiéndale realizar la práctica técnica interactiva en los módulos reales usando las marcas:
                       - Ir al Simulador: `[RECOMENDACION:SIMULADOR:{rec_level}]`
                       - Ir al Análisis de Capturas: `[RECOMENDACION:PCAP]`
                    3. Motívalo a seguir explorando y experimentando en ciberseguridad.
                    """
        else:
            # Falló alguna de las preguntas del test. Lo regresamos a teaching para reforzar.
            progreso["stage"] = "teaching"
            progreso["topic_messages_count"] = 0
            progreso["test_step"] = 0 # Reiniciar progreso del test
            
            stage_instructions = f"""
            El estudiante ha respondido de forma INCORRECTA o incompleta a la Pregunta {step + 1} del Mini-Test del tema: '{display_active}'.
            
            DEBES HACER LO SIGUIENTE EXACTAMENTE:
            1. Explícale detalladamente en qué consistía el error de su respuesta y cuál era el concepto técnico correcto (apóyate en el RAG).
            2. Infórmale con tono alentador que regresamos temporalmente a la fase de enseñanza para reforzar el tema y que podrá intentar el Mini-Test de 3 preguntas completas de nuevo cuando esté listo.
            3. TIENES ESTRICTAMENTE PROHIBIDO incluir marcas de recomendación `[RECOMENDACION:...]` en esta respuesta.
            4. Haz una pregunta aclaratoria más sencilla para asegurar que asimile la base antes de continuar.
            """

    # 4. Guardar progreso actualizado en base de datos
    if id_sesion is not None:
        guardar_progreso_usuario(id_sesion, progreso)

    # 5. Obtener contexto RAG
    rag_context = ""
    active_topic = progreso["current_topic"] or topic
    if progreso["stage"] == "global_diagnostic":
        # Durante el diagnóstico, no queremos RAG en absoluto para mantener respuestas cortas y concisas
        rag_context = ""
    elif router_json.get("needs_rag", True):
        # Si acabamos de pasar a teaching, consultamos con el nombre del tema para traer la introducción correcta
        query_text = user_message
        if progreso["stage"] == "teaching" and progreso["topic_messages_count"] == 0:
            query_text = f"Conceptos básicos e introducción a {active_topic}"
        
        rag_context = rag.get_knowledge(query_text, topic=active_topic)

    pcap_context = f"Datos de Scapy: {pcap_data}" if pcap_data else "No hay archivo subido aún."

    # 6. Construir prompt del tutor estructurado
    # Reemplazar el prompt base con el prompt adaptativo
    SYSTEM_PROMPT_GENERAL_TUTOR_ADAPTIVE = """
Eres un Tutor Experto y Directivo en Ciberseguridad en NetTutor.
Tu objetivo es guiar al estudiante de forma clara, directa y altamente pedagógica a través de un plan de estudio adaptativo.

ESTADO DE APRENDIZAJE DEL ESTUDIANTE:
{progreso_json}

REGLAS GENERALES:
1. Mantén siempre un tono profesional, experto y motivador. Sé directo, claro y no des explicaciones excesivamente largas o de relleno.
2. Si el estudiante se equivoca o no sabe algo, corrígelo con amabilidad dando la respuesta correcta directamente en vez de ser críptico o evasivo.
3. Si recomiendas pasar a la práctica, utiliza las siguientes marcas textuales exactas al final de tu mensaje para que el frontend pueda renderizar tarjetas premium interactivas:
   - Para recomendar el Simulador de Ataques: `[RECOMENDACION:SIMULADOR:Nivel_X]` (donde X es del 1 al 5 correspondiente al tema).
     * Tema 'texto_plano' -> `[RECOMENDACION:SIMULADOR:Nivel_1]`
     * Tema 'http_phishing' -> `[RECOMENDACION:SIMULADOR:Nivel_2]`
     * Tema 'port_scan' -> `[RECOMENDACION:SIMULADOR:Nivel_3]`
     * Tema 'dos' -> `[RECOMENDACION:SIMULADOR:Nivel_4]`
     * Tema 'malware_c2' -> `[RECOMENDACION:SIMULADOR:Nivel_5]`
   - Para recomendar el Análisis PCAP: `[RECOMENDACION:PCAP]`
   - Asegúrate de incluir el texto explicativo y de motivación al lado de las marcas, por ejemplo:
     "¡Excelente trabajo completando este módulo! Te recomiendo poner en práctica lo aprendido en el simulador: [RECOMENDACION:SIMULADOR:Nivel_1] o analizando una captura de red real: [RECOMENDACION:PCAP]"

INSTRUCCIONES DE ETAPA ACTUAL:
{stage_instructions}
"""

    full_system_prompt = SYSTEM_PROMPT_GENERAL_TUTOR_ADAPTIVE.format(
        progreso_json=json.dumps(progreso, ensure_ascii=False, indent=2),
        stage_instructions=stage_instructions
    ) + f"\n\nCONTEXTO TÉCNICO RAG:\n{rag_context if rag_context else 'No se recuperó contexto adicional.'}\n\nDATOS DE CAPTURA PCAP:\n{pcap_context}"

    messages_to_send = [{"role": "system", "content": full_system_prompt}]
    if history:
        messages_to_send.extend(history)
    else:
        messages_to_send.append({"role": "user", "content": user_message})

    final_response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=messages_to_send,
        temperature=0.2,
    )
    
    return {
        "response": final_response.choices[0].message.content,
        "router": router_json,
        "progreso": progreso
    }

# =========================
# PCAP ANALYSIS
# =========================

def get_pcap_analysis_response(
    pcap_data: dict,
    history: Optional[List[Dict[str, str]]] = None,
    user_message: Optional[str] = None
) -> dict:
    global rag
    router_json = {}

    if user_message:
        router_messages = [
            {"role": "system", "content": SYSTEM_PROMPT_ANALYSIS_ROUTER},
            {"role": "user", "content": f"MENSAJE ACTUAL:\n{user_message}"}
        ]
        if history:
            historial_breve = history[-3:] if len(history) >= 3 else history
            router_messages.insert(1, {"role": "system", "content": f"HISTORIAL RECIENTE:\n{json.dumps(historial_breve, ensure_ascii=False)}"})
            
        intent_response = client.chat.completions.create(
            model="openai/gpt-oss-120b",
            messages=router_messages,
            temperature=0.1,
            response_format={"type": "json_object"}
        )
        
        raw_router = intent_response.choices[0].message.content.strip()
        router_json = safe_json_loads(raw_router)
        
        rag_context = ""
        if router_json.get("needs_rag", True) and rag:
            rag_context = rag.get_knowledge(user_message, topic="general")
            
        prompt = SYSTEM_PROMPT_PCAP_ANALYSIS.format(pcap_summary=str(pcap_data))
        prompt += f"\n\nINTENCIÓN DEL USUARIO:\n{json.dumps(router_json, ensure_ascii=False)}"
        if rag_context:
            prompt += f"\n\nCONTEXTO TÉCNICO (RAG):\n{rag_context}"
            
        messages_to_send = [{"role": "system", "content": prompt}]
        if history:
            messages_to_send.extend(history)
        messages_to_send.append({"role": "user", "content": user_message})
        
    else:
        prompt = SYSTEM_PROMPT_PCAP_ANALYSIS.format(pcap_summary=str(pcap_data))
        messages_to_send = [{"role": "system", "content": prompt}]
        if history:
            messages_to_send.extend(history)
        else:
            messages_to_send.append(
                {
                    "role": "user",
                    "content": "Analiza los datos del PCAP y guía mi aprendizaje de acuerdo a las reglas establecidas."
                }
            )

    final_response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=messages_to_send,
        temperature=0.2,
    )

    return {
        "response": final_response.choices[0].message.content,
        "router": router_json
    }

# =========================
# ESCENARIOS
# =========================

def generate_scenario_data(nivel_id: int):
    global rag
    if rag is None:
        init_rag_service()

    from app.db.supabase_client import supabase

    res = supabase.table("Nivel").select("*").eq("id_nivel", nivel_id).execute()
    if not res.data:
        raise ValueError(f"Nivel {nivel_id} no encontrado en la BD")
    
    nivel_info = res.data[0]
    topic = nivel_info.get("titulo_ataque", "general")
    prompt_especifico = nivel_info.get("prompt_especifico", "")

    contexto_rag = rag.get_knowledge(
        f"Análisis técnico de {topic}",
        topic=topic,
    )

    prompt = SYSTEM_PROMPT_SCENARIO_DESIGNER + f"""

TOPICO: {topic}
NIVEL: {nivel_id}
CONTEXTO_RAG:
{contexto_rag if contexto_rag else "Información general de seguridad"}
INSTRUCCIÓN ESPECÍFICA:
{prompt_especifico}
"""

    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "system", "content": prompt}],
        temperature=0.8,
        response_format={"type": "json_object"},
    )

    raw = response.choices[0].message.content
    return json.loads(raw)