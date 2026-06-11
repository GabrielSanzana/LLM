import os
from pathlib import Path

from dotenv import load_dotenv
from langchain_chroma import Chroma
from langchain_huggingface import HuggingFaceEmbeddings

load_dotenv()

class RAGService:
    def __init__(self):
        base_dir = Path(__file__).resolve().parents[2]  # Backend/
        default_db_dir = base_dir / "data" / "chroma_db"

        self.persist_directory = os.getenv("CHROMA_DB_DIR", str(default_db_dir))
        self.collection_name = os.getenv("CHROMA_COLLECTION_NAME", "chileatiende_docs")

        self.embeddings = HuggingFaceEmbeddings(
            model_name=os.getenv("EMBEDDING_MODEL", "BAAI/bge-m3"),
            model_kwargs={"device": "cpu"},
            encode_kwargs={"normalize_embeddings": True},
        )

        self.vectorstore = Chroma(
            collection_name=self.collection_name,
            persist_directory=self.persist_directory,
            embedding_function=self.embeddings,
        )

    def get_knowledge(self, query: str, k: int = 3) -> str:
        docs = []

        try:
            docs = self.vectorstore.max_marginal_relevance_search(
                query,
                k=k,
                fetch_k=max(10, k * 4),
                lambda_mult=0.8,
            )

        except Exception as e:
            print(f"[RAG] Error recuperando información: {e}")
            return ""

        if not docs:
            print(f"[RAG] No se encontraron resultados para: '{query}'")
            return ""

        print("\n" + "=" * 100)
        print(f"[RAG QUERY] {query}")
        print(f"[RAG] Recuperados {len(docs)} chunks")
        print("=" * 100)

        parts = []

        for i, d in enumerate(docs, start=1):
            source = d.metadata.get("source_file", "Documento Oficial")
            page = d.metadata.get("page", "?")
            text = (d.page_content or "").strip()

            print(f"\n[RAG RESULTADO {i}]")
            print(f"Documento : {source}")
            print(f"Página     : {page}")
            print("Chunk:")
            print("-" * 80)
            print(text[:1000])  # evita inundar la consola
            print("-" * 80)

            if text:
                parts.append(
                    f"[Fuente: {source} | pág. {page}]\n{text}"
                )

        print("=" * 100 + "\n")

        return "\n\n".join(parts)