# Explicación del Agente de Inteligencia Artificial (ChileAtiende Q&A)

Este documento detalla el diseño, la arquitectura y el flujo de ejecución del agente virtual implementado en el backend del proyecto. A continuación, se responden las tres preguntas planteadas en base al código real del repositorio.

---

## Pregunta 1: El Problema y el Contrato de Herramientas (JSON Schema / @tool)

### 1.1 Breve Caso de Uso a Resolver
El sistema resuelve la necesidad de los ciudadanos chilenos de obtener respuestas claras, verídicas y oficiales sobre trámites, leyes, subsidios y beneficios estatales (ecosistema **ChileAtiende / Registro Civil**). Adicionalmente, el ciudadano puede programar un recordatorio del trámite en su **Google Calendar** personal.

El agente debe:
- Consultar obligatoriamente una base de conocimientos local de forma semántica (RAG) para no alucinar requisitos legales ni fechas de trámites.
- Solicitar activamente el correo electrónico del usuario y la fecha si no son explícitos.
- Calcular fechas relativas (como "mañana" o "el próximo lunes") basándose en la hora del servidor.
- Generar el evento de calendario con los requisitos oficiales adjuntos en la descripción del evento.

---

### 1.2 Definición Técnica de las Herramientas

En el archivo [react_agent.py](file:///c:/Users/lzamo/Desktop/LLM/Backend/app/services/react_agent.py), las herramientas se le presentan al LLM a través de un esquema nativo de **Function Calling (JSON Schema)** de la API de OpenAI/Groq.

A continuación, se muestra la definición en formato **JSON Schema** y su equivalente conceptual en **Python documentada con decoradores `@tool`**.

#### Herramienta 1: Búsqueda Semántica (`search_chileatiende_knowledge`)

* **Definición nativa en JSON Schema:**
```json
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
}
```

* **Equivalencia en Python (`@tool`):**
```python
from langchain_core.tools import tool

@tool
def search_chileatiende_knowledge(query: str) -> str:
    """
    Realiza una búsqueda semántica en la base de conocimientos del Registro Civil. 
    Usa esta herramienta para buscar requisitos, procesos o leyes oficiales de ChileAtiende.
    
    Args:
        query: La consulta principal o términos de búsqueda ingresados por el usuario.
    """
    # Código interno que ejecuta Multi-Query Retrieval (MQR) y busca en ChromaDB
    pass
```

---

#### Herramienta 2: Crear Recordatorio (`crear_recordatorio`)

* **Definición nativa en JSON Schema:**
```json
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
```

* **Equivalencia en Python (`@tool`):**
```python
from langchain_core.tools import tool

@tool
def crear_recordatorio(tramite: str, fecha_hora: str, email: str, documentos: str) -> str:
    """
    Crea un recordatorio en Google Calendar y envía una invitación al correo del usuario.
    Requiere que primero se hayan obtenido los requisitos mediante búsqueda semántica.
    
    Args:
        tramite: El nombre del trámite a recordar (ej. 'Renovación de cédula de identidad').
        fecha_hora: La fecha y hora en formato ISO 8601 (YYYY-MM-DDTHH:MM:SS).
        email: El correo del ciudadano receptor.
        documentos: Requisitos oficiales recuperados previamente del RAG.
    """
    # Código interno que conecta con Google Calendar API usando credenciales de cuenta de servicio
    pass
```

---

## Pregunta 2: La Arquitectura Cognitiva (El Patrón Elegido)

### 2.1 El Patrón Elegido: ReAct (Reasoning and Acting) con Multi-Query Retrieval (MQR)

El proyecto implementa un patrón **ReAct (Reasoning and Acting)** dinámico ejecutado a través del mecanismo nativo de Function Calling de la API de Groq en un ciclo iterativo controlado (`max_steps=2`).

#### ¿Por qué ReAct?
El agente no sigue un plan estático precalculado (Plan-and-Execute) ni evalúa la corrección de su propia respuesta en un bucle corrector separado (Reflexion). En su lugar:
1. Recibe la entrada del usuario y **razona** si le falta información (ej. no conoce los requisitos del trámite o no tiene el correo del usuario).
2. Si le falta información del trámite, decide **actuar** llamando a `search_chileatiende_knowledge`.
3. Una vez obtenida la información del RAG, el bucle vuelve a procesar el estado actual. El agente **razona** que ya tiene los requisitos y que ahora puede **actuar** llamando a `crear_recordatorio` si cuenta con los datos del usuario.
4. Finalmente, tras recibir el resultado de la creación del recordatorio, genera la respuesta conversacional final limpia de marcas técnicas.

---

### 2.2 Prompts de Sistema Clave

El comportamiento está orquestado por dos prompts principales en [react_agent.py](file:///c:/Users/lzamo/Desktop/LLM/Backend/app/services/react_agent.py):

#### A. Prompt del Orquestador Principal (Tutor General)
Este prompt define las reglas y el flujo lógico de ejecución (incluyendo el enrutamiento y control de comportamiento en 3 escenarios de negocio).

```python
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
```

Adicionalmente, se le inyecta dinámicamente en tiempo de ejecución la fecha y hora actual del sistema para que pueda realizar razonamiento temporal relativo:
`"La fecha y hora actual del sistema es: Lunes, 2026-06-08 09:30:00. Úsala para calcular fechas relativas como 'mañana', 'lunes', etc."`

#### B. Prompt del Especialista / Query Rewriter (Multi-Query Retrieval)
Cuando el agente decide invocar la herramienta `search_chileatiende_knowledge`, la consulta pasa por un reescritor (MQR) que genera variantes alternativas de búsqueda semántica mediante el siguiente prompt dedicado:

```python
def generar_mqr(user_query: str) -> List[str]:
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
    ...
```

* **Especialización:** Este prompt delega la tarea de diversificar la búsqueda a un "rol secundario" especializado que descompone la duda del usuario en terminología técnica del gobierno y palabras clave de requisitos antes de consultar ChromaDB, mejorando drásticamente los resultados devueltos al contexto.

---

## Pregunta 3: Function Calling en Acción (La Traza)

A continuación se presenta un flujo real y estructurado de la comunicación en formato JSON entre el código Python y la API del LLM.

### Escenario de Prueba
* **Fecha actual del sistema:** `Lunes, 2026-06-08 09:00:00`
* **Mensaje del usuario:** *"Hola, necesito saber qué papeles piden para renovar la cédula de identidad y por favor agendame un recordatorio para mañana a las 11 AM al correo ciudadano@ejemplo.cl"*

---

### Paso 1: Petición inicial al LLM
El backend de FastAPI toma el mensaje del usuario y el prompt del sistema y los envía al LLM junto con la lista de herramientas disponibles (`TOOLS`).

```json
// POST enviado al LLM
{
  "model": "llama-3.3-70b-versatile",
  "messages": [
    {
      "role": "system",
      "content": "Eres el asistente virtual experto oficial de ChileAtiende... [SISTEMA]: La fecha y hora actual del sistema es: Lunes, 2026-06-08 09:00:00. ..."
    },
    {
      "role": "user",
      "content": "Hola, necesito saber qué papeles piden para renovar la cédula de identidad y por favor agendame un recordatorio para mañana a las 11 AM al correo ciudadano@ejemplo.cl"
    }
  ],
  "tools": [ /* Esquemas JSON de search_chileatiende_knowledge y crear_recordatorio */ ],
  "tool_choice": "auto"
}
```

---

### Paso 2: El LLM decide invocar la Búsqueda Semántica
El LLM analiza que no puede responder de memoria ni crear el recordatorio sin obtener primero los documentos requeridos del RAG. Por lo tanto, emite un `tool_call`.

```json
// Respuesta recibida del LLM (Elección de Herramienta)
{
  "id": "chatcmpl-XYZ123",
  "object": "chat.completion",
  "choices": [
    {
      "index": 0,
      "message": {
        "role": "assistant",
        "content": null,
        "tool_calls": [
          {
            "id": "call_abc456",
            "type": "function",
            "function": {
              "name": "search_chileatiende_knowledge",
              "arguments": "{\"query\": \"Renovación de cédula de identidad chilenos\"}"
            }
          }
        ]
      },
      "finish_reason": "tool_calls"
    }
  ]
}
```

---

### Paso 3: Python ejecuta la función local y devuelve el resultado
El backend intercepta la llamada, ejecuta `generar_mqr` (que genera 3 variantes como *"requisitos para renovar carnet"*, *"cédula de identidad renovación registro civil"*, etc.), consulta ChromaDB y obtiene la información oficial. Esta se devuelve al modelo con el rol `"tool"` y el ID correspondiente.

```json
// Siguiente llamada enviada al LLM (con el resultado de la herramienta)
{
  "model": "llama-3.3-70b-versatile",
  "messages": [
    /* ... mensajes anteriores ... */
    {
      "role": "assistant",
      "content": null,
      "tool_calls": [
        {
          "id": "call_abc456",
          "type": "function",
          "function": {
            "name": "search_chileatiende_knowledge",
            "arguments": "{\"query\": \"Renovación de cédula de identidad chilenos\"}"
          }
        }
      ]
    },
    {
      "role": "tool",
      "tool_call_id": "call_abc456",
      "name": "search_chileatiende_knowledge",
      "content": "[Fuente: cedula_identidad.txt | pág. 1]\nPara chilenos que renuevan cédula de identidad se requiere presentar la cédula anterior (si la tiene). Si se perdió, debe indicarlo. El costo es de $3.820 pesos chilenos."
    }
  ]
}
```

---

### Paso 4: El LLM decide agendar el recordatorio
El LLM vuelve a razonar: ahora tiene la lista de documentos oficiales, el correo electrónico del usuario (`ciudadano@ejemplo.cl`), y calcula de manera exacta la fecha "mañana a las 11 AM" basándose en el tiempo de referencia inyectado (`2026-06-08 09:00:00` + 1 día = `2026-06-09T11:00:00`). Genera la llamada a la segunda herramienta.

```json
// Respuesta recibida del LLM (Segunda llamada de Herramienta)
{
  "choices": [
    {
      "index": 0,
      "message": {
        "role": "assistant",
        "content": null,
        "tool_calls": [
          {
            "id": "call_def789",
            "type": "function",
            "function": {
              "name": "crear_recordatorio",
              "arguments": "{\n  \"tramite\": \"Renovación de cédula de identidad\",\n  \"fecha_hora\": \"2026-06-09T11:00:00\",\n  \"email\": \"ciudadano@ejemplo.cl\",\n  \"documentos\": \"Cédula de identidad anterior (si la posee). En caso de pérdida, informar al oficial civil.\"\n}"
            }
          }
        ]
      },
      "finish_reason": "tool_calls"
    }
  ]
}
```

---

### Paso 5: Python crea el evento en Google Calendar y devuelve el resultado
El backend ejecuta la integración con Google Calendar API y le devuelve al LLM la confirmación del agendamiento.

```json
// Siguiente llamada enviada al LLM (con el resultado del calendario)
{
  "model": "llama-3.3-70b-versatile",
  "messages": [
    /* ... mensajes anteriores ... */
    {
      "role": "assistant",
      "content": null,
      "tool_calls": [
        {
          "id": "call_def789",
          "type": "function",
          "function": {
            "name": "crear_recordatorio",
            "arguments": "{\n  \"tramite\": \"Renovación de cédula de identidad\",\n  \"fecha_hora\": \"2026-06-09T11:00:00\",\n  \"email\": \"ciudadano@ejemplo.cl\",\n  \"documentos\": \"Cédula de identidad anterior (si la posee). En caso de pérdida, informar al oficial civil.\"\n}"
          }
        }
      ]
    },
    {
      "role": "tool",
      "tool_call_id": "call_def789",
      "name": "crear_recordatorio",
      "content": "✅ Recordatorio agendado con éxito directamente en tu calendario (ciudadano@ejemplo.cl) para el 09/06/2026 a las 11:00."
    }
  ]
}
```

---

### Paso 6: Respuesta Final del LLM al usuario
El LLM, viendo que el recordatorio ya fue creado y que tiene las respuestas del RAG, formula la respuesta conversacional definitiva que se mostrará en la interfaz del chat del ciudadano, cumpliendo con la directriz de no exhibir pensamientos internos ni metadatos.

```json
// Respuesta final limpia del LLM
{
  "choices": [
    {
      "index": 0,
      "message": {
        "role": "assistant",
        "content": "Hola. Para renovar su cédula de identidad, únicamente necesita presentar su cédula anterior en la oficina. Si no la tiene por robo o extravío, solo debe notificarlo al oficial durante el trámite. El valor actual es de $3.820 pesos chilenos.\n\nHe agendado exitosamente el recordatorio en su calendario (ciudadano@ejemplo.cl) para el **martes 9 de junio de 2026 a las 11:00 AM**, adjuntando la información correspondiente. ¡Que tenga un excelente día!"
      },
      "finish_reason": "stop"
    }
  ]
}
```
