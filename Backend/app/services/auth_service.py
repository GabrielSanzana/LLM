from app.db.supabase_client import supabase

def validar_credenciales(email, password):
    try:
        response = supabase.table("Usuario") \
            .select("id, nombre, correo") \
            .eq("correo", email) \
            .eq("clave", password) \
            .single() \
            .execute()
        
        return response.data
    except Exception as e:
        print(f"Error de autenticación: {e}")
        return None
    
def registrar_usuario(nombre, email, password):
    try:
        # 1. Verificar si el usuario ya existe
        existe = supabase.table("Usuario").select("*").eq("correo", email).execute()
        if existe.data:
            return None

        # 2. Insertar nuevo usuario
        # Nota: Asegúrate de que los nombres de las columnas coincidan con tu Supabase
        nuevo = supabase.table("Usuario").insert({
            "nombre": nombre,
            "correo": email,
            "clave": password  # En producción deberías usar hashing (ej. bcrypt)
        }).execute()

        return nuevo.data
    except Exception as e:
        print(f"Error al registrar: {e}")
        return None