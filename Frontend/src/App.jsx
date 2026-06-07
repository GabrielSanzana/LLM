import React, { useState } from 'react';
import Navbar from './components/Navbar';
import ChatView from './components/ChatView';

function App() {
  const [activeView, setActiveView] = useState('chat');

  return (
    <div className="h-screen flex flex-col overflow-hidden bg-gray-100">
      <Navbar activeView={activeView} switchView={setActiveView} />

      <main className="flex-1 overflow-hidden relative">
        {activeView === 'chat' && (
          <ChatView switchView={setActiveView} />
        )}
      </main>
    </div>
  );
}

export default App;