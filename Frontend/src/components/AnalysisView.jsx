import React, { useState, useRef, useEffect } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

export default function AnalysisView() {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState('');
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const fileInputRef = useRef(null);
  const scrollRef = useRef(null);
  
  // =========================
  // AUTO SCROLL
  // =========================
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages, isAnalyzing, isLoading]);

  // =========================
  // CARGAR HISTORIAL
  // =========================
  useEffect(() => {
    const cargarHistorial = async () => {
      const emailEnStorage = localStorage.getItem("userEmail");
      if (!emailEnStorage || emailEnStorage === "undefined") {
        setMessages([]);
        return;
      }
      try {
        const response = await fetch(`http://localhost:8000/api/chat/history/${emailEnStorage}`);
        if (response.ok) {
          const data = await response.json();
          if (data.status === "success" && data.history) {
            // Filtramos solo los de analisis_pcap o los agregamos todos? 
            // Para mantener consistencia con ChatView, obtenemos el historial completo.
            // Si el backend no filtra por nodo, todos se ven. Idealmente el backend filtraria, 
            // pero por ahora lo mostramos.
            const historialFormateado = data.history.filter(msg => msg.nodo === 'analisis_pcap').map(msg => ({
              role: msg.role,
              content: msg.content
            }));
            setMessages(historialFormateado);
          }
        }
      } catch (error) {
        console.error("Error al cargar:", error);
      }
    };
    cargarHistorial();
  }, []);

  const handleFileChange = async (e) => {
    const file = e.target.files[0];
    if (!file) return;

    const emailActual = localStorage.getItem("userEmail");
    if (!emailActual || emailActual === "undefined") {
      alert("Error: No se detectó tu sesión. Por favor, inicia sesión de nuevo.");
      return;
    }

    setIsAnalyzing(true);
    setMessages(prev => [...prev, { role: 'system', content: `Analizando archivo: ${file.name}...` }]);

    const formData = new FormData();
    formData.append('file', file);
    formData.append('email', emailActual);
    formData.append('nodo_actual', 'analisis_pcap');

    try {
      const response = await fetch('http://localhost:8000/api/analyze?email=' + encodeURIComponent(emailActual) + '&nodo_actual=analisis_pcap', {
        method: 'POST',
        body: formData,
      });

      const data = await response.json();

      if (data.status === 'success') {
        setMessages(prev => [
          ...prev,
          { 
            role: 'assistant', 
            content: data.narrative
          }
        ]);
      } else {
        setMessages(prev => [...prev, { role: 'system', content: `Error: ${data.message}` }]);
      }
    } catch (error) {
      setMessages(prev => [...prev, { role: 'system', content: 'Error en la conexión con el servidor.' }]);
    } finally {
      setIsAnalyzing(false);
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  };

  const handleSend = async () => {
    const emailActual = localStorage.getItem("userEmail");
    if (!emailActual || emailActual === "undefined") {
      alert("Error: No se detectó tu sesión. Por favor, inicia sesión de nuevo.");
      return;
    }

    if (!input.trim() || isLoading || isAnalyzing) return;

    const userMsg = input;
    setInput('');

    setMessages(prev => [...prev, { role: 'user', content: userMsg }]);
    setIsLoading(true);

    try {
      const response = await fetch('http://localhost:8000/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          email: emailActual,
          message: userMsg,
          nodo_actual: "analisis_pcap"
        })
      });

      if (!response.ok) {
        const errData = await response.json();
        throw new Error(errData.detail || `Error ${response.status}`);
      }

      const data = await response.json();
      console.log("Router Intent (Analysis Chat):", data.router);

      setMessages(prev => [...prev, {
        role: 'assistant',
        content: data.response || 'El tutor no devolvió contenido.'
      }]);
    } catch (error) {
      console.error("Error al enviar mensaje:", error);
      setMessages(prev => [...prev, {
        role: 'assistant',
        content: `Error del sistema: ${error.message}`
      }]);
    } finally {
      setIsLoading(false);
    }
  };

  const handleDeleteHistory = async () => {
    if (!window.confirm("¿Estás seguro de que deseas borrar todo el historial de este análisis?")) return;
    
    const emailActual = localStorage.getItem("userEmail");
    try {
      const res = await fetch(`http://localhost:8000/api/chat/history/${encodeURIComponent(emailActual)}?nodo_actual=analisis_pcap`, {
        method: 'DELETE'
      });
      if (res.ok) {
        setMessages([]);
      } else {
        alert("Error al borrar el historial");
      }
    } catch (err) {
      alert("Error de conexión");
    }
  };

  return (
    <div className="h-full flex flex-col p-6 fade-in items-center justify-center">
      <div className="w-full max-w-4xl h-full flex flex-col bg-white rounded-3xl shadow-xl overflow-hidden border border-gray-100">
        
        {/* HEADER */}
        <div className="p-6 border-b flex items-center justify-between gap-4 bg-gray-50/50 flex-shrink-0">
          <div className="flex items-center gap-4">
            <div className="w-10 h-10 rounded-full bg-indigo-600 flex items-center justify-center text-white font-bold shadow-lg shadow-indigo-200">
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
              </svg>
            </div>
            <div>
              <h3 className="font-bold text-gray-800 text-sm">Análisis de Tráfico Forense</h3>
              <p className="text-xs text-gray-400 font-medium">Sube tu captura y pregunta al tutor.</p>
            </div>
          </div>
          <div className="flex gap-2">
            {messages.length > 0 && (
              <button 
                onClick={handleDeleteHistory}
                disabled={isAnalyzing || isLoading}
                className="bg-red-50 text-red-600 hover:bg-red-100 px-4 py-2 rounded-xl font-bold shadow-sm transition-all flex items-center gap-2 text-sm border border-red-200"
                title="Borrar Historial"
              >
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                </svg>
              </button>
            )}
            <button 
              onClick={() => fileInputRef.current.click()}
              disabled={isAnalyzing}
              className={`${isAnalyzing ? 'bg-gray-400' : 'bg-indigo-600 hover:bg-indigo-700'} text-white px-4 py-2 rounded-xl font-bold shadow-md transition-all flex items-center gap-2 text-sm`}
            >
              {isAnalyzing ? 'Procesando...' : 'Subir .pcap'}
            </button>
          </div>
          <input type="file" ref={fileInputRef} className="hidden" onChange={handleFileChange} accept=".pcap,.pcapng" />
        </div>

        {/* CHAT AREA */}
        <div ref={scrollRef} className="flex-1 p-8 space-y-6 overflow-y-auto custom-scrollbar min-h-0 bg-slate-50/30">
          {messages.length === 0 && (
            <p className="text-center text-gray-400 mt-20 italic">
              Sube un archivo .pcap para comenzar el análisis o haz una pregunta sobre el tráfico de red.
            </p>
          )}

          {messages.map((m, i) => (
            <div key={i} className={`fade-in flex ${m.role === 'user' ? 'justify-end' : 'justify-start'}`}>
              
              {m.role === 'system' && (
                <div className="w-full text-center">
                  <div className="inline-block bg-indigo-50 text-indigo-700 p-2 rounded-xl text-sm italic border border-indigo-100">
                    {m.content}
                  </div>
                </div>
              )}

              {(m.role === 'user' || m.role === 'assistant') && (
                <div className={`max-w-[80%] p-4 rounded-2xl text-sm leading-relaxed ${
                  m.role === 'user'
                    ? 'bg-indigo-600 text-white shadow-md rounded-tr-none whitespace-pre-wrap'
                    : 'bg-white border border-gray-200 text-gray-800 shadow-sm rounded-tl-none'
                }`}>
                  {m.role === 'user' ? (
                    m.content
                  ) : (
                    <div className="chat-markdown">
                      <ReactMarkdown remarkPlugins={[remarkGfm]}>{m.content}</ReactMarkdown>
                    </div>
                  )}
                </div>
              )}

            </div>
          ))}

          {(isAnalyzing || isLoading) && (
             <div className="flex justify-start">
               <div className="text-xs text-indigo-500 animate-pulse font-bold bg-indigo-50 px-3 py-1 rounded-full">
                 Tutor pensando...
               </div>
             </div>
          )}
        </div>

        {/* INPUT */}
        {messages.length > 0 && (
          <div className="p-6 border-t bg-white flex-shrink-0 fade-in">
            <div className="relative flex gap-2">
              <input
                type="text"
                value={input}
                disabled={isAnalyzing || isLoading}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && handleSend()}
                placeholder={isAnalyzing ? 'Analizando archivo...' : 'Escribe tu duda sobre el análisis aquí...'}
                className="flex-1 bg-gray-100 border-none rounded-2xl py-4 px-6 outline-none focus:ring-2 focus:ring-indigo-500 transition-all disabled:opacity-50"
              />
              <button
                disabled={isAnalyzing || isLoading}
                onClick={handleSend}
                className="bg-indigo-600 text-white p-4 rounded-2xl hover:bg-indigo-700 transition-colors disabled:opacity-50 shadow-lg flex items-center justify-center"
              >
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M14 5l7 7m0 0l-7 7m7-7H3" />
                </svg>
              </button>
            </div>
          </div>
        )}

      </div>
    </div>
  );
}