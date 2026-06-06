import React, { useState } from 'react';
import Navbar from './components/Navbar';
import AnalysisView from './components/AnalysisView';
import ChatView from './components/ChatView';
import SimulatorView from './components/SimulatorView';
import LoginModal from './components/LoginModal';
import RegisterModal from './components/RegisterModal';

function App() {
  // --- ESTADOS ---
  const [activeView, setActiveView] = useState('analysis');
  const [showLoginModal, setShowLoginModal] = useState(false);
  const [showRegisterModal, setShowRegisterModal] = useState(false);
  
  // Inicialización de usuario desde LocalStorage
  const [user, setUser] = useState(() => {
    const savedUser = localStorage.getItem("user");
    try {
      return savedUser ? JSON.parse(savedUser) : null;
    } catch (e) {
      return null;
    }
  });

  // --- LÓGICA DE IDENTIDAD (La "Key" del Chat) ---
  // Este valor cambia cuando el usuario entra o sale, forzando al Chat a limpiarse.
  const chatKey = user?.email || 'invitado';

  // --- HANDLERS ---
  const handleLoginSuccess = (userData) => {
    // 1. Guardamos el objeto completo
    localStorage.setItem("user", JSON.stringify(userData));
    
    // 2. Guardamos el email por separado para que el componente ChatView lo use fácilmente
    if (userData.email) {
      localStorage.setItem("userEmail", userData.email);
    }
    
    setUser(userData);
    setShowLoginModal(false);
  };

  const handleLogout = () => {
    // 1. Limpieza total de persistencia
    localStorage.removeItem("user");
    localStorage.removeItem("userEmail");
    
    // 2. Limpieza de estado de React
    setUser(null);
    
    // 3. Reset de vista (vuelve a análisis para asegurar el desmontaje del chat)
    setActiveView('analysis');
  };

  return (
    <div className="h-screen flex flex-col overflow-hidden bg-gray-100">
      
      {/* BARRA DE NAVEGACIÓN */}
      <Navbar
        activeView={activeView}
        switchView={setActiveView}
        onLoginClick={() => setShowLoginModal(true)}
        onRegisterClick={() => setShowRegisterModal(true)}
        user={user}
        onLogout={handleLogout}
      />

      {/* MODAL DE LOGIN */}
      {showLoginModal && (
        <LoginModal
          onClose={() => setShowLoginModal(false)}
          onLoginSuccess={handleLoginSuccess}
        />
      )}

      {/* MODAL DE REGISTRO */}
      {showRegisterModal && (
        <RegisterModal
          onClose={() => setShowRegisterModal(false)}
          onSwitchToLogin={() => {
            setShowRegisterModal(false);
            setShowLoginModal(true);
          }}
        />
      )}

      {/* ÁREA PRINCIPAL DE CONTENIDO */}
<main className="flex-1 overflow-hidden relative">
  {activeView === 'analysis' && <AnalysisView />}
  
{activeView === 'chat' && (
  <ChatView 
    key={user ? user.email : 'invitado'} // Si user cambia, el chat SE REINICIA sí o sí
    currentUser={user} // Pasamos el usuario como prop para mayor seguridad
    switchView={setActiveView}
  />
)}
  
  {activeView === 'sim' && <SimulatorView />}
</main>

    </div>
  );
}

export default App;