import React, { useState } from 'react';

const RegisterModal = ({ onClose, onSwitchToLogin }) => {
  const [nombre, setNombre] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setLoading(true);
    try {
      const response = await fetch("http://127.0.0.1:8000/api/register", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ nombre, email, password }),
      });

      if (response.ok) {
        alert("¡Registro exitoso! Ahora puedes iniciar sesión.");
        onSwitchToLogin();
      } else {
        alert("Error al registrar. Revisa si el correo ya existe.");
      }
    } catch (error) {
      alert("Error de conexión con el servidor.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 bg-black/40 backdrop-blur-sm flex items-center justify-center z-[100]">
      <div className="bg-white rounded-2xl shadow-2xl w-full max-w-[400px] p-8 animate-in fade-in zoom-in duration-200">
        
        {/* Título */}
        <h2 className="text-2xl font-bold text-gray-800 mb-6">Registrarse</h2>

        <form onSubmit={handleSubmit} className="flex flex-col gap-4">
          
          <input
            type="text"
            placeholder="Nombre"
            className="w-full px-4 py-3 border border-gray-300 rounded-lg outline-none focus:border-indigo-600 transition-colors"
            value={nombre}
            onChange={(e) => setNombre(e.target.value)}
            required
          />

          <input
            type="email"
            placeholder="Correo"
            className="w-full px-4 py-3 border border-gray-300 rounded-lg outline-none focus:border-indigo-600 transition-colors"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
          />

          <input
            type="password"
            placeholder="Contraseña"
            className="w-full px-4 py-3 border border-gray-300 rounded-lg outline-none focus:border-indigo-600 transition-colors"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
          />

          {/* Botón Principal (Mismo color índigo que tu imagen) */}
          <button
            type="submit"
            disabled={loading}
            className="w-full bg-[#4f46e5] text-white py-3 rounded-lg font-bold hover:bg-[#4338ca] transition-all shadow-md active:scale-[0.98] disabled:opacity-70 mt-2"
          >
            {loading ? 'Creando cuenta...' : 'Registrar'}
          </button>

          {/* Opción para volver al login */}
          <p className="text-center text-sm text-gray-500 mt-2">
            ¿Ya tienes cuenta?{' '}
            <button 
              type="button" 
              onClick={onSwitchToLogin}
              className="text-indigo-600 font-bold hover:underline"
            >
              Inicia sesión
            </button>
          </p>

          {/* Botón Cancelar (Mismo estilo que tu imagen) */}
          <button
            type="button"
            onClick={onClose}
            className="text-gray-500 text-sm font-medium hover:text-gray-700 transition-colors mt-2"
          >
            Cancelar
          </button>
        </form>
      </div>
    </div>
  );
};

export default RegisterModal;