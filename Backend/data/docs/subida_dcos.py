import requests
import os

# URL base de la API de GitHub para listar contenidos del repositorio
repo_api_url = "https://api.github.com/repos/PatricioFigueroa/Chile-Atiende-RAG/contents/"
response = requests.get(repo_api_url)
files_data = response.json()

# Filtrar solo archivos PDF
pdf_files = [f for f in files_data if f['name'].endswith('.pdf')]

# Crear carpeta para los documentos si no existe

downloaded_files = []
for file_info in pdf_files:
    pdf_url = file_info['download_url']
    file_path = os.path.join("Backend/data/docs", file_info['name'])

    print(f"Descargando {file_info['name']}...")
    r = requests.get(pdf_url)
    with open(file_path, "wb") as f:
        f.write(r.content)
    downloaded_files.append(file_path)

print(f"\n✅ Se han descargado {len(downloaded_files)} archivos PDF.")