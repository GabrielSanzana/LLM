from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    email: str  # Para saber de quién es el mensaje
    message: str
    nodo_actual: str = "inicio"