import { useState } from "react";

export default function LoginModal({ onClose, onLoginSuccess }) {
  const [correo, setCorreo] = useState("");
  const [password, setPassword] = useState("");
  const [errorMsg, setErrorMsg] = useState("");
  const [isLoading, setIsLoading] = useState(false);

  const handleLogin = async (e) => {
    if (e) e.preventDefault();
    setErrorMsg("");
    setIsLoading(true);

    try {
      const response = await fetch("http://localhost:8000/api/login", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ email: correo, password }),
      });

      const data = await response.json();

      if (!response.ok) {
        throw new Error(data.detail || "Error al iniciar sesión");
      }

      // ==========================================
      // PERSISTENCIA CORREGIDA
      // ==========================================
      
      // IMPORTANTE: Usamos data.user.correo porque así viene de tu tabla Usuario
      if (data.user && data.user.correo) {
        localStorage.setItem("userEmail", data.user.correo);
        localStorage.setItem("userName", data.user.nombre || "Usuario");
        
        console.log("Sesión guardada para:", data.user.correo);
      } else {
        throw new Error("El servidor no devolvió los datos del usuario correctamente.");
      }

      setCorreo("");
      setPassword("");
      
      // Notificamos éxito
      onLoginSuccess(data.user); 
      
    } catch (error) {
      console.error("Error en Login:", error);
      setErrorMsg(error.message);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 bg-black/40 backdrop-blur-sm flex items-center justify-center z-[100] p-4">
      <div className="bg-white rounded-2xl shadow-2xl w-full max-w-[400px] p-8 animate-in fade-in zoom-in duration-200 border border-gray-100">
        
        <h2 className="text-2xl font-bold text-gray-800 mb-2">Bienvenido de nuevo</h2>
        <p className="text-gray-500 text-sm mb-6">Ingresa tus credenciales para acceder al tutor.</p>

        <form onSubmit={handleLogin} className="flex flex-col gap-4">
          <div className="space-y-1">
            <label className="text-xs font-semibold text-gray-500 ml-1">Correo Electrónico</label>
            <input
              placeholder="nombre@ejemplo.com"
              type="email"
              className="w-full px-4 py-3 bg-gray-50 border border-gray-200 rounded-xl outline-none focus:border-indigo-600 focus:bg-white transition-all"
              value={correo}
              onChange={(e) => setCorreo(e.target.value)}
              disabled={isLoading}
              required
            />
          </div>

          <div className="space-y-1">
            <label className="text-xs font-semibold text-gray-500 ml-1">Contraseña</label>
            <input
              placeholder="••••••••"
              type="password"
              className="w-full px-4 py-3 bg-gray-50 border border-gray-200 rounded-xl outline-none focus:border-indigo-600 focus:bg-white transition-all"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              disabled={isLoading}
              required
            />
          </div>

          {errorMsg && (
            <div className="bg-red-50 border-l-4 border-red-500 p-3 rounded">
              <p className="text-red-600 text-xs font-bold">{errorMsg}</p>
            </div>
          )}

          <button
            type="submit"
            disabled={isLoading}
            className={`w-full py-4 rounded-xl text-white font-bold shadow-lg shadow-indigo-100 transition-all active:scale-[0.98] mt-2 ${
              isLoading ? "bg-gray-400" : "bg-indigo-600 hover:bg-indigo-700"
            }`}
          >
            {isLoading ? (
              <span className="flex items-center justify-center gap-2">
                <svg className="animate-spin h-5 w-5 text-white" viewBox="0 0 24 24">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none"></circle>
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                </svg>
                Verificando...
              </span>
            ) : "Entrar al Chat"}
          </button>

          <button
            type="button"
            onClick={onClose}
            className="text-gray-400 text-sm font-medium hover:text-gray-600 transition-colors mt-2"
          >
            Volver atrás
          </button>
        </form>
      </div>
    </div>
  );
}