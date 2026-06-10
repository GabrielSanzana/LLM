import os
from pathlib import Path
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from app.models.schemas import ChatRequest
from app.services.chat_service import (
    obtener_o_crear_sesion,
    guardar_mensaje_db,
    cargar_historial_db,
    borrar_historial_db,
)
from app.services.langgraph_agent import get_response

BASE_DIR = Path(__file__).resolve().parents[2]

app = FastAPI(title="Registro Civil - Chat QA (ReAct)")

origins = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:5174",
    "http://127.0.0.1:5174",
    "http://localhost:5175",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def read_root():
    return {"message": "Registro Civil Chat (ReAct) listo"}


@app.get("/api/status")
def get_status():
    return {"status": "ready", "message": "Servicio de chat disponible"}


@app.post("/api/chat")
def chat_endpoint(request: ChatRequest):
    try:
        session_id = obtener_o_crear_sesion()
        guardar_mensaje_db(session_id, "user", request.message)

        historial = cargar_historial_db(session_id)
        # pasar solo role/content al agente
        historial_simple = [{"role": m["role"], "content": m["content"]} for m in historial]

        result = get_response(request.message, history=historial_simple)
        response_text = result.get("response", "")

        guardar_mensaje_db(session_id, "assistant", response_text)

        return {"status": "success", "response": response_text, "trace": result.get("trace", [])}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/chat/history")
def get_chat_history():
    session_id = obtener_o_crear_sesion()
    history = cargar_historial_db(session_id)
    return {"status": "success", "history": history}


@app.delete("/api/chat/clear")
def clear_chat():
    session_id = obtener_o_crear_sesion()
    ok = borrar_historial_db(session_id)
    return {"status": "success" if ok else "error", "cleared": ok}