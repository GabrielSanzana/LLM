import os
# pyrefly: ignore [missing-import]
from scapy.all import rdpcap, IP, TCP, UDP

def analyze_pcap(file_path: str):
    """
    Extrae metadatos clave del PCAP para que el LLM tenga contexto técnico real.
    """
    if not os.path.exists(file_path):
        return "Error: Archivo no encontrado."

    try:
        packets = rdpcap(file_path)
        total_packets = len(packets)
        
        # Analizar protocolos y flujos básicos
        proto_counts = {"TCP": 0, "UDP": 0, "ICMP": 0, "Otros": 0}
        unique_ips = set()
        payload_snippets = []

        for pkt in packets[:50]:  # Analizamos los primeros 50 para no saturar el prompt
            if IP in pkt:
                unique_ips.add(pkt[IP].src)
                unique_ips.add(pkt[IP].dst)
                
                if TCP in pkt: proto_counts["TCP"] += 1
                elif UDP in pkt: proto_counts["UDP"] += 1
                elif pkt.haslayer("ICMP"): proto_counts["ICMP"] += 1
                else: proto_counts["Otros"] += 1

            # Extraer pedazos de texto si existen (útil para Nivel 1 y 2)
            if pkt.haslayer("Raw"):
                load = str(pkt["Raw"].load)
                if len(load) > 10:
                    payload_snippets.append(load[:50])

        summary = {
            "total_packets": total_packets,
            "protocols": proto_counts,
            "unique_ips": list(unique_ips),
            "scapy_summary": [pkt.summary() for pkt in packets[:20]],
            "payload_hints": list(set(payload_snippets))[:5]
        }
        
        return summary
    except Exception as e:
        return f"Error en análisis de Scapy: {str(e)}"