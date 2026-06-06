import os
import shutil
import threading
from contextlib import asynccontextmanager
from pathlib import Path
from pydantic import BaseModel

# pyrefly: ignore [missing-import]
from dotenv import load_dotenv
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware

BASE_DIR = Path(__file__).resolve().parents[2]
load_dotenv(BASE_DIR / ".env")

from app.scripts.ingest import run_ingestion
from app.models.schemas import ChatRequest
from app.services.agent import (
    get_tutor_response,
    init_rag_service,
    get_pcap_analysis_response,
    generate_scenario_data,
    get_simulator_response,
)
from app.services.analyzer import analyze_pcap
from app.services.auth_service import validar_credenciales, registrar_usuario
from app.services.chat_service import (
    obtener_o_crear_sesion,
    guardar_mensaje_db,
    cargar_historial_db,
)

class LoginRequest(BaseModel):
    email: str
    password: str

class RegisterRequest(BaseModel):
    nombre: str
    email: str
    password: str

class SimulatorRequest(BaseModel):
    email: str
    message: str
    nivel_id: int = 1
    memory_summary: str = ""
    pcap_data: dict | None = None

app_state = {
    "is_ready": False,
    "init_error": None,
    "pcaps": {}, # session_id -> pcap_data
    "phase": "starting",
}

def background_initialization():
    """Carga documentos y RAG en un hilo separado."""
    try:
        app_state["phase"] = "ingesting"
        print("🛠️ Iniciando ingesta de documentos...")
        run_ingestion()

        app_state["phase"] = "loading_rag"
        print("🧠 Cargando modelos RAG en memoria...")
        init_rag_service()

        app_state["is_ready"] = True
        app_state["phase"] = "ready"
        print("🚀 TUTOR LISTO: Base de conocimientos y modelos cargados.")
    except Exception as e:
        app_state["init_error"] = str(e)
        app_state["phase"] = "error"
        print(f"❌ Error crítico en inicialización: {e}")

@asynccontextmanager
async def lifespan(app: FastAPI):
    thread = threading.Thread(target=background_initialization, daemon=True)
    thread.start()
    yield
    print("Cerrando servidor...")

app = FastAPI(title="Cybersecurity Tutor API", lifespan=lifespan)

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

CAPTURES_DIR = BASE_DIR / "data" / "captures"
CAPTURES_DIR.mkdir(parents=True, exist_ok=True)

@app.get("/")
def read_root():
    return {"message": "Tutor de Ciberseguridad Activo"}

@app.get("/api/status")
async def get_status():
    return {
        "status": "ready" if app_state["is_ready"] else "initializing",
        "phase": app_state["phase"],
        "message": "Chat listo" if app_state["is_ready"] else "Inicializando base de conocimientos técnica...",
        "error": app_state["init_error"],
    }

@app.post("/api/login")
async def login_endpoint(credentials: LoginRequest):
    user = validar_credenciales(credentials.email, credentials.password)
    if not user:
        raise HTTPException(status_code=401, detail="Correo o contraseña incorrectos")
    return {"status": "success", "user": user}

@app.post("/api/register")
async def register_endpoint(user_data: RegisterRequest):
    nuevo_usuario = registrar_usuario(user_data.nombre, user_data.email, user_data.password)
    if not nuevo_usuario:
        raise HTTPException(status_code=400, detail="El correo ya existe o hubo un error")
    return {"status": "success", "message": "Usuario creado correctamente"}

@app.get("/api/scenario/{nivel_id}")
async def get_new_scenario(nivel_id: int):
    if not app_state["is_ready"]:
        raise HTTPException(status_code=503, detail="Sistema cargando...")

    try:
        scenario_data = generate_scenario_data(nivel_id)
        return {"status": "success", "data": scenario_data}
    except Exception as e:
        print(f"Error generando escenario: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/simulator/chat")
async def simulator_chat_endpoint(payload: SimulatorRequest):
    """
    NUEVO: chat del simulador de niveles con router GPT OSS 120B + tutor Llama 70B.
    No toca el chat general ni el análisis PCAP existentes.
    """
    if not app_state["is_ready"]:
        raise HTTPException(status_code=503, detail="La IA aún se está cargando.")

    try:
        result = get_simulator_response(
            user_message=payload.message,
            pcap_data=payload.pcap_data,
            history=None,
            memory_summary=payload.memory_summary,
        )
        return {"status": "success", **result}
    except Exception as e:
        print(f"Error en simulator_chat_endpoint: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/chat/history/{email}")
async def get_chat_history(email: str):
    try:
        id_sesion = obtener_o_crear_sesion(email)
        historial = cargar_historial_db(id_sesion)
        return {"status": "success", "history": historial}
    except Exception:
        return {"status": "success", "history": []}

@app.delete("/api/chat/history/{email}")
async def delete_chat_history(email: str, nodo_actual: str = "inicio"):
    try:
        from app.services.chat_service import borrar_historial_db
        id_sesion = obtener_o_crear_sesion(email)
        exito = borrar_historial_db(id_sesion, nodo_actual)
        if exito:
            return {"status": "success", "message": "Historial borrado"}
        else:
            raise HTTPException(status_code=500, detail="Error al borrar historial en DB")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/chat/progress/{email}")
async def get_user_progress(email: str):
    if not app_state["is_ready"]:
        raise HTTPException(status_code=503, detail="Sistema en inicialización.")
    try:
        from app.services.chat_service import obtener_progreso_usuario
        id_sesion = obtener_o_crear_sesion(email)
        progreso = obtener_progreso_usuario(id_sesion)
        return {"status": "success", "progreso": progreso}
    except Exception as e:
        print(f"Error en get_user_progress: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/chat")
async def chat_endpoint(request: ChatRequest):
    if not app_state["is_ready"]:
        raise HTTPException(status_code=503, detail="La IA aún se está cargando.")

    try:
        id_sesion = obtener_o_crear_sesion(request.email)
        guardar_mensaje_db(id_sesion, "user", request.message, request.nodo_actual)

        historial_db = cargar_historial_db(id_sesion)
        historial_nodo = [
            {"role": m["role"], "content": m["content"]}
            for m in historial_db
            if m["nodo"] == request.nodo_actual
        ]
        
        if request.nodo_actual == "analisis_pcap":
            pcap_data = app_state["pcaps"].get(id_sesion)
            if not pcap_data:
                raise HTTPException(status_code=400, detail="No hay datos de PCAP en memoria para esta sesión. Sube el archivo nuevamente.")
            result = get_pcap_analysis_response(pcap_data, history=historial_nodo, user_message=request.message)
            progreso_data = None
        else:
            result = get_tutor_response(request.message, history=historial_nodo, id_sesion=id_sesion)
            progreso_data = result.get("progreso")
            
        response_text = result["response"]
        router_debug = result["router"]

        guardar_mensaje_db(id_sesion, "assistant", response_text, request.nodo_actual)

        res_body = {
            "status": "success", 
            "response": response_text, 
            "router": router_debug
        }
        if progreso_data:
            res_body["progreso"] = progreso_data

        return res_body
    except Exception as e:
        print(f"Error en chat_endpoint: {e}")
        raise HTTPException(status_code=500, detail=str(e))



@app.post("/api/analyze")
async def analyze_endpoint(email: str, file: UploadFile = File(...), nodo_actual: str = "analisis_pcap"):
    if not app_state["is_ready"]:
        raise HTTPException(status_code=503, detail="Sistema en inicialización.")

    file_path = CAPTURES_DIR / file.filename
    try:
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        pcap_data = analyze_pcap(str(file_path))
        if isinstance(pcap_data, str) and "Error" in pcap_data:
            return {"status": "error", "message": pcap_data}

        id_sesion = obtener_o_crear_sesion(email)
        app_state["pcaps"][id_sesion] = pcap_data
        
        user_msg = f"Archivo analizado: {file.filename}"
        guardar_mensaje_db(id_sesion, "user", user_msg, nodo_actual)

        result = get_pcap_analysis_response(pcap_data)
        narrative = result["response"]
        guardar_mensaje_db(id_sesion, "assistant", narrative, nodo_actual)

        return {
            "status": "success",
            "narrative": narrative,
            "technical_details": pcap_data,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if file_path.exists():
            file_path.unlink()