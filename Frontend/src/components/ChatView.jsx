import React, { useState, useEffect, useRef } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

export default function ChatView({ switchView }) {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [backendReady, setBackendReady] = useState(false);
  const [backendMessage, setBackendMessage] = useState('Inicializando servicio...');

  const scrollRef = useRef(null);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages, isLoading]);

  useEffect(() => {
    let mounted = true;
    const checkBackend = async () => {
      try {
        const res = await fetch('http://127.0.0.1:8000/api/status');
        const data = await res.json();
        if (!mounted) return;
        if (data.status === 'ready') {
          setBackendReady(true);
          setBackendMessage('Servicio listo');
        } else {
          setBackendReady(false);
          setBackendMessage(data.message || 'Inicializando...');
        }
      } catch (err) {
        if (!mounted) return;
        setBackendReady(false);
        setBackendMessage('Backend desconectado');
      }
    };

    checkBackend();
    const id = setInterval(checkBackend, 2000);
    return () => { mounted = false; clearInterval(id); };
  }, []);

  useEffect(() => {
    const loadHistory = async () => {
      try {
        const res = await fetch('http://127.0.0.1:8000/api/chat/history');
        if (!res.ok) return;
        const data = await res.json();
        if (data.status === 'success' && data.history) {
          // Cargamos solo el historial limpio para la vista del usuario
          setMessages(data.history.map(m => ({ role: m.role, content: m.content })));
        }
      } catch (err) {
        console.error('Error cargando historial', err);
      }
    };
    loadHistory();
  }, []);

  const handleSend = async () => {
    if (!input.trim() || isLoading) return;
    if (!backendReady) {
      setMessages(prev => [...prev, { role: 'assistant', content: 'Servicio no disponible.' }]);
      return;
    }

    const userMsg = input.trim();
    setInput('');
    setMessages(prev => [...prev, { role: 'user', content: userMsg }]);
    setIsLoading(true);

    try {
      const res = await fetch('http://127.0.0.1:8000/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: userMsg })
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();

      // =======================================================================
      // PROCESAMIENTO Y AGRUPACIÓN EN CONSOLE.LOG DEL FLUJO PLAN-AND-EXECUTE
      // =======================================================================
      if (data.trace && Array.isArray(data.trace)) {
        console.group(`%c📋 Plan-and-Execute: Flujo para "${userMsg}"`, "color: #0f766e; font-weight: bold; font-size: 13px;");
        
        data.trace.forEach((step) => {
          if (step.type === "plan_generated") {
            console.group(`%c🗺️ Plan Generado por el Planificador`, "color: #0d9488; font-weight: bold;");
            step.plan.forEach((p) => {
              console.log(
                `%cPaso ${p.step_id}%c: ${p.description} %c(Herramienta esperada: ${p.tool_expected})`,
                "font-weight: bold; color: #0f766e;",
                "color: #1f2937;",
                "color: #6b7280; font-style: italic;"
              );
            });
            console.groupEnd();
          }
          else if (step.type === "executing_step") {
            console.group(`%c🚀 Ejecutando Paso ${step.step_id}: "${step.description}"`, "color: #b45309; font-weight: bold;");
          }
          else if (step.type === "tool_call") {
            console.log(`%cHerramienta llamada:%c ${step.function}`, "font-weight: bold; color: #4b5563;", "color: #047857; font-family: monospace;");
            console.log(`%cArgumentos enviados:`, "font-weight: bold; color: #4b5563;", step.arguments);
          }
          else if (step.type === "mqr_generated") {
            console.log(`%c🔀 Multi-Query Rewriting (Variaciones RAG):`, "font-weight: bold; color: #6366f1;", step.queries);
          }
          else if (step.type === "tool_message") {
            console.log(`%cResultado de Herramienta:`, "font-weight: bold; color: #4b5563;");
            console.log(`%c${step.result}`, "color: #1e293b;");
            console.groupEnd(); // Cierra el grupo del paso actual
          }
          else if (step.type === "step_completed_text") {
            console.log(`%cResultado del paso (Texto):`, "font-weight: bold; color: #4b5563;");
            console.log(`%c${step.content}`, "color: #1e293b;");
            console.groupEnd(); // Cierra el grupo del paso actual
          }
          else if (step.type === "step_error") {
            console.error(`❌ Error en Paso ${step.step_id}: ${step.error}`);
            console.groupEnd(); // Cierra el grupo del paso actual
          }
          else if (step.type === "final_answer") {
            console.log(`%c✅ Síntesis Final Generada por el Asistente:`, "font-weight: bold; color: #0d9488;", step.content);
          }
        });
        
        console.groupEnd();
      }
      // =======================================================================

      // Añadimos solo la respuesta limpia a la UI del usuario
      setMessages(prev => [...prev, { role: 'assistant', content: data.response || '' }]);
      
    } catch (err) {
      console.error(err);
      setMessages(prev => [...prev, { role: 'assistant', content: `Error: ${err.message}` }]);
    } finally {
      setIsLoading(false);
    }
  };

  const handleClear = async () => {
    if (!window.confirm('¿Borrar historial?')) return;
    try {
      const res = await fetch('http://127.0.0.1:8000/api/chat/clear', { method: 'DELETE' });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      if (data.cleared) setMessages([]);
    } catch (err) {
      alert('Error borrando historial: ' + err.message);
    }
  };

  return (
    <div className="h-full flex flex-col items-center justify-center p-6 fade-in">
      <div className="w-full max-w-3xl h-full flex flex-col bg-white rounded-3xl shadow-xl overflow-hidden border border-gray-100">

        {/* Cabecera */}
        <div className="p-4 border-b flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-full bg-indigo-600 flex items-center justify-center text-white font-bold">RC</div>
            <div>
              <h3 className="font-bold">Registro Civil - Asistente</h3>
              <p className="text-xs text-gray-500">{backendMessage}</p>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <button onClick={handleClear} disabled={isLoading || messages.length === 0} className="text-sm text-red-600 px-3 py-1 rounded-md border border-red-100 transition-colors hover:bg-red-50 disabled:opacity-50">
              Borrar historial
            </button>
          </div>
        </div>

        {/* Zona de Mensajes */}
        <div ref={scrollRef} className="flex-1 p-6 overflow-y-auto space-y-4 bg-slate-50 custom-scrollbar">
          {messages.length === 0 ? (
            <div className="h-full flex flex-col items-center justify-center text-center p-8">
              <p className="text-gray-400 font-medium">Escribe tu consulta sobre el Registro Civil...</p>
              <p className="text-xs text-gray-400 max-w-xs mt-1">Por ejemplo: requisitos para una denuncia, trámites de matrimonio o solicita recordatorios.</p>
            </div>
          ) : (
            messages.map((m, i) => (
              <div key={i} className={`flex ${m.role === 'user' ? 'justify-end' : 'justify-start'}`}>
                <div className={`${m.role === 'user' ? 'bg-indigo-600 text-white rounded-br-none' : 'bg-white border text-gray-800 rounded-bl-none'} max-w-[85%] p-4 rounded-2xl shadow-sm`}>
                  {m.role === 'assistant' ? (
                    <div className="chat-markdown prose prose-sm max-w-none">
                      <ReactMarkdown remarkPlugins={[remarkGfm]}>{m.content}</ReactMarkdown>
                    </div>
                  ) : (
                    <div className="whitespace-pre-wrap text-sm">{m.content}</div>
                  )}
                </div>
              </div>
            ))
          )}

          {isLoading && (
            <div className="flex justify-start items-center gap-2 text-sm text-indigo-600 font-semibold animate-pulse bg-indigo-50/50 px-3 py-2 rounded-xl w-fit">
              <svg className="animate-spin h-4 w-4 text-indigo-600" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
              </svg>
              El asistente está consultando la información...
            </div>
          )}
        </div>

        {/* Input Footer */}
        <div className="p-4 border-t bg-white">
          <div className="flex gap-2">
            <input 
              value={input} 
              onChange={e => setInput(e.target.value)} 
              onKeyDown={e => e.key === 'Enter' && handleSend()} 
              disabled={!backendReady} 
              placeholder={backendReady ? 'Escribe tu pregunta o pídele un recordatorio...' : 'Esperando servicio...'} 
              className="flex-1 p-3 rounded-xl border border-gray-200 bg-gray-50 focus:outline-none focus:border-indigo-500 focus:bg-white transition-all text-sm disabled:cursor-not-allowed" 
            />
            <button 
              onClick={handleSend} 
              disabled={!backendReady || isLoading || !input.trim()} 
              className="bg-indigo-600 hover:bg-indigo-700 disabled:bg-gray-300 text-white font-medium px-5 py-2 rounded-xl transition-colors text-sm disabled:cursor-not-allowed"
            >
              Enviar
            </button>
          </div>
        </div>

      </div>
    </div>
  );
}