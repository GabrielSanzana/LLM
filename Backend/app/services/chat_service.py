from datetime import datetime
from app.db.supabase_client import supabase

def asegurar_nivel_inicial():
    """
    Verifica si existe el nivel 0. 
    Si no existe, lo inserta con los campos reales de tu esquema.
    """
    try:
        # Buscamos por id_nivel = 0 según tu instrucción
        res = supabase.table("Nivel").select("id_nivel").eq("id_nivel", 0).execute()
        
        if not res.data:
            print("🌱 Sembrando nivel inicial (id_nivel: 0)...")
            supabase.table("Nivel").insert({
                "id_nivel": 0,
                "titulo_ataque": "Introducción",
                "path_archivo_trafico": "default.pcap",
                "prompt_especifico": "Eres un tutor experto en redes..."
            }).execute()
    except Exception as e:
        print(f"⚠️ Nota en asegurar_nivel_inicial: {e}")

def obtener_o_crear_sesion(email_usuario: str):
    try:
        # 1. Garantizar que el nivel 0 existe
        asegurar_nivel_inicial()

        # 2. Obtener el ID del usuario (columna 'id' según tu imagen)
        res_user = supabase.table("Usuario").select("id").eq("correo", email_usuario).execute()
        if not res_user.data:
            raise Exception(f"Usuario no encontrado: {email_usuario}")
        
        id_usuario_db = res_user.data[0]["id"]

        # 3. Buscar sesión existente para este usuario y el nivel 0 (Chat General)
        res_sesion = supabase.table("Sesion_aprendizaje")\
            .select("id_sesion")\
            .eq("id_usuario", id_usuario_db)\
            .eq("id_nivel", 0)\
            .execute()
        
        if res_sesion.data:
            return res_sesion.data[0]["id_sesion"]
        
        # 4. Crear sesión vinculada al id_nivel 0
        nueva_sesion = supabase.table("Sesion_aprendizaje").insert({
            "id_usuario": id_usuario_db,
            "id_nivel": 0,  # Inicializado en 0
            "fecha_inicio": datetime.now().date().isoformat(), # Formato 'date' según tu imagen
            "modo": "Simulacion"
        }).execute()
        
        return nueva_sesion.data[0]["id_sesion"]
        
    except Exception as e:
        print(f"❌ Error en flujo de sesión: {e}")
        raise e

def guardar_mensaje_db(id_sesion: int, rol: str, contenido: str, nodo: str = "inicio"):
    try:
        # El rol en tu imagen es int8, asegúrate de enviar el ID del rol o cambiarlo a texto si lo prefieres
        # Si 'rol' debe ser un número (ej: 1 para user, 2 para ai), cámbialo aquí:
        val_rol = 1 if rol == "user" else 2

        supabase.table("Historial_chat").insert({
            "id_sesion": id_sesion,
            "rol": val_rol, 
            "contenido": contenido,
            "nodo_pedagogico": nodo,
            "enviado_en": datetime.now().isoformat()
        }).execute()
    except Exception as e:
        print(f"⚠️ Error al guardar mensaje: {e}")

def cargar_historial_db(id_sesion: int):
    try:
        res = supabase.table("Historial_chat")\
            .select("*")\
            .eq("id_sesion", id_sesion)\
            .order("id_mensaje", desc=False)\
            .execute()
        
        historial_para_frontend = []
        for msg in res.data:
            # Sincronizamos con lo que tu ChatView.jsx espera
            historial_para_frontend.append({
                "role": "user" if msg["rol"] == 1 else "assistant",
                "content": msg["contenido"],
                "nodo": msg["nodo_pedagogico"]
            })
        return historial_para_frontend
    except Exception as e:
        print(f"❌ Error al cargar historial: {e}")
        return []

def borrar_historial_db(id_sesion: int, nodo: str):
    try:
        if nodo == "inicio":
            supabase.table("Historial_chat")\
                .delete()\
                .eq("id_sesion", id_sesion)\
                .eq("nodo_pedagogico", "progreso_usuario")\
                .execute()

        supabase.table("Historial_chat")\
            .delete()\
            .eq("id_sesion", id_sesion)\
            .eq("nodo_pedagogico", nodo)\
            .execute()
        return True
    except Exception as e:
        print(f"❌ Error al borrar historial: {e}")
        return False

def obtener_progreso_usuario(id_sesion: int) -> dict:
    import json
    try:
        res = supabase.table("Historial_chat")\
            .select("contenido")\
            .eq("id_sesion", id_sesion)\
            .eq("nodo_pedagogico", "progreso_usuario")\
            .order("id_mensaje", desc=True)\
            .limit(1)\
            .execute()
        
        if res.data:
            return json.loads(res.data[0]["contenido"])
    except Exception as e:
        print(f"⚠️ Error al obtener progreso de usuario: {e}")
    
    # Progreso por defecto (Diagnóstico Global Inicial)
    return {
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

def guardar_progreso_usuario(id_sesion: int, progreso: dict):
    import json
    try:
        supabase.table("Historial_chat").insert({
            "id_sesion": id_sesion,
            "rol": 2, # Asistente/Sistema
            "contenido": json.dumps(progreso, ensure_ascii=False),
            "nodo_pedagogico": "progreso_usuario",
            "enviado_en": datetime.now().isoformat()
        }).execute()
    except Exception as e:
        print(f"❌ Error al guardar progreso de usuario: {e}")