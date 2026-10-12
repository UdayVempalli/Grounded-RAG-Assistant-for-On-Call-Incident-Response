"""Ingestion: runbooks/*.md -> chunks -> embeddings -> Qdrant.

Run:  python -m app.ingest
"""
import os
from pathlib import Path

from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams
from sentence_transformers import SentenceTransformer

QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333")
COLLECTION = "runbooks"
EMBED_MODEL = "all-MiniLM-L6-v2"  # 384-dim, fast, free, local

RUNBOOK_DIR = Path(__file__).resolve().parent.parent / "data" / "runbooks"


def chunk_markdown(text: str, size: int = 500, overlap: int = 50) -> list[str]:
    """Fixed-size char chunking. TODO: compare against section-aware chunking
    (split on ## headers) and keep the winner — measure with eval.py."""
    chunks, start = [], 0
    while start < len(text):
        chunks.append(text[start:start + size])
        start += size - overlap
    return [c.strip() for c in chunks if c.strip()]


def main() -> None:
    model = SentenceTransformer(EMBED_MODEL)
    client = QdrantClient(url=QDRANT_URL)

    client.recreate_collection(
        COLLECTION,
        vectors_config=VectorParams(size=384, distance=Distance.COSINE),
    )

    points, pid = [], 0
    for md_file in sorted(RUNBOOK_DIR.glob("*.md")):
        text = md_file.read_text()
        chunks = chunk_markdown(text)
        vectors = model.encode(chunks, show_progress_bar=True)
        for chunk, vector in zip(chunks, vectors):
            points.append(PointStruct(
                id=pid,
                vector=vector.tolist(),
                payload={"source": md_file.name, "text": chunk},
            ))
            pid += 1

    client.upsert(COLLECTION, points)
    print(f"ingested {pid} chunks from {len(list(RUNBOOK_DIR.glob('*.md')))} runbooks")


if __name__ == "__main__":
    main()
