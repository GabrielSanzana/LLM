import React, { useState, useEffect, useRef } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

export default function ChatView({ currentUser, switchView }) {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [backendReady, setBackendReady] = useState(false);
  const [backendMessage, setBackendMessage] = useState('Inicializando tutor...');
  const [progress, setProgress] = useState(null);

  const scrollRef = useRef(null);
  const userEmail = localStorage.getItem("userEmail");

  // =========================
  // AUTO SCROLL
  // =========================
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages, isLoading]);

  // =========================
  // VERIFICAR STATUS BACKEND
  // =========================
  useEffect(() => {
    let interval;
    const checkBackend = async () => {
      try {
        const res = await fetch('http://localhost:8000/api/status');
        if (!res.ok) throw new Error('Backend caído');
        const data = await res.json();

        if (data.status === 'ready') {
          setBackendReady(true);
          setBackendMessage('Tutor listo');
        } else {
          setBackendReady(false);
          setBackendMessage(data.message || 'Inicializando base vectorial...');
        }
      } catch (err) {
        setBackendReady(false);
        setBackendMessage('Backend desconectado');
      }
    };

    checkBackend();
    interval = setInterval(checkBackend, 2000);
    return () => clearInterval(interval);
  }, []);

  // =========================
  // CARGAR PROGRESO DE USUARIO
  // =========================
  const fetchProgress = async () => {
    const emailEnStorage = localStorage.getItem("userEmail");
    if (!emailEnStorage || emailEnStorage === "undefined") return;

    try {
      const response = await fetch(`http://localhost:8000/api/chat/progress/${encodeURIComponent(emailEnStorage)}`);
      if (response.ok) {
        const data = await response.json();
        if (data.status === "success" && data.progreso) {
          setProgress(data.progreso);
        }
      }
    } catch (error) {
      console.error("Error al cargar progreso:", error);
    }
  };
  // =========================
  // INICIALIZAR EVALUACION PROACTIVA
  // =========================
  const inicializarEvaluacion = async (email) => {
    setIsLoading(true);
    try {
      const response = await fetch('http://localhost:8000/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          email: email,
          message: "Hola, me gustaría comenzar el test de diagnóstico inicial.",
          nodo_actual: "inicio"
        })
      });

      if (response.ok) {
        const data = await response.json();
        if (data.progreso) {
          setProgress(data.progreso);
        }
        setMessages([
          { role: 'user', content: "Hola, me gustaría comenzar el test de diagnóstico inicial." },
          { role: 'assistant', content: data.response || 'El tutor no devolvió contenido.' }
        ]);
      }
    } catch (error) {
      console.error("Error al inicializar evaluación:", error);
    } finally {
      setIsLoading(false);
    }
  };

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
            const historialFormateado = data.history
              .filter(msg => msg.nodo === 'inicio')
              .map(msg => ({
                role: msg.role,
                content: msg.content
              }));
            setMessages(historialFormateado);

            // Si el historial está vacío, iniciamos automáticamente la primera pregunta diagnóstica
            if (historialFormateado.length === 0) {
              inicializarEvaluacion(emailEnStorage);
            }
          }
        }
      } catch (error) {
        console.error("Error al cargar historial:", error);
      }
    };

    cargarHistorial();
    fetchProgress();
  }, []);
  // =========================
  // ENVIAR MENSAJE
  // =========================
  const handleSend = async () => {
    const emailActual = localStorage.getItem("userEmail");

    if (!emailActual || emailActual === "undefined") {
      alert("Error: No se detectó tu sesión. Por favor, inicia sesión de nuevo.");
      return;
    }

    if (!input.trim() || isLoading) return;

    if (!backendReady) {
      setMessages(prev => [...prev, {
        role: 'assistant',
        content: 'El tutor todavía está cargando la base de conocimientos.'
      }]);
      return;
    }

    const userMsg = input;
    setInput('');

    // Actualización optimista
    setMessages(prev => [...prev, { role: 'user', content: userMsg }]);
    setIsLoading(true);

    try {
      const response = await fetch('http://localhost:8000/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          email: emailActual,
          message: userMsg,
          nodo_actual: "inicio"
        })
      });

      if (!response.ok) {
        const errData = await response.json();
        throw new Error(errData.detail || `Error ${response.status}`);
      }

      const data = await response.json();
      console.log("Router Intent (General Chat):", data.router);

      if (data.progreso) {
        setProgress(data.progreso);
      }

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

  // =========================
  // BORRAR HISTORIAL / RESET
  // =========================
  const handleDeleteHistory = async () => {
    if (!window.confirm("¿Estás seguro de que deseas borrar todo el historial y reiniciar tu ruta de aprendizaje adaptada?")) return;
    
    const emailActual = localStorage.getItem("userEmail");
    if (!emailActual || emailActual === "undefined") return;

    try {
      const res = await fetch(`http://localhost:8000/api/chat/history/${encodeURIComponent(emailActual)}?nodo_actual=inicio`, {
        method: 'DELETE'
      });
      if (res.ok) {
        setMessages([]);
        setProgress(null);
        inicializarEvaluacion(emailActual);
      } else {
        alert("Error al borrar el historial");
      }
    } catch (err) {
      alert("Error de conexión");
    }
  };

  // =========================
  // INICIAR MINI-TEST DE FORMA EXPLICITA
  // =========================
  const handleStartMiniTest = async () => {
    const emailActual = localStorage.getItem("userEmail");
    if (!emailActual || emailActual === "undefined") {
      alert("Error: No se detectó tu sesión. Por favor, inicia sesión de nuevo.");
      return;
    }

    if (isLoading || !backendReady) return;

    const userMsg = "🎯 ¡Listo! Deseo realizar el Mini-Test de este tema.";
    
    // Actualización optimista de la interfaz
    setMessages(prev => [...prev, { role: 'user', content: userMsg }]);
    setIsLoading(true);

    try {
      const response = await fetch('http://localhost:8000/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          email: emailActual,
          message: "/iniciar_mini_test", // Comando inequívoco al backend
          nodo_actual: "inicio"
        })
      });

      if (!response.ok) {
        const errData = await response.json();
        throw new Error(errData.detail || `Error ${response.status}`);
      }

      const data = await response.json();
      console.log("Router Intent (Mini-Test start):", data.router);

      if (data.progreso) {
        setProgress(data.progreso);
      }

      setMessages(prev => [...prev, {
        role: 'assistant',
        content: data.response || 'El tutor no devolvió contenido.'
      }]);
    } catch (error) {
      console.error("Error al iniciar el mini-test:", error);
      setMessages(prev => [...prev, {
        role: 'assistant',
        content: `Error del sistema: ${error.message}`
      }]);
    } finally {
      setIsLoading(false);
    }
  };

  const TOPIC_DISPLAY_NAMES = {
    "texto_plano": "Texto Plano (Telnet/FTP sin cifrar)",
    "http_phishing": "HTTP y Cabeceras de Phishing",
    "port_scan": "Escaneo de Puertos (Tráfico SYN)",
    "dos": "Denegación de Servicio (DoS/Inundaciones)",
    "malware_c2": "Malware y Canales de Comando y Control (C2)"
  };

  // =========================
  // MONITOR DE SESIÓN
  // =========================
  useEffect(() => {
    const emailEnStorage = localStorage.getItem("userEmail");
    if (!emailEnStorage || emailEnStorage === "undefined") {
      setMessages([]);
      setProgress(null);
    }
  }, [localStorage.getItem("userEmail")]);

  const displayEmail = localStorage.getItem("userEmail") || "Invitado";

  // =========================
  // DATOS DEL STEPPER
  // =========================
  const topics = [
    { id: "texto_plano", name: "Texto Plano", desc: "Red sin cifrar" },
    { id: "http_phishing", name: "Phishing", desc: "Cabeceras HTTP" },
    { id: "port_scan", name: "Port Scan", desc: "Ráfagas SYN" },
    { id: "dos", name: "DDoS", desc: "Saturación host" },
    { id: "malware_c2", name: "Malware C2", desc: "Beacons y control" }
  ];

  return (
    <div className="h-full flex flex-col items-center justify-center p-6 fade-in">
      <div className="w-full max-w-5xl h-full flex flex-row bg-white rounded-3xl shadow-xl overflow-hidden border border-gray-100">

        {/* SIDEBAR: STEPPER VERTICAL */}
        {progress && (
          <div className="w-64 bg-slate-900 text-white flex flex-col flex-shrink-0 border-r border-slate-800 p-6 select-none">
            <div className="mb-6 flex-shrink-0">
              <div className="flex items-center gap-2 mb-2">
                <span className="text-indigo-400 text-lg">🛡️</span>
                <h4 className="text-[11px] font-black tracking-wider uppercase text-slate-200">Plan de Estudios</h4>
              </div>
              <p className="text-[10px] text-slate-400 leading-relaxed">
                Completa tu ruta de aprendizaje adaptada para dominar los temas clave.
              </p>
            </div>

            <div className="flex-1 flex flex-col justify-start gap-1 py-2 overflow-y-auto custom-scrollbar">
              {topics.map((t, idx) => {
                const isCompleted = progress.completed_topics?.includes(t.id);
                const isActive = progress.current_topic === t.id;
                
                return (
                  <div key={t.id} className="relative flex items-start gap-4 pb-6 last:pb-0 group">
                    {/* Vertical connecting line */}
                    {idx < topics.length - 1 && (
                      <div className={`absolute left-4 top-8 bottom-0 w-[2px] -translate-x-1/2 transition-colors duration-500 ${
                        isCompleted && progress.completed_topics?.includes(topics[idx + 1].id)
                          ? 'bg-emerald-500'
                          : isCompleted
                            ? 'bg-gradient-to-b from-emerald-500 to-slate-800'
                            : 'bg-slate-800'
                      }`} />
                    )}

                    {/* Node Circle */}
                    <div className={`w-8 h-8 rounded-full flex items-center justify-center font-bold text-[10px] shadow-md border transition-all duration-300 z-10 flex-shrink-0 ${
                      isCompleted 
                        ? 'bg-emerald-500/20 border-emerald-500 text-emerald-400 shadow-emerald-950/20' 
                        : isActive
                          ? 'bg-indigo-600 border-indigo-400 text-white ring-4 ring-indigo-500/25 shadow-indigo-900/40 animate-pulse'
                          : 'bg-slate-800 border-slate-700 text-slate-500 shadow-slate-950/25'
                    }`}>
                      {isCompleted ? '✓' : idx + 1}
                    </div>

                    {/* Text metadata */}
                    <div className="flex flex-col min-w-0 pt-0.5">
                      <span className={`text-[11px] font-black transition-colors truncate ${
                        isCompleted 
                          ? 'text-emerald-400' 
                          : isActive 
                            ? 'text-indigo-400 font-extrabold' 
                            : 'text-slate-400'
                      }`}>{t.name}</span>
                      <span className="text-[9px] text-slate-500 mt-0.5 truncate leading-tight">{t.desc}</span>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        )}

        {/* CHAT CONTAINER */}
        <div className="flex-1 h-full flex flex-col min-w-0 bg-white">

          {/* HEADER */}
          <div className="p-6 border-b flex items-center justify-between gap-4 bg-gray-50/50 flex-shrink-0">
            <div className="flex items-center gap-4">
              <div className="w-10 h-10 rounded-full bg-indigo-600 flex items-center justify-center text-white font-bold shadow-lg shadow-indigo-200">
                AI
              </div>
              <div>
                <h3 className="font-bold text-gray-800 text-sm">Tutor de Ciberseguridad</h3>
                <p className="text-xs text-gray-400 font-medium">Estudiante: {displayEmail}</p>
              </div>
            </div>

            <div className="flex items-center gap-3">
              {messages.length > 0 && (
                <button 
                  onClick={handleDeleteHistory}
                  disabled={isLoading}
                  className="bg-red-50 text-red-600 hover:bg-red-100 px-3 py-1.5 rounded-xl font-bold shadow-sm transition-all flex items-center gap-2 text-xs border border-red-200"
                  title="Reiniciar Progreso y Chat"
                >
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" d="M4 4v5h.582m15.356 2A8.001 8.001 0 1 1 21.21 7.89" />
                    <path strokeLinecap="round" strokeLinejoin="round" d="M17 9.89h5v-5" />
                  </svg>
                  Reiniciar Ruta
                </button>
              )}
              <div className={`text-xs font-bold px-3 py-1 rounded-full ${
                backendReady ? 'bg-green-100 text-green-700' : 'bg-yellow-100 text-yellow-700'
              }`}>
                {backendMessage}
              </div>
            </div>
          </div>

          {/* TOP PROGRESS / ACTION HEADER AREA */}
          {progress && (
            <div className="flex-shrink-0">
              {progress.stage === "global_diagnostic" ? (
                // Barra de diagnóstico inicial
                <div className="w-full bg-slate-900 text-white p-4 px-6 border-b border-slate-800 flex items-center justify-between gap-4">
                  <div className="flex items-center gap-3">
                    <div className="w-2 h-2 rounded-full bg-indigo-500 animate-ping"></div>
                    <div>
                      <h4 className="text-[10px] font-bold tracking-wider text-indigo-400 uppercase">Test de Diagnóstico Inicial</h4>
                      <p className="text-[10px] text-slate-400 mt-0.5">Construyendo tu ruta de aprendizaje adaptada</p>
                    </div>
                  </div>
                  <div className="flex items-center gap-4 flex-1 max-w-xs justify-end">
                    <span className="text-[10px] font-bold text-slate-300">Pregunta {Math.min((progress.diagnostic_step || 0) + 1, 5)} de 5</span>
                    <div className="w-24 bg-slate-800 h-1.5 rounded-full overflow-hidden border border-slate-700/50">
                      <div 
                        className="bg-gradient-to-r from-indigo-500 to-purple-500 h-full rounded-full transition-all duration-500" 
                        style={{ width: `${((progress.diagnostic_step || 0) / 5) * 100}%` }}
                      ></div>
                    </div>
                  </div>
                </div>
              ) : progress.stage === "teaching" && progress.current_topic ? (
                // Botón de Comenzar Mini-Test colocado donde estaba el header de los temas
                <div className="w-full bg-indigo-50/70 border-b border-indigo-100/50 p-4 px-6 flex items-center justify-between gap-4 animate-fade-in flex-shrink-0">
                  <div className="flex items-center gap-3">
                    <div className="w-8 h-8 rounded-xl bg-indigo-100 text-indigo-600 flex items-center justify-center font-bold text-sm shadow-sm">
                      📖
                    </div>
                    <div>
                      <h4 className="text-[10px] font-bold tracking-wider text-indigo-800 uppercase">Módulo de Aprendizaje Activo</h4>
                      <p className="text-xs text-indigo-950 mt-0.5 font-medium">
                        Estás aprendiendo: <strong className="text-indigo-600 text-center">{TOPIC_DISPLAY_NAMES[progress.current_topic] || progress.current_topic}</strong>
                      </p>
                    </div>
                  </div>
                  <button
                    onClick={handleStartMiniTest}
                    disabled={isLoading}
                    className="bg-indigo-600 hover:bg-indigo-700 text-white font-extrabold text-[10px] uppercase tracking-wider py-2.5 px-4 rounded-xl shadow-md shadow-indigo-200 transition-all hover:scale-[1.02] active:scale-[0.98] disabled:opacity-50 disabled:pointer-events-none flex-shrink-0"
                  >
                    🎯 Comenzar Mini-Test (3 Preguntas)
                  </button>
                </div>
              ) : null}
            </div>
          )}

          {/* CHAT AREA */}
          <div ref={scrollRef} className="flex-1 p-8 space-y-6 overflow-y-auto custom-scrollbar min-h-0 bg-slate-50/30">
            {messages.length === 0 && (
              <p className="text-center text-gray-400 mt-20 italic">
                ¡Bienvenido! Pregúntame sobre protocolos, análisis de red o mitigación de ataques.
              </p>
            )}

            {messages.map((m, i) => {
              const isUser = m.role === 'user';
              let displayContent = m.content;
              let containsSim = null;
              let containsPcap = false;

              if (!isUser) {
                containsSim = m.content.match(/\[RECOMENDACION:SIMULADOR:(Nivel_\d)\]/);
                containsPcap = m.content.includes("[RECOMENDACION:PCAP]");
                displayContent = m.content
                  .replace(/\[RECOMENDACION:SIMULADOR:Nivel_\d\]/g, "")
                  .replace(/\[RECOMENDACION:PCAP\]/g, "")
                  .trim();
              }

              return (
                <div key={i} className={`flex ${isUser ? 'justify-end' : 'justify-start'} animate-fade-in`}>
                  <div className={`max-w-[80%] p-4 rounded-2xl text-base leading-relaxed ${
                    isUser
                      ? 'bg-indigo-600 text-white shadow-md rounded-tr-none'
                      : 'bg-white border border-gray-200 text-gray-800 shadow-sm rounded-tl-none'
                  }`}>
                    {isUser ? (
                      <div className="whitespace-pre-wrap">{displayContent}</div>
                    ) : (
                      <div className="chat-markdown">
                        <ReactMarkdown remarkPlugins={[remarkGfm]}>{displayContent}</ReactMarkdown>
                      </div>
                    )}
                    
                    {!isUser && (containsSim || containsPcap) && (
                      <div className="mt-4 pt-4 border-t border-gray-100 flex flex-col gap-2">
                        <span className="text-[9px] font-black text-gray-400 uppercase tracking-widest">
                          Práctica Recomendada:
                        </span>
                        <div className="flex flex-wrap gap-2 mt-1">
                          {containsSim && (
                            <button
                              onClick={() => {
                                const nivelStr = containsSim[1];
                                const nivelId = parseInt(nivelStr.split("_")[1]);
                                localStorage.setItem("activeLevel", nivelId);
                                if (switchView) switchView('sim');
                              }}
                              className="bg-indigo-600 hover:bg-indigo-700 text-white font-bold text-xs py-2 px-4 rounded-xl shadow transition-all flex items-center gap-2 transform hover:-translate-y-0.5"
                            >
                              <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M13 10V3L4 14h7v7l9-11h-7z" />
                              </svg>
                              🎯 Ir al Simulador: Nivel {containsSim[1].split("_")[1]}
                            </button>
                          )}
                          {containsPcap && (
                            <button
                              onClick={() => {
                                if (switchView) switchView('analysis');
                              }}
                              className="bg-slate-800 hover:bg-slate-900 text-white font-bold text-xs py-2 px-4 rounded-xl shadow transition-all flex items-center gap-2 transform hover:-translate-y-0.5"
                            >
                              <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                              </svg>
                              🔍 Ir a Analizar PCAP
                            </button>
                          )}
                        </div>
                      </div>
                    )}
                  </div>
                </div>
              );
            })}

            {isLoading && (
              <div className="flex justify-start">
                <div className="text-xs text-indigo-500 animate-pulse font-bold bg-indigo-50 px-3 py-1 rounded-full">
                  Tutor pensando...
                </div>
              </div>
            )}
          </div>

          {/* INPUT */}
          <div className="p-6 border-t bg-white flex-shrink-0">
            <div className="relative flex gap-2">
              <input
                type="text"
                value={input}
                disabled={!backendReady || isLoading}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && handleSend()}
                placeholder={backendReady ? 'Escribe tu duda o respuesta técnica aquí...' : 'Esperando al tutor...'}
                className="flex-1 bg-gray-100 border-none rounded-2xl py-4 px-6 outline-none focus:ring-2 focus:ring-indigo-500 transition-all disabled:opacity-50"
              />
              <button
                disabled={!backendReady || isLoading}
                onClick={handleSend}
                className="bg-indigo-600 text-white p-4 rounded-2xl hover:bg-indigo-700 transition-colors disabled:opacity-50 shadow-lg flex items-center justify-center"
              >
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M14 5l7 7m0 0l-7 7m7-7H3" />
                </svg>
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}