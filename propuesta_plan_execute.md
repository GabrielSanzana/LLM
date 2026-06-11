# Propuesta: Migración a Arquitectura Plan-and-Execute (Plan-and-Solve)

Este documento explica de forma conceptual y técnica cómo cambiar la arquitectura actual de tu agente (basada en **ReAct**) hacia una arquitectura **Plan-and-Execute (Plan-and-Solve)**, y cómo afectaría esto al proyecto.

---

## 1. Comparación de Arquitecturas: ReAct vs. Plan-and-Execute

| Aspecto | ReAct (Actual) | Plan-and-Execute (Propuesta) |
| :--- | :--- | :--- |
| **Concepto** | Ciclo dinámico e iterativo de *Pensamiento*, *Acción* y *Observación* paso a paso. | Un módulo **Planificador** crea una lista estructurada de pasos iniciales, y un **Ejecutor** corre las herramientas en orden. |
| **Flujo de Ejecución** | `Entrada -> Pensar -> Llamar herramienta -> Observar -> Pensar -> Respuesta final` | `Entrada -> Crear Plan -> Ejecutar Paso 1 -> Ejecutar Paso 2 -> Sintetizar Respuesta` |
| **Consumo de Tokens** | Medio (varía según el número de pasos, pero reutiliza todo el contexto en cada paso). | Alto (requiere múltiples llamadas al LLM: Planificación, Ejecución por paso, y Síntesis). |
| **Predictibilidad** | Baja (el modelo decide libremente qué llamar y cuándo detenerse; puede entrar en bucle). | Alta (el plan se genera al inicio y se ejecuta de forma estructurada; ideal para auditoría). |
| **Flexibilidad** | Alta (responde muy bien a giros inesperados durante la conversación). | Media/Baja (el plan es rígido, aunque se puede implementar un "Replanteador" si un paso falla). |

---

## 2. Cómo cambia el proyecto

1. **Estructura del Backend**:
   * Mantendrás el mismo endpoint `/api/chat` en `main.py`, pero la lógica interna llamará a un nuevo servicio de orquestación (`plan_execute_agent.py`).
   * El código se vuelve más modular: en lugar de un único prompt largo, tendrás tres prompts especializados: **Planificador**, **Ejecutor** y **Sintetizador**.

2. **Visibilidad de la Traza**:
   * En lugar de mostrar llamadas a herramientas sueltas en la traza, podrás mostrar el plan completo al inicio de la ejecución (ej: `"Paso 1: Buscar en RAG"`, `"Paso 2: Agendar calendario"`), dando una experiencia visual mucho más robusta en el Frontend.

---

## 3. Implementación Paso a Paso en Python

Para implementar esto de forma limpia sin romper tu lógica ReAct actual, crearemos un nuevo archivo: [plan_execute_agent.py](file:///c:/Users/lzamo/Desktop/LLM/Backend/app/services/plan_execute_agent.py).

### 3.1 Prompts Clave de la Arquitectura

#### A. Prompt del Planificador (Planner)
El planificador recibe la entrada y genera un JSON con el plan detallado.

```python
SYSTEM_PLANNER_PROMPT = """
Eres el Planificador Oficial de ChileAtiende. Tu único objetivo es recibir la consulta de un ciudadano chileno y crear un plan secuencial de pasos para resolverla utilizando las herramientas y opciones disponibles.

Opciones de pasos a planificar:
1. `search_chileatiende_knowledge`: Buscar requisitos, costos y leyes del trámite. (Obligatorio si se pregunta por detalles de un trámite).
2. `crear_recordatorio`: Agendar un recordatorio en Google Calendar (requiere trámite, documentos recuperados del RAG, fecha_hora e email del usuario).
3. `ask_user`: Solicitar información faltante al usuario (por ejemplo, su correo electrónico si pidió agendar pero no lo suministró).

Reglas de Planificación:
- Si el usuario solicita agendar un recordatorio, debes planificar primero la búsqueda semántica en la base de conocimientos (`search_chileatiende_knowledge`) para obtener los requisitos.
- Si no posees el correo electrónico del usuario, debes planificar un paso `ask_user` preguntando por el correo.
- Tu salida debe ser estrictamente un arreglo JSON de objetos con la siguiente estructura:
[
  {
    "step_id": 1,
    "tool": "search_chileatiende_knowledge",
    "description": "Buscar los requisitos y costos para la renovación del carnet de identidad",
    "query": "requisitos renovación cédula identidad chilenos"
  }
]
No agregues texto explicativo antes ni después del JSON.
"""
```

#### B. Prompt del Sintetizador (Synthesizer)
Una vez ejecutados todos los pasos del plan, este prompt toma los resultados y formula la respuesta conversacional final.

```python
SYSTEM_SYNTHESIZER_PROMPT = """
Eres el asistente virtual experto oficial de ChileAtiende.
Tu tarea es responder al ciudadano de forma clara, empática y resolutiva, basándote en su consulta original y en los resultados obtenidos tras ejecutar el plan de acción.

Consulta original del usuario: {user_query}

Resultados del plan ejecutado:
{results_context}

Redacta la respuesta final de forma directa y natural. No incluyas menciones técnicas al "planificador", "ejecutor" o IDs de pasos. El ciudadano solo debe ver la información limpia.
"""
```

---

### 3.2 Código Propuesto para `plan_execute_agent.py`

Aquí tienes el código de cómo estructurar la lógica de orquestación en Python:

```python
import os
import json
from typing import Any, Dict, List, Optional
from groq import Groq
from datetime import datetime

from .rag_service import RAGService
from .google_calendar_service import GoogleCalendarService
from .react_agent import generar_mqr, busqueda_semantica_abierta, _clip_text

client = Groq(api_key=os.getenv("GROQ_API_KEY"))
rag = RAGService()
calendar_service = GoogleCalendarService()

# (Definir aquí SYSTEM_PLANNER_PROMPT y SYSTEM_SYNTHESIZER_PROMPT)

def get_response_plan_execute(
    user_message: str,
    history: Optional[List[Dict[str, str]]] = None
) -> Dict[str, Any]:
    model = os.environ["GROQ_MODEL"]
    trace = []
    
    # 1. GENERAR EL PLAN
    dias_semana = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]
    ahora = datetime.now()
    nombre_dia = dias_semana[ahora.weekday()]
    current_time_str = f"{nombre_dia}, {ahora.strftime('%Y-%m-%d %H:%M:%S')}"
    
    planner_messages = [
        {"role": "system", "content": SYSTEM_PLANNER_PROMPT + f"\n\nFecha actual: {current_time_str}"},
        {"role": "user", "content": f"Consulta del usuario: {user_message}"}
    ]
    
    try:
        planner_resp = client.chat.completions.create(
            model=model,
            messages=planner_messages,
            temperature=0.1,  # Baja temperatura para asegurar formato JSON
            response_format={"type": "json_object"}
        )
        plan_data = json.loads(planner_resp.choices[0].message.content)
        # Suponiendo que el modelo responde {"plan": [...]}
        plan = plan_data.get("plan", [])
    except Exception as e:
        # Fallback si el planificador falla: plan minimalista
        plan = [{"step_id": 1, "tool": "search_chileatiende_knowledge", "query": user_message}]
        
    trace.append({"type": "plan_generated", "plan": plan})
    
    # 2. EJECUTAR EL PLAN
    results_context = []
    requirements_extracted = ""
    email_user = None
    
    # Extraer correo del historial o del mensaje si existe
    if "@" in user_message:
        # Extracción simple de correo
        for word in user_message.split():
            if "@" in word:
                email_user = word.strip(".,!?")
                
    for step in plan:
        tool_name = step.get("tool")
        step_id = step.get("step_id")
        
        trace.append({"type": "executing_step", "step_id": step_id, "tool": tool_name})
        
        if tool_name == "search_chileatiende_knowledge":
            query = step.get("query", user_message)
            queries_optimizadas = generar_mqr(query)
            observation = busqueda_semantica_abierta(queries_optimizadas, query)
            requirements_extracted = _clip_text(observation, 2000)
            
            results_context.append(f"Paso {step_id} (Búsqueda RAG): {requirements_extracted}")
            trace.append({"type": "step_result", "step_id": step_id, "result": "Búsqueda RAG completada"})
            
        elif tool_name == "crear_recordatorio":
            if not email_user:
                # Si no tenemos el correo, cambiamos dinámicamente el paso para pedirlo
                results_context.append(f"Paso {step_id}: No se pudo crear el recordatorio porque falta el email del usuario.")
                trace.append({"type": "step_result", "step_id": step_id, "result": "Falta email"})
                continue
                
            fecha_hora = step.get("fecha_hora") or (ahora + datetime.timedelta(days=1)).strftime("%Y-%m-%dT09:00:00")
            tramite = step.get("tramite", "Trámite ChileAtiende")
            
            res = calendar_service.create_reminder_event(
                tramite=tramite,
                fecha_hora_str=fecha_hora,
                email=email_user,
                documentos=requirements_extracted
            )
            observation = res.get("message", "Error al procesar recordatorio.")
            results_context.append(f"Paso {step_id} (Google Calendar): {observation}")
            trace.append({"type": "step_result", "step_id": step_id, "result": observation})
            
        elif tool_name == "ask_user":
            results_context.append(f"Paso {step_id}: Se requiere preguntar al usuario por información faltante.")
            trace.append({"type": "step_result", "step_id": step_id, "result": "Esperando información del usuario"})

    # 3. SINTETIZAR RESPUESTA FINAL
    synthesizer_messages = [
        {"role": "system", "content": SYSTEM_SYNTHESIZER_PROMPT},
        {"role": "user", "content": f"Consulta original: {user_message}\n\nResultados:\n" + "\n".join(results_context)}
    ]
    
    final_resp = client.chat.completions.create(
        model=model,
        messages=synthesizer_messages,
        temperature=0.3
    )
    
    response_text = final_resp.choices[0].message.content
    trace.append({"type": "final_answer", "content": response_text})
    
    return {
        "response": response_text,
        "trace": trace
    }
```

---

## 4. Próximos Pasos para Habilitarlo en el Proyecto

Si deseas que implemente este cambio en tu código:
1. Crearemos el archivo `plan_execute_agent.py` en `Backend/app/services/`.
2. Actualizaremos `Backend/app/main.py` para importar `get_response` desde `plan_execute_agent` en lugar de `react_agent`.
3. Ajustaremos la visualización de la traza en el Frontend si es necesario para renderizar el plan inicial de pasos.
