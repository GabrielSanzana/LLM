import os
import re
from pathlib import Path

from dotenv import load_dotenv
from langchain_chroma import Chroma
from langchain_huggingface import HuggingFaceEmbeddings

load_dotenv()

ALLOWED_TOPICS = {
    "port_scan",
    "texto_plano",
    "pop3",
    "malware_c2",
    "dos",
    "http_phishing",
    "general",
}


class RAGService:
    def __init__(self):
        base_dir = Path(__file__).resolve().parents[2]  # Backend/
        default_db_dir = base_dir / "data" / "chroma_db"

        self.persist_directory = os.getenv("CHROMA_DB_DIR", str(default_db_dir))
        self.collection_name = os.getenv("CHROMA_COLLECTION_NAME", "cybersecurity_docs")

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

    def _normalize_topic(self, topic: str | None) -> str | None:
        if not topic:
            return None

        t = topic.strip().lower()
        t = re.sub(r"[^a-z_]", "", t)

        if t in ALLOWED_TOPICS and t != "general":
            return t

        for allowed in ALLOWED_TOPICS:
            if allowed in t and allowed != "general":
                return allowed

        return None

    def get_knowledge(self, query: str, topic: str = None, k: int = 4) -> str:
        normalized_topic = self._normalize_topic(topic)

        docs = []
        try:
            if normalized_topic:
                docs = self.vectorstore.max_marginal_relevance_search(
                    query,
                    k=k,
                    fetch_k=max(10, k * 4),
                    lambda_mult=0.5,
                    filter={"topic": normalized_topic},
                )

            if not docs:
                docs = self.vectorstore.max_marginal_relevance_search(
                    query,
                    k=k,
                    fetch_k=max(10, k * 4),
                    lambda_mult=0.5,
                )
        except Exception as e:
            print(f"[RAG] Error recuperando conocimiento: {e}")
            return ""

        if not docs:
            return ""

        parts = []
        for d in docs:
            source = d.metadata.get("source_file", "unknown")
            page = d.metadata.get("page", "?")
            topic_meta = d.metadata.get("topic", "unknown")
            text = (d.page_content or "").strip()

            if text:
                parts.append(f"[Fuente: {source} | pág. {page} | topic: {topic_meta}]\n{text}")

        return "\n\n".join(parts)