import React, { useState, useEffect, useRef } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

export default function SimulatorView() {
  const [currentLevel, setCurrentLevel] = useState(null);
  const [completedLevels, setCompletedLevels] = useState(new Set());
  const [chatLog, setChatLog] = useState([]);
  const [inputValue, setInputValue] = useState('');
  const [activeData, setActiveData] = useState(null);
  const [isLoading, setIsLoading] = useState(false);
  const [isSending, setIsSending] = useState(false);
  const [memorySummary, setMemorySummary] = useState('');
  const chatBoxRef = useRef(null);

  const levelMap = { text: 1, phishing: 2, scan: 3, ddos: 4, c2: 5 };

  const getEmail = () => {
    return (
      localStorage.getItem('email') ||
      localStorage.getItem('user_email') ||
      'simulador@nettutor.local'
    );
  };

  const loadAttack = async (levelId) => {
    const numericId = levelMap[levelId];
    setIsLoading(true);
    setCurrentLevel(levelId);
    setChatLog([]);
    setMemorySummary('');

    try {
      const response = await fetch(`http://localhost:8000/api/scenario/${numericId}`);
      const result = await response.json();

      if (result.status === 'success') {
        const { escenario, guia_tutor, paquetes_pcap, metadata_simulacion } = result.data;

        setActiveData({
          label: metadata_simulacion?.topico?.toUpperCase() || 'SIMULACIÓN',
          guide: `
            <div class="space-y-4">
              <div class="bg-indigo-900/20 p-3 rounded-lg border border-indigo-500/30">
                <h4 class="text-indigo-400 font-bold text-xs uppercase mb-1">Empresa Target</h4>
                <p class="text-white">${escenario.empresa_ficticia}</p>
              </div>
              <p>${escenario.descripcion_entorno}</p>
              <div class="mt-4 p-3 bg-slate-800 rounded-lg border border-slate-700">
                <h4 class="text-amber-400 font-bold text-[10px] uppercase">Objetivo de la Misión</h4>
                <p class="text-slate-200 text-xs">${escenario.objetivo_aprendizaje}</p>
              </div>
            </div>
          `,
          concepts: guia_tutor.pistas_sistema || [],
          packets: paquetes_pcap || [],
        });

        setChatLog([
          { sender: 'AI', text: guia_tutor.mensaje_inicial || 'Escenario cargado.' },
        ]);
      } else {
        setChatLog([
          { sender: 'AI', text: 'No se pudo cargar el escenario.' },
        ]);
      }
    } catch (error) {
      console.error('Error al cargar datos:', error);
      setChatLog([
        { sender: 'AI', text: 'Error cargando la simulación.' },
      ]);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    if (chatBoxRef.current) {
      chatBoxRef.current.scrollTop = chatBoxRef.current.scrollHeight;
    }
  }, [chatLog]);

  useEffect(() => {
    const savedLevel = localStorage.getItem("activeLevel");
    if (savedLevel) {
      const numericId = parseInt(savedLevel);
      const levelKey = Object.keys(levelMap).find(key => levelMap[key] === numericId);
      if (levelKey) {
        loadAttack(levelKey);
      }
      localStorage.removeItem("activeLevel");
    }
  }, []);

  const sendSimChat = async () => {
    if (!inputValue.trim() || isSending || !currentLevel) return;

    const userText = inputValue.trim();
    setInputValue('');
    setChatLog((prev) => [...prev, { sender: 'User', text: userText }]);
    setIsSending(true);

    try {
      const response = await fetch('http://localhost:8000/api/simulator/chat', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          email: getEmail(),
          message: userText,
          nivel_id: levelMap[currentLevel],
          memory_summary: memorySummary,
          pcap_data: {
            packets: activeData?.packets || [],
            level: currentLevel,
            topico: activeData?.label || 'SIMULACION',
          },
        }),
      });

      const data = await response.json();

      console.log('Router Intent (Simulator):', data.router);

      if (!response.ok) {
        throw new Error(data.detail || `HTTP ${response.status}`);
      }

      setMemorySummary(data.memory_next || '');

      setChatLog((prev) => [
        ...prev,
        {
          sender: 'AI',
          text: data.response || 'El tutor no devolvió respuesta.',
        },
      ]);
    } catch (error) {
      console.error('Error al enviar al simulador:', error);

      setChatLog((prev) => [
        ...prev,
        {
          sender: 'AI',
          text: `Error del sistema: ${error.message}`,
        },
      ]);
    } finally {
      setIsSending(false);
    }
  };

  return (
    <div className="h-full flex flex-col p-6 bg-slate-50 font-sans">
      <div className="flex-1 flex flex-col gap-6 min-h-0">
        {/* Selector de Niveles */}
        <div className="bg-white p-4 rounded-2xl shadow-sm border border-gray-100 flex flex-col gap-3">
          <div className="flex justify-between items-center px-1">
            <span className="text-[10px] font-bold text-gray-400 uppercase tracking-widest">
              Entrenamiento Forense
            </span>
            {memorySummary && (
              <span className="text-[10px] font-bold text-emerald-600">
                Memoria activa
              </span>
            )}
          </div>

          <div className="grid grid-cols-5 gap-3">
            {Object.keys(levelMap).map((id) => (
              <button
                key={id}
                onClick={() => loadAttack(id)}
                disabled={isLoading}
                className={`px-3 py-3 border rounded-xl text-[10px] font-bold transition-all ${
                  currentLevel === id
                    ? 'ring-2 ring-indigo-500 bg-indigo-50 border-indigo-200'
                    : 'bg-slate-50 border-slate-200 hover:bg-white'
                }`}
              >
                NIVEL {levelMap[id]}
              </button>
            ))}
          </div>
        </div>

        <div className="flex-1 flex gap-6 overflow-hidden">
          <div className="flex-1 flex flex-col gap-4 overflow-hidden">
            {/* Tabla Principal */}
            <div className="flex-1 bg-white rounded-2xl shadow-sm border border-gray-100 overflow-hidden flex flex-col">
              <div className="p-4 border-b bg-gray-50 flex justify-between items-center">
                <h3 className="text-xs font-bold text-gray-500 uppercase">
                  Tráfico de Red Detectado
                </h3>
                <span className="text-[10px] font-black bg-indigo-100 text-indigo-700 px-2 py-1 rounded">
                  {activeData?.label || 'ESPERANDO CARGA'}
                </span>
              </div>

              <div className="flex-1 overflow-auto font-mono text-[10px]">
                <table className="w-full text-left border-collapse">
                  <thead className="bg-gray-100 sticky top-0 border-b text-gray-500 font-bold uppercase">
                    <tr>
                      <th className="px-3 py-2 border-r w-12 text-center">No.</th>
                      <th className="px-3 py-2 border-r w-20">Tiempo</th>
                      <th className="px-3 py-2 border-r w-28">Origen</th>
                      <th className="px-3 py-2 border-r w-28">Destino</th>
                      <th className="px-3 py-2 border-r w-16 text-center">Prot.</th>
                      <th className="px-3 py-2">Información</th>
                    </tr>
                  </thead>

                  <tbody>
                    {activeData?.packets?.length > 0 ? (
                      activeData.packets.map((p, i) => (
                        <tr key={i} className="border-b border-gray-50 hover:bg-indigo-50/50">
                          <td className="px-3 py-1 border-r text-gray-400 text-center">{p.no}</td>
                          <td className="px-3 py-1 border-r text-indigo-600 font-medium">{p.time}</td>
                          <td className="px-3 py-1 border-r text-slate-700">{p.src}</td>
                          <td className="px-3 py-1 border-r text-slate-700">{p.dst}</td>
                          <td className="px-3 py-1 border-r text-center">
                            <span className="bg-slate-200 px-1 rounded font-bold">{p.pr}</span>
                          </td>
                          <td className="px-3 py-1 text-slate-900 truncate">{p.info}</td>
                        </tr>
                      ))
                    ) : (
                      <tr>
                        <td colSpan="6" className="py-20 text-center text-slate-400 italic">
                          {isLoading
                            ? 'Consultando base de datos forense...'
                            : 'Selecciona un nivel del mapa para visualizar los paquetes.'}
                        </td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
            </div>

            {/* Consola de Chat */}
            <div className="h-44 bg-white rounded-2xl shadow-lg border border-indigo-100 flex flex-col overflow-hidden">
              <div className="flex-1 p-4 overflow-y-auto space-y-3" ref={chatBoxRef}>
                {chatLog.map((msg, idx) => (
                  <div key={idx} className={`flex ${msg.sender === 'User' ? 'justify-end' : 'justify-start'}`}>
                    <div
                      className={`max-w-[85%] p-2 rounded-xl text-xs ${
                        msg.sender === 'User'
                          ? 'bg-slate-100 text-slate-800'
                          : 'bg-indigo-600 text-white shadow-md'
                      }`}
                    >
                      <strong>{msg.sender === 'User' ? 'Analista' : 'Tutor'}:</strong>{' '}
                      {msg.sender === 'User' ? (
                        msg.text
                      ) : (
                        <span className="chat-markdown chat-markdown-dark inline-block w-full">
                          <ReactMarkdown remarkPlugins={[remarkGfm]}>{msg.text}</ReactMarkdown>
                        </span>
                      )}
                    </div>
                  </div>
                ))}

                {isSending && (
                  <div className="text-[10px] text-indigo-500 font-bold animate-pulse">
                    Tutor pensando...
                  </div>
                )}
              </div>

              <div className="p-2 bg-gray-50 border-t flex gap-2">
                <input
                  className="flex-1 bg-white border rounded-xl px-4 py-2 text-xs outline-none focus:ring-2 focus:ring-indigo-500"
                  placeholder="Describe el hallazgo técnico..."
                  value={inputValue}
                  onChange={(e) => setInputValue(e.target.value)}
                  onKeyDown={(e) => e.key === 'Enter' && sendSimChat()}
                  disabled={!currentLevel || isSending}
                />
                <button
                  onClick={sendSimChat}
                  disabled={!currentLevel || isSending}
                  className="bg-indigo-600 text-white px-4 py-2 rounded-xl text-[10px] font-bold uppercase tracking-wider disabled:opacity-50"
                >
                  Reportar
                </button>
              </div>
            </div>
          </div>

          {/* Guía Lateral */}
          <div className="w-72 flex flex-col">
            <div className="flex-1 bg-slate-900 rounded-3xl shadow-xl p-5 text-white flex flex-col border border-slate-700 overflow-hidden">
              <h3 className="text-[10px] font-bold text-indigo-400 uppercase tracking-widest mb-4">
                Investigación Guiada
              </h3>

              <div className="flex-1 overflow-y-auto text-xs text-slate-300 leading-relaxed space-y-3">
                {!activeData ? (
                  <p className="text-slate-500 italic">
                    Selecciona un nivel para recibir el briefing de la misión.
                  </p>
                ) : (
                  <div dangerouslySetInnerHTML={{ __html: activeData.guide }} />
                )}
              </div>

              {activeData?.concepts?.length > 0 && (
                <div className="mt-4 pt-4 border-t border-slate-800">
                  <div className="flex flex-wrap gap-1">
                    {activeData.concepts.map((c, i) => (
                      <span
                        key={i}
                        className="bg-indigo-500/20 text-indigo-300 border border-indigo-500/30 px-2 py-1 rounded-[4px] text-[8px] font-bold uppercase"
                      >
                        {c}
                      </span>
                    ))}
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}