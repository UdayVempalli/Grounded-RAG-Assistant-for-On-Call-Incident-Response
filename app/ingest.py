"""Ingestion: runbooks/*.md -> chunks -> embeddings -> Qdrant.

Idempotent: re-running ingest produces the same end state — no duplicates,
no wipe. Deterministic point IDs (UUID5 of source + chunk index) make
upserts overwrite in place; per-source replace drops stale chunks from
edited runbooks; deleted runbooks are cleaned up.

Run:  python -m app.ingest
"""
import os
import uuid
from pathlib import Path

from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    FieldCondition,
    Filter,
    MatchValue,
    PointStruct,
    VectorParams,
)
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


def _point_id(source: str, index: int) -> str:
    """Deterministic point ID: same (source, chunk) -> same ID, every run."""
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"{source}:{index}"))


def _delete_source(client: QdrantClient, source: str) -> None:
    client.delete(
        COLLECTION,
        points_selector=Filter(
            must=[FieldCondition(key="source", match=MatchValue(value=source))]
        ),
    )


def main() -> None:
    model = SentenceTransformer(EMBED_MODEL)
    client = QdrantClient(url=QDRANT_URL)

    # Create if missing — never wipe. Re-runs update in place.
    try:
        client.get_collection(COLLECTION)
    except Exception:
        client.create_collection(
            COLLECTION,
            vectors_config=VectorParams(size=384, distance=Distance.COSINE),
        )

    current_sources = set()
    total = 0
    for md_file in sorted(RUNBOOK_DIR.glob("*.md")):
        source = md_file.name
        current_sources.add(source)
        # Per-source replace: drop this file's old chunks, then upsert the new
        # ones. An edited runbook never leaves stale chunks behind.
        _delete_source(client, source)
        text = md_file.read_text()
        chunks = chunk_markdown(text)
        vectors = model.encode(chunks, show_progress_bar=True)
        points = [
            PointStruct(
                id=_point_id(source, i),
                vector=vector.tolist(),
                payload={"source": source, "text": chunk},
            )
            for i, (chunk, vector) in enumerate(zip(chunks, vectors))
        ]
        if points:
            client.upsert(COLLECTION, points)
        total += len(points)

    # Remove chunks belonging to runbooks deleted since the last ingest.
    stored_sources = set()
    offset = None
    while True:
        records, offset = client.scroll(
            COLLECTION, with_payload=True, limit=1000, offset=offset
        )
        stored_sources.update(r.payload["source"] for r in records)
        if offset is None:
            break
    for stale in stored_sources - current_sources:
        _delete_source(client, stale)
        print(f"removed stale runbook: {stale}")

    print(f"ingested {total} chunks from {len(current_sources)} runbooks")


if __name__ == "__main__":
    main()
