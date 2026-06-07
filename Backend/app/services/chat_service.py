"""Chat service simplificado que usa una memoria local en proceso.

Este módulo reemplaza la dependencia de Supabase y mantiene un historial
simple en memoria para un único chat. La información se perderá al apagar
el servidor (comportamiento intencional: memoria efímera).
"""

from typing import List, Dict, Any
from app.db.local_store import LocalStore


store = LocalStore()


def obtener_o_crear_sesion() -> str:
    """Devuelve el id de sesión único (local)."""
    return store.get_session_id()


def guardar_mensaje_db(id_sesion: str, rol: str, contenido: str, nodo: str = "inicio") -> None:
    store.add_message(rol, contenido, nodo=nodo)


def cargar_historial_db(id_sesion: str) -> List[Dict[str, Any]]:
    return store.get_history()


def borrar_historial_db(id_sesion: str = None, nodo: str = "inicio") -> bool:
    return store.clear_history(nodo=nodo)


def obtener_progreso_usuario(id_sesion: str) -> dict:
    # No se mantiene progreso pedagógico en esta versión simplificada.
    return {}


def guardar_progreso_usuario(id_sesion: str, progreso: dict) -> None:
    # No persistimos progreso en la versión efímera.
    return
