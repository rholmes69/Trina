"""Trina Document RAG — index workspace files with ChromaDB + sentence-transformers.

Usage
-----
Index (or re-index) the workspace:
    python rag.py --index

Search from the terminal:
    python rag.py --search "client proposal last month"
    python rag.py --search "meeting notes" --n 8

The index is stored in <TRINA_WORKSPACE>/.rag_index/ and persists across runs.
Call index_workspace() again any time files change to keep it fresh.

Supported file types: .txt  .md  .pdf  .docx  .csv  .json  .py  .js  .html
"""

import os
from pathlib import Path
from typing import Generator

# ── Config ────────────────────────────────────────────────────────────────────

WORKSPACE  = Path(os.getenv("TRINA_WORKSPACE", Path.home() / "TrinaDocs"))
CHROMA_DIR = WORKSPACE / ".rag_index"
COLLECTION = "workspace_docs"
EMBED_MODEL = "all-MiniLM-L6-v2"   # 80 MB, fast on CPU, good quality

CHUNK_WORDS   = 400
CHUNK_OVERLAP = 50

SUPPORTED = {".txt", ".md", ".pdf", ".docx", ".csv", ".json", ".py", ".js", ".html"}


# ── Text chunking ─────────────────────────────────────────────────────────────

def _chunks(text: str) -> Generator[str, None, None]:
    words = text.split()
    start = 0
    while start < len(words):
        end = min(start + CHUNK_WORDS, len(words))
        yield " ".join(words[start:end])
        if end == len(words):
            break
        start += CHUNK_WORDS - CHUNK_OVERLAP


# ── Text extraction ───────────────────────────────────────────────────────────

def _extract(path: Path) -> str:
    suffix = path.suffix.lower()

    if suffix == ".pdf":
        try:
            import pypdf
            reader = pypdf.PdfReader(str(path))
            return "\n".join(page.extract_text() or "" for page in reader.pages)
        except Exception:
            return ""

    if suffix == ".docx":
        try:
            import docx
            doc = docx.Document(str(path))
            return "\n".join(p.text for p in doc.paragraphs)
        except Exception:
            return ""

    try:
        return path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return ""


# ── ChromaDB collection (lazy singleton) ──────────────────────────────────────

_collection = None


def _get_collection():
    global _collection
    if _collection is not None:
        return _collection

    import chromadb
    from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction

    CHROMA_DIR.mkdir(parents=True, exist_ok=True)
    client = chromadb.PersistentClient(path=str(CHROMA_DIR))
    ef = SentenceTransformerEmbeddingFunction(model_name=EMBED_MODEL)
    _collection = client.get_or_create_collection(COLLECTION, embedding_function=ef)
    return _collection


# ── Public: index ─────────────────────────────────────────────────────────────

def index_workspace(verbose: bool = False) -> str:
    """Walk WORKSPACE, chunk all supported files, upsert into ChromaDB."""
    col     = _get_collection()
    indexed = 0
    skipped = 0

    for path in WORKSPACE.rglob("*"):
        if not path.is_file():
            continue
        if path.suffix.lower() not in SUPPORTED:
            continue
        # Skip hidden dirs (e.g. .rag_index itself)
        if any(part.startswith(".") for part in path.parts):
            continue

        text = _extract(path)
        if not text.strip():
            skipped += 1
            continue

        rel  = path.relative_to(WORKSPACE).as_posix()
        ids, docs, metas = [], [], []

        for i, chunk in enumerate(_chunks(text)):
            if not chunk.strip():
                continue
            ids.append(f"{rel}::chunk{i}")
            docs.append(chunk)
            metas.append({"source": rel, "chunk": i})

        if ids:
            col.upsert(ids=ids, documents=docs, metadatas=metas)
            indexed += 1
            if verbose:
                print(f"[rag] indexed {rel}  ({len(ids)} chunks)")

    total = col.count()
    return (
        f"Indexed {indexed} files ({skipped} skipped — empty or unsupported). "
        f"Index now holds {total} chunks."
    )


# ── Public: search ────────────────────────────────────────────────────────────

def search(query: str, n: int = 5) -> str:
    """Semantic search across indexed workspace documents. Returns formatted results."""
    col   = _get_collection()
    count = col.count()

    if count == 0:
        return (
            "No documents are indexed yet. "
            "Ask Trina to index your workspace, or run: python rag.py --index"
        )

    results   = col.query(query_texts=[query], n_results=min(n, count))
    docs      = results["documents"][0]
    metadatas = results["metadatas"][0]
    distances = results["distances"][0]

    if not docs:
        return f"No results found for: {query!r}"

    lines = [f"Search results for: {query!r}", ""]
    for doc, meta, dist in zip(docs, metadatas, distances):
        score   = round(1.0 - dist, 3)
        source  = meta.get("source", "unknown")
        preview = doc[:300].replace("\n", " ")
        lines.append(f"[{score:.2f}] {source}")
        lines.append(f"  {preview}{'…' if len(doc) > 300 else ''}")
        lines.append("")

    return "\n".join(lines).strip()


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    from dotenv import load_dotenv
    load_dotenv()

    # Re-resolve WORKSPACE after .env is loaded
    WORKSPACE  = Path(os.getenv("TRINA_WORKSPACE", Path.home() / "TrinaDocs"))
    CHROMA_DIR = WORKSPACE / ".rag_index"

    parser = argparse.ArgumentParser(description="Trina document index")
    parser.add_argument("--index",  action="store_true", help="Rebuild the RAG index")
    parser.add_argument("--search", metavar="QUERY",     help="Semantic search the index")
    parser.add_argument("--n",      type=int, default=5, help="Number of results (default 5)")
    args = parser.parse_args()

    if args.index:
        print(index_workspace(verbose=True))
    elif args.search:
        print(search(args.search, n=args.n))
    else:
        parser.print_help()
