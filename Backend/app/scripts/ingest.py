import re
import shutil
from pathlib import Path

# pyrefly: ignore [missing-import]
from langchain_community.document_loaders import PyPDFLoader
# pyrefly: ignore [missing-import]
from langchain_chroma import Chroma
# pyrefly: ignore [missing-import]
from langchain_huggingface import HuggingFaceEmbeddings

COLLECTION_NAME = "cybersecurity_docs"


def clean_text(t: str) -> str:
    if not t:
        return ""

    t = t.replace("\x00", " ")
    t = t.replace("\uf0b7", " ")
    t = t.replace("\u200b", " ")

    # Une palabras cortadas al final de línea
    t = re.sub(r"(\w)-\s*\n\s*(\w)", r"\1\2", t)

    # Mantiene algo de estructura
    t = re.sub(r"\n{3,}", "\n\n", t)

    # Quita URLs
    t = re.sub(r"https?://\S+", " ", t)

    # Normaliza espacios
    t = re.sub(r"[ \t]+", " ", t)

    lines = []
    for line in t.split("\n"):
        line = line.strip()
        if not line:
            continue
        if len(line) <= 2:
            continue
        lines.append(line)

    t = "\n".join(lines)
    t = re.sub(r"\s+\n", "\n", t)
    t = re.sub(r"\n\s+", "\n", t)
    t = re.sub(r"[ \t]+", " ", t)

    return t.strip()


def split_sentences(t: str):
    t = clean_text(t)
    if not t:
        return []

    protected = {
        "e.g.": "eg__DOT__",
        "i.e.": "ie__DOT__",
        "Fig.": "Fig__DOT__",
        "No.": "No__DOT__",
        "Dr.": "Dr__DOT__",
        "Mr.": "Mr__DOT__",
        "Ms.": "Ms__DOT__",
        "etc.": "etc__DOT__",
    }

    for k, v in protected.items():
        t = t.replace(k, v)

    sents = re.split(r"(?<=[.!?])\s+", t)

    out = []
    for s in sents:
        s = s.strip()
        for k, v in protected.items():
            s = s.replace(v, k)
        if len(s) >= 20:
            out.append(s)

    return out


def chunk_text_sentences(
    t: str,
    max_sentences: int = 4,
    overlap: int = 1,
    min_chars: int = 200,
    max_chars: int = 1200,
):
    sents = split_sentences(t)
    if not sents:
        return []

    chunks = []
    step = max(1, max_sentences - overlap)

    i = 0
    while i < len(sents):
        current = []
        current_len = 0

        for j in range(i, min(i + max_sentences, len(sents))):
            sent = sents[j]
            if not sent:
                continue

            if current and (current_len + len(sent) + 1 > max_chars):
                break

            current.append(sent)
            current_len += len(sent) + 1

        chunk = " ".join(current).strip()
        if chunk and len(chunk) >= min_chars:
            chunk = re.sub(r"\s+", " ", chunk)
            chunks.append(chunk)

        i += step

    return chunks


def infer_topic(filename: str):
    f = filename.lower()

    if "rfc854" in f or "telnet" in f or "texto" in f or "plano" in f:
        return "texto_plano"

    if "rfc1939" in f or "pop3" in f:
        return "pop3"

    if "rfc7230" in f or "http" in f:
        return "http_phishing"

    if "nmap" in f:
        return "port_scan"

    if "mitre" in f or "beacon" in f:
        return "malware_c2"

    if "ddos" in f or "flood" in f:
        return "dos"

    return "general"


def load_pdf_texts(pdf_dir: str):
    pdf_paths = sorted(Path(pdf_dir).rglob("*.pdf"))
    docs = []

    print("PDFs encontrados:", [p.name for p in pdf_paths])

    for pdf_path in pdf_paths:
        print(f"Cargando: {pdf_path.name}")
        loader = PyPDFLoader(str(pdf_path))
        pdf_docs = loader.load()

        for page_num, d in enumerate(pdf_docs):
            cleaned = clean_text(d.page_content)

            if len(cleaned) < 80:
                continue

            d.page_content = cleaned
            d.metadata["source_file"] = pdf_path.name
            d.metadata["source_path"] = str(pdf_path)
            d.metadata["page"] = page_num + 1
            d.metadata["topic"] = infer_topic(pdf_path.name)
            docs.append(d)

    return docs


def run_ingestion(force=False):
    base_dir = Path(__file__).resolve().parents[2]  # Backend/
    docs_path = base_dir / "data" / "docs"
    db_path = base_dir / "data" / "chroma_db"

    if not docs_path.exists():
        raise FileNotFoundError(f"No existe la carpeta de docs: {docs_path}")
    if db_path.exists() and any(db_path.iterdir()) and not force:
        print("✅ chroma_db ya existe. Saltando ingesta (usa force=True para regenerar).")
        return
    docs = load_pdf_texts(str(docs_path))

    all_chunks = []
    all_metas = []

    for doc in docs:
        text = doc.page_content
        if not text:
            continue

        chunks = chunk_text_sentences(
            text,
            max_sentences=4,
            overlap=1,
            min_chars=200,
            max_chars=1200,
        )

        for idx, ch in enumerate(chunks):
            meta = dict(doc.metadata)
            meta["chunk_id"] = idx
            all_chunks.append(ch)
            all_metas.append(meta)

    print(f"Chunks generados: {len(all_chunks)}")

    if not all_chunks:
        raise RuntimeError("No se generaron chunks. Revisa extracción/limpieza de los PDFs.")

    if db_path.exists():
        shutil.rmtree(db_path)

    embeddings = HuggingFaceEmbeddings(
        model_name="BAAI/bge-m3",
        model_kwargs={"device": "cpu"},
        encode_kwargs={"normalize_embeddings": True},
    )

    Chroma.from_texts(
        texts=all_chunks,
        embedding=embeddings,
        metadatas=all_metas,
        collection_name=COLLECTION_NAME,
        persist_directory=str(db_path),
    )

    print("Base de conocimientos lista.")


if __name__ == "__main__":
    run_ingestion()