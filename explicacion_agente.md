# Explicación del Agente de Inteligencia Artificial (ChileAtiende Q&A - Plan-and-Execute)

Este documento detalla el diseño, la arquitectura y el flujo de ejecución del agente virtual implementado en el backend del proyecto tras la migración al patrón **Plan-and-Execute**. A continuación, se responden las tres preguntas planteadas basadas en el código real del repositorio.

---

## Pregunta 1: El Problema y el Contrato de Herramientas (JSON Schema / @tool)

### 1.1 Breve Caso de Uso a Resolver
El sistema resuelve la necesidad de los ciudadanos chilenos de obtener respuestas claras, verídicas y oficiales sobre trámites, leyes, subsidios y beneficios estatales (ecosistema **ChileAtiende / Registro Civil**). Adicionalmente, el ciudadano puede programar un recordatorio del trámite en su **Google Calendar** personal.

El agente debe:
- Identificar la intención del usuario (si solo consulta información o si también quiere un recordatorio).
- Consultar obligatoriamente una base de conocimientos local de forma semántica (RAG) para no alucinar requisitos legales ni fechas de trámites.
- Solicitar activamente el correo electrónico del usuario si desea un recordatorio y no lo ha provisto.
- Agendar la cita en Google Calendar inyectando en la descripción los requisitos oficiales recuperados desde ChromaDB.

---

### 1.2 Definición Técnica de las Herramientas

En el archivo [plan_execute_agent.py](file:///c:/Users/lzamo/Desktop/LLM/Backend/app/services/plan_execute_agent.py), las herramientas se le presentan al LLM a través de un esquema nativo de **Function Calling (JSON Schema)** de la API de Groq en la variable `TOOLS`.

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
                    "description": "La lista de documentos y requisitos necesarios para el trámite, recuperados en los pasos anteriores."
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

### 2.1 El Patrón Elegido: Plan-and-Execute (Plan-and-Solve)

Se ha implementado el patrón **Plan-and-Execute**. A diferencia de ReAct (que decide de forma incremental en cada paso y es más propenso a entrar en bucles o desviarse), este patrón divide la lógica de resolución en tres roles y agentes de prompt altamente especializados que se ejecutan secuencialmente:

1. **El Planificador (Planner)**: Analiza la entrada del usuario y el historial. Su único objetivo es trazar un plan secuencial de pasos lógicos representados en un objeto JSON.
2. **El Ejecutor (Executor)**: Bucle en Python que procesa cada paso del plan. Para cada paso, se invoca un prompt ejecutor secundario que toma los resultados acumulados de los pasos anteriores y determina si debe llamar a una herramienta (`search_chileatiende_knowledge` o `crear_recordatorio`).
3. **El Sintetizador (Synthesizer)**: Toma la consulta del usuario, el historial conversacional y los resultados de todos los pasos ejecutados del plan, redactando una respuesta ciudadana limpia y directa.

---

### 2.2 Prompts de Sistema Clave y Especialización

#### A. Prompt del Planificador (Planner)
Su especialización es puramente estratégica. No ejecuta herramientas directly ni se preocupa por los datos exactos del recordatorio; solo divide el problema. Fuerza una salida JSON estructurada.

```python
SYSTEM_PLANNER_PROMPT = """
Eres el Planificador Oficial de ChileAtiende. Tu único objetivo es recibir la consulta de un ciudadano chileno y crear un plan secuencial de pasos lógicos para resolverla utilizando las herramientas y opciones disponibles.

Herramientas y capacidades disponibles:
1. `search_chileatiende_knowledge`: Buscar requisitos, pasos, costos y leyes de un trámite en la base de conocimientos de ChileAtiende.
2. `crear_recordatorio`: Registrar un recordatorio oficial en Google Calendar enviando una invitación por correo electrónico al usuario.

Reglas de Planificación:
- Si el usuario pregunta por los requisitos, fechas o detalles de un trámite, el primer paso debe ser SIEMPRE realizar una búsqueda semántica (`search_chileatiende_knowledge`).
- Si el usuario solicita agendar un recordatorio, debes planificar primero la búsqueda en RAG para tener los requisitos oficiales, y luego planificar la creación del recordatorio (`crear_recordatorio`).
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
```

#### B. Prompt del Ejecutor (Executor)
Su especialización es operativa. Su objetivo es tomar la descripción de una tarea e inyectarle los argumentos específicos basándose en el historial de pasos previos y la consulta del usuario.

```python
SYSTEM_EXECUTOR_PROMPT = """
Eres el Agente Ejecutor de ChileAtiende. Tu tarea es ejecutar un paso específico de un plan previamente trazado por el Planificador.
Para lograr tu objetivo, debes analizar el paso actual y el contexto acumulado de los pasos ya completados, y decidir si requieres llamar a una herramienta.

=== CONTEXTO DE EJECUCIÓN ===
- Consulta original del usuario: {user_message}
- Historial de pasos completados y sus resultados:
{previous_steps_context}

=== PASO ACTUAL A EJECUTAR ===
- Paso ID: {step_id}
- Descripción: {step_description}
- Herramienta esperada: {tool_expected}

=== INSTRUCCIONES ===
1. Si el paso requiere usar una herramienta (ej. 'search_chileatiende_knowledge' o 'crear_recordatorio'), debes invocarla utilizando la llamada a función nativa (tool calling) y rellenar sus parámetros utilizando la información del contexto anterior.
2. Si el paso requiere agendar un recordatorio, extrae el correo del usuario, el trámite y la lista de documentos que se obtuvieron en los pasos de búsqueda anteriores.
3. Si el paso actual no requiere ninguna herramienta ('none'), simplemente describe brevemente el resultado o responde indicando qué falta.
"""
```

#### C. Prompt del Sintetizador (Synthesizer)
Su especialización es la redacción conversacional final y la empatía ciudadana. Su única entrada es la consulta inicial y el resumen textual de los resultados de cada paso.

```python
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
```

---

## Pregunta 3: Function Calling en Acción (La Traza)

A continuación se detalla cómo fluyen los mensajes y la ejecución entre la API y el código Python bajo la arquitectura Plan-and-Execute.

### Escenario de Prueba
* **Fecha actual del servidor:** `Lunes, 2026-06-08 09:00:00`
* **Mensaje del usuario:** *"Hola, necesito saber qué papeles piden para renovar la cédula de identidad y por favor agendame un recordatorio para mañana a las 11 AM al correo ciudadano@ejemplo.cl"*

---

### Paso 3.1: Fase de Planificación (Llamada al Planner)
El backend de FastAPI toma la pregunta y la envía al LLM solicitando la estructura del plan.

```json
// POST al LLM (Planner)
{
  "model": "llama-3.3-70b-versatile",
  "messages": [
    { "role": "system", "content": "Eres el Planificador Oficial de ChileAtiende... [SISTEMA]: La fecha y hora actual del sistema es: Lunes, 2026-06-08 09:00:00." },
    { "role": "user", "content": "Hola, necesito saber qué papeles piden para renovar la cédula de identidad y por favor agendame un recordatorio para mañana a las 11 AM al correo ciudadano@ejemplo.cl" }
  ],
  "response_format": { "type": "json_object" }
}
```

El LLM devuelve el plan en formato JSON:
```json
// Respuesta del Planner
{
  "plan": [
    {
      "step_id": 1,
      "description": "Buscar en el RAG los requisitos para la renovación de la cédula de identidad de chilenos.",
      "tool_expected": "search_chileatiende_knowledge"
    },
    {
      "step_id": 2,
      "description": "Crear un recordatorio en Google Calendar para el trámite de renovación de cédula de identidad para el 9 de junio de 2026 a las 11:00 AM.",
      "tool_expected": "crear_recordatorio"
    }
  ]
}
```

---

### Paso 3.2: Fase de Ejecución (Paso 1 - RAG)
El motor de Python toma el **Paso 1** y envía la solicitud al Ejecutor con las herramientas disponibles.

```json
// POST al LLM (Ejecutor - Paso 1)
{
  "model": "llama-3.3-70b-versatile",
  "messages": [
    { 
      "role": "system", 
      "content": "Eres el Agente Ejecutor de ChileAtiende... \n=== CONTEXTO ===\nConsulta original: Hola, necesito saber qué papeles... \nHistorial de pasos: Ninguno aún.\n\n=== PASO ACTUAL ===\nPaso ID: 1\nDescripción: Buscar en el RAG los requisitos...\nHerramienta esperada: search_chileatiende_knowledge" 
    },
    { "role": "user", "content": "Procesa y ejecuta este paso." }
  ],
  "tools": [ /* Herramientas */ ],
  "tool_choice": "auto"
}
```

El LLM decide invocar la búsqueda RAG:
```json
// Respuesta del LLM (Tool Call)
{
  "choices": [
    {
      "message": {
        "role": "assistant",
        "tool_calls": [
          {
            "id": "call_rag_1",
            "type": "function",
            "function": {
              "name": "search_chileatiende_knowledge",
              "arguments": "{\"query\": \"requisitos renovación cédula identidad chilenos\"}"
            }
          }
        ]
      }
    }
  ]
}
```

El código de Python intercepta esta llamada, ejecuta el RAG de ChromaDB en local y retorna la observación al flujo de la aplicación.
* **Resultado del RAG en Python:** *"Para chilenos que renuevan cédula se requiere presentar la cédula anterior (si la tiene). El costo es de $3.820 pesos chilenos."*

---

### Paso 3.3: Fase de Ejecución (Paso 2 - Calendario)
Python actualiza el contexto del historial y llama al Ejecutor para resolver el **Paso 2**.

```json
// POST al LLM (Ejecutor - Paso 2)
{
  "model": "llama-3.3-70b-versatile",
  "messages": [
    { 
      "role": "system", 
      "content": "Eres el Agente Ejecutor de ChileAtiende... \n=== CONTEXTO ===\nConsulta original: Hola, necesito saber qué papeles...\nHistorial de pasos:\n- Paso 1 (Buscar en el RAG...): Se llamó a `search_chileatiende_knowledge`. Resultado: Para chilenos que renuevan cédula se requiere presentar la cédula anterior (si la tiene). El costo es de $3.820 pesos chilenos.\n\n=== PASO ACTUAL ===\nPaso ID: 2\nDescripción: Crear un recordatorio en Google Calendar...\nHerramienta esperada: crear_recordatorio" 
    },
    { "role": "user", "content": "Procesa y ejecuta este paso." }
  ],
  "tools": [ /* Herramientas */ ],
  "tool_choice": "auto"
}
```

El LLM infiere los argumentos dinámicamente y llama a la herramienta:
```json
// Respuesta del LLM (Tool Call 2)
{
  "choices": [
    {
      "message": {
        "role": "assistant",
        "tool_calls": [
          {
            "id": "call_calendar_2",
            "type": "function",
            "function": {
              "name": "crear_recordatorio",
              "arguments": "{\n  \"tramite\": \"Renovación de cédula de identidad\",\n  \"fecha_hora\": \"2026-06-09T11:00:00\",\n  \"email\": \"ciudadano@ejemplo.cl\",\n  \"documentos\": \"Presentar la cédula de identidad anterior. Costo: $3.820 pesos chilenos.\"\n}"
            }
          }
        ]
      }
    }
  ]
}
```

El backend de Python ejecuta localmente la integración con Google Calendar API y obtiene el mensaje de éxito:
* **Resultado de la API de Google en Python:** *"✅ Recordatorio agendado con éxito directamente en tu calendario (ciudadano@ejemplo.cl) para el 09/06/2026 a las 11:00."*

---

### Paso 3.4: Fase de Síntesis Final (Llamada al Synthesizer)
Python consolida los resultados de todos los pasos y llama al Sintetizador.

```json
// POST al LLM (Synthesizer)
{
  "model": "llama-3.3-70b-versatile",
  "messages": [
    {
      "role": "system",
      "content": "Eres el asistente virtual experto oficial de ChileAtiende... \n=== CONTEXTO DE LA RESOLUCIÓN ===\nConsulta: Hola, necesito saber qué papeles...\nPlan y resultados:\n- Paso 1 (Buscar en el RAG...): Se llamó a `search_chileatiende_knowledge`. Resultado: Para chilenos que renuevan cédula se requiere presentar la cédula anterior (si la tiene). El costo es de $3.820 pesos chilenos.\n- Paso 2 (Crear un recordatorio...): Se llamó a `crear_recordatorio`. Resultado: ✅ Recordatorio agendado con éxito..."
    },
    { "role": "user", "content": "Hola, necesito saber qué papeles piden para renovar la cédula de identidad y por favor agendame un recordatorio para mañana a las 11 AM al correo ciudadano@ejemplo.cl" }
  ]
}
```

El LLM devuelve la respuesta final limpia al usuario:
```json
// Respuesta final sintetizada
{
  "choices": [
    {
      "message": {
        "role": "assistant",
        "content": "Hola. Para renovar su cédula de identidad, debe presentar su cédula anterior. El costo del trámite es de $3.820 pesos chilenos.\n\nHe agendado exitosamente el recordatorio en su calendario para el **martes 9 de junio de 2026 a las 11:00 AM** enviándole la invitación a **ciudadano@ejemplo.cl** junto con los requisitos detallados. ¡Que tenga un excelente día!"
      }
    }
  ]
}
```

---

### 3.5 Limpieza de Procesos de Pensamiento (`<think>`) en Python

Dado que algunos modelos de razonamiento (como DeepSeek-R1) inyectan su proceso de pensamiento directamente en la respuesta encerrándolo entre etiquetas `<think>...</think>`, el backend de Python aplica la siguiente función de limpieza mediante expresiones regulares antes de retornar cualquier texto a la base de datos o al cliente final:

```python
import re

def clean_think_tags(text: str) -> str:
    if not text:
        return ""
    # Eliminar bloques <think>...</think> (insensible a mayúsculas, multilínea)
    return re.sub(r'(?i)<think>.*?</think>', '', text, flags=re.DOTALL).strip()
```
Esto asegura que las explicaciones internas en inglés queden ocultas al ciudadano, garantizando una respuesta totalmente conversacional y oficial.
