from typing import List, Dict, Any


class LocalStore:
    """Simple store en memoria para un único chat.

    - `history` es una lista de mensajes con campos: role, content, nodo.
    - El store vive en memoria y se borra al terminar el proceso.
    """

    def __init__(self):
        self._session_id = "local"
        self.history: List[Dict[str, Any]] = []

    def get_session_id(self) -> str:
        return self._session_id

    def add_message(self, role: str, content: str, nodo: str = "inicio") -> None:
        self.history.append({"role": role, "content": content, "nodo": nodo})

    def get_history(self) -> List[Dict[str, Any]]:
        return [m.copy() for m in self.history]

    def clear_history(self, nodo: str = "inicio") -> bool:
        if nodo == "inicio" or nodo is None:
            self.history.clear()
            return True

        # eliminar solo mensajes de un nodo concreto
        self.history = [m for m in self.history if m.get("nodo") != nodo]
        return True
