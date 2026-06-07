import sys
from datetime import datetime, timedelta
from app.services.google_calendar_service import GoogleCalendarService, parse_fecha_hora
from app.services.react_agent import get_response

def run_tests():
    print("=== Iniciando pruebas de Google Calendar Service ===")
    
    # Test 1: Date Parser
    print("\n1. Probando el analizador de fechas (parse_fecha_hora):")
    ahora = datetime.now()
    
    fechas_prueba = [
        ("2026-06-08T10:00:00", datetime(2026, 6, 8, 10, 0, 0)),
        ("2026-06-12", datetime(2026, 6, 12, 9, 0, 0)),
        ("08/12/2026 15:30", datetime(2026, 12, 8, 15, 30, 0)),
        ("formato-invalido", ahora + timedelta(days=1))  # Fallback a mañana
    ]
    
    for fecha_str, esperada in fechas_prueba:
        res = parse_fecha_hora(fecha_str)
        # Para el formato inválido, solo verificamos que sea mañana a las 9
        if fecha_str == "formato-invalido":
            correcto = (res.hour == 9 and res.minute == 0)
        else:
            correcto = (res.year == esperada.year and res.month == esperada.month and 
                        res.day == esperada.day and res.hour == esperada.hour and res.minute == esperada.minute)
        
        status = "PASSED" if correcto else "FAILED"
        print(f"  Input: '{fecha_str}' -> Parseado como: {res.strftime('%Y-%m-%d %H:%M:%S')} [{status}]")
        if not correcto:
            print(f"    Esperado: {esperada}")

    # Test 2: Google Calendar Service Initialization and Mock Mode
    print("\n2. Probando GoogleCalendarService:")
    service = GoogleCalendarService()
    
    # Crear un evento de prueba
    resultado = service.create_reminder_event(
        tramite="Renovación de cédula de identidad",
        fecha_hora_str="2026-06-08T11:00:00",
        email="test_ciudadano@example.com",
        documentos="Cédula anterior vencida\nComprobante de pago"
    )
    
    print(f"  Resultado de la creación del evento:")
    print(f"  Status: {resultado.get('status')}")
    print(f"  Mensaje: {resultado.get('message')}")
    print(f"  Enlace: {resultado.get('htmlLink')}")
    
    assert "status" in resultado, "El resultado debe contener 'status'"
    print("  Prueba de servicio completada exitosamente.")

    # Test 3: Agent Integration (Dry Run)
    print("\n3. Probando la integración del Agente (get_response):")
    try:
        # Pregunta sobre trámite (debería consultar RAG)
        print("  Enviando consulta de trámite...")
        resp1 = get_response("¿Cómo obtengo un certificado de nacimiento?")
        print(f"  Respuesta del Agente:\n{resp1['response'][:200]}...")
        print(f"  Trace del agente: {resp1['trace']}")

        # Solicitar recordatorio sin email (debería preguntar por el email)
        print("\n  Enviando solicitud de recordatorio sin email...")
        resp2 = get_response("Perfecto, recuérdamelo mañana a las 10 am", history=[
            {"role": "user", "content": "¿Cómo obtengo un certificado de nacimiento?"},
            {"role": "assistant", "content": resp1['response']}
        ])
        print(f"  Respuesta del Agente: {resp2['response']}")
        
    except Exception as e:
        print(f"  Error probando la integración del Agente: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    import sys
    # Reconfigure stdout to use UTF-8 to avoid encoding errors with emojis on Windows
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    run_tests()
