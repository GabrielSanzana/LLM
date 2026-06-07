import React from "react";

export default function Navbar({ activeView, switchView }) {
  return (
    <nav className="bg-white border-b border-gray-200 px-8 py-3 flex justify-between items-center shadow-sm z-50">

      {/* LOGO */}
      <div className="flex items-center gap-3">
        <div className="bg-indigo-600 p-2 rounded-xl shadow-lg shadow-indigo-200">
          <svg xmlns="http://www.w3.org/2000/svg" className="h-6 w-6 text-white" fill="none" viewBox="0 0 24 24"
               stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2"
                  d="M13 10V3L4 14h7v7l9-11h-7z" />
          </svg>
        </div>

        <span className="text-xl font-bold text-gray-800 tracking-tight">
          NetTutor <span className="text-indigo-600">AI</span>
        </span>
      </div>

      {/* NAV (solo Chat) */}
      <div className="flex gap-1">
        <button onClick={() => switchView('chat')}
          className={`px-4 py-2 rounded-lg text-sm font-semibold transition-all hover:bg-gray-100 ${activeView === 'chat' ? 'active-nav' : 'text-gray-600'}`}>
          Chat General
        </button>
      </div>

      {/* No auth in simplified app */}
      <div className="flex items-center gap-3">
        <span className="text-sm font-semibold text-gray-700">Usuario: Invitado</span>
      </div>

    </nav>
  );
}