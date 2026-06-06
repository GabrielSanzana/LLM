import os
from langchain_chroma import Chroma
from langchain_huggingface import HuggingFaceEmbeddings
from dotenv import load_dotenv

load_dotenv()

def diagnostic():
    db_path = os.getenv("CHROMA_DB_DIR")
    model_name = os.getenv("EMBEDDING_MODEL", "BAAI/bge-m3")
    
    print(f"--- DIAGNÓSTICO DE RAG ---")
    print(f"Ruta DB: {os.path.abspath(db_path) if db_path else 'NO DEFINIDA'}")
    print(f"Modelo: {model_name}")

    if not db_path or not os.path.exists(db_path):
        print("❌ ERROR: La carpeta de la base de datos no existe.")
        return

    embeddings = HuggingFaceEmbeddings(model_name=model_name)
    vectorstore = Chroma(persist_directory=db_path, embedding_function=embeddings)
    
    # Intentar obtener todos los IDs de la base
    data = vectorstore.get()
    num_docs = len(data['ids'])
    
    print(f"Documentos totales indexados: {num_docs}")
    
    if num_docs > 0:
        print("\nPrimeros 2 documentos (Metadatos):")
        for i in range(min(2, num_docs)):
            print(f"- Doc {i}: {data['metadatas'][i]}")
    else:
        print("❌ LA BASE DE DATOS ESTÁ VACÍA.")

if __name__ == "__main__":
    diagnostic()