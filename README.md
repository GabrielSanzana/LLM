# NetTutor

Este proyecto está dividido en dos partes principales:
- **Backend**: Construido con Python y FastAPI.
- **Frontend**: Construido con React y Vite.

A continuación, se detallan las instrucciones paso a paso para configurar y ejecutar ambas partes por primera vez.

---

## Crear .env 
   ```powershell
   copy .env.copy .env
   ```



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
