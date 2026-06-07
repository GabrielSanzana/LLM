# Proyecto LLM

Este proyecto está dividido en dos partes principales:
- **Backend**: Construido con Python y FastAPI.
- **Frontend**: Construido con React y Vite.

A continuación, se detallan las instrucciones paso a paso para configurar y ejecutar ambas partes por primera vez.

---

## Crear .env 
   ```powershell
   copy .env.copy .env
   ```

## 📅 Configuración de Google Calendar API (Recordatorios)

El sistema incluye integración con Google Calendar para agendar recordatorios. Para habilitarlo, debes configurar las credenciales de una **Cuenta de Servicio (Service Account)** de Google:

### 1. Generar el archivo de credenciales (`credentials.json`)
1. Ingresa a [Google Cloud Console](https://console.cloud.google.com/).
2. Crea un nuevo proyecto (o selecciona uno existente).
3. Dirígete a **API y servicios** > **Biblioteca**, busca **Google Calendar API** y haz clic en **Habilitar**.
4. Ve a **IAM y administración** > **Cuentas de servicio** y haz clic en **Crear cuenta de servicio**.
5. Completa los detalles (ej. nombre: `calendar-agent`), haz clic en **Crear y continuar** y luego en **Listo**.
6. Haz clic en la cuenta de servicio recién creada en la lista y entra a la pestaña **Claves** (Keys).
7. Haz clic en **Agregar clave** > **Crear clave nueva**. Selecciona el formato **JSON** y presiona **Crear**.
8. Se descargará un archivo `.json`. Cámbiale el nombre a `credentials.json` y colócalo en la carpeta **`Backend/`** del proyecto (`Backend/credentials.json`).

> [!WARNING]
> Este archivo contiene llaves privadas y está configurado en el [`.gitignore`]para que no sea subido a Git. **Nunca lo expongas en un repositorio público.**

### 2. Compartir tu Calendario con la Cuenta de Servicio
Dado que la cuenta de servicio actúa como un usuario virtual independiente, debes otorgarle permisos explícitos sobre el calendario donde deseas crear los eventos:
1. Abre tu archivo `credentials.json` recién descargado y copia el valor del campo `"client_email"` (que termina en `@tu-proyecto.iam.gserviceaccount.com`).
2. Abre [Google Calendar](https://calendar.google.com/) en tu navegador.
3. En la barra lateral izquierda, busca el calendario que vas a utilizar, haz clic en los tres puntos y selecciona **Configuración y uso compartido**.
4. Desplázate hasta la sección **Compartir con personas o grupos específicos** y haz clic en **Agregar personas**.
5. Pega el correo de la cuenta de servicio copiado en el paso 1.
6. En la opción de permisos, selecciona **Realizar cambios en eventos** (este permiso es obligatorio para que el agente pueda agendar).
7. Guarda los cambios.


## 🚀 1. Configuración del Backend (Python/FastAPI)

El backend requiere Python instalado en tu sistema.

### Pasos para la primera vez:

1. **Abre una terminal** y navega a la carpeta del backend:
   ```powershell
   cd Backend
   ```
2. **Crea el entorno virtual** (solo la primera vez):
   ```powershell
   python -m venv venv
   ```
3. **Activa el entorno virtual**:
   ```powershell
   .\venv\Scripts\Activate.ps1
   ```
   > ⚠️ Si ves un error de permisos, ejecuta primero:
   > `Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser`

4. **Instala las dependencias**:
   Instala todas las librerías necesarias leyendo el archivo `requirements.txt`:
   ```powershell
   pip install -r requirements.txt
   ```

### ¿Cómo ejecutar el servidor Backend en el día a día?
Cada vez que vayas a trabajar en el proyecto, abre tu terminal, navega a la carpeta `Backend`, **activa el entorno virtual** y ejecuta el servidor:
```powershell
cd Backend
.\venv\Scripts\Activate.ps1
python -m uvicorn app.main:app --reload
```
El backend estará corriendo en: `http://localhost:8000` (o el puerto que te indique la terminal).

---

### Comando para crear requirements.txt
```powershell
python -m pip freeze > requirements.txt
```

## 🎨 2. Configuración del Frontend (React/Vite)

El frontend requiere tener instalado [Node.js](https://nodejs.org/) en tu computadora.

### Pasos para la primera vez:

1. **Abre una nueva terminal** (es mejor tener una terminal para el backend y otra para el frontend) y navega a la carpeta del frontend:
   ```powershell
   cd Frontend
   ```

2. **Instala las dependencias**:
   Ejecuta el siguiente comando para que `npm` descargue todas las librerías definidas en el archivo `package.json`:
   ```powershell
   npm install
   ```
   *(Esto creará una carpeta llamada `node_modules` que contiene todas las librerías).*

### ¿Cómo ejecutar el servidor Frontend en el día a día?
Cada vez que vayas a trabajar, simplemente abre la terminal en la carpeta `Frontend` y ejecuta:
```powershell
npm run dev
```
El frontend estará corriendo normalmente en: `http://localhost:5173`

---

## 💡 Resumen para tu flujo de trabajo diario
Para que el proyecto completo funcione, necesitas **dos terminales abiertas**:

**Terminal 1 (Backend):**
```powershell
cd Backend
.\venv\Scripts\Activate.ps1
python -m uvicorn app.main:app --reload
```

**Terminal 2 (Frontend):**
```powershell
cd Frontend
npm run dev
```
