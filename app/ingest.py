"""Ingestion: runbooks/*.md -> chunks -> embeddings -> Qdrant.

Idempotent: re-running ingest produces the same end state — no duplicates,
no wipe. Deterministic point IDs (UUID5 of source + chunk index) make
upserts overwrite in place; per-source replace drops stale chunks from
edited runbooks; deleted runbooks are cleaned up.

Run:  python -m app.ingest
"""
from __future__ import annotations

import os
import uuid
from pathlib import Path

# Heavy imports (torch, qdrant_client) live inside the functions that use
# them: importing this module must stay fast so tests can import the pure
# helpers (chunk_markdown, _point_id) without loading torch.

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
    from qdrant_client.models import FieldCondition, Filter, MatchValue

    client.delete(
        COLLECTION,
        points_selector=Filter(
            must=[FieldCondition(key="source", match=MatchValue(value=source))]
        ),
    )


def _load_model():
    """Load the embedding model. Kept behind a helper so tests can inject
    a mock without importing sentence_transformers (which pulls in torch)."""
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer(EMBED_MODEL)


def _load_client():
    """Build the Qdrant client. Same lazy-import reason as _load_model."""
    from qdrant_client import QdrantClient

    return QdrantClient(url=QDRANT_URL)


def main(model=None, client=None) -> None:
    from qdrant_client.models import (
        Distance,
        FieldCondition,
        Filter,
        MatchValue,
        PointStruct,
        VectorParams,
    )

    model = model or _load_model()
    client = client or _load_client()

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
        # Upload-then-delete: upsert the new chunks first, then delete only
        # the old IDs no longer used. Queries never see a gap for this source.
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
        new_ids = {pt.id for pt in points}
        if points:
            client.upsert(COLLECTION, points)
        total += len(points)
        offset = None
        while True:
            records, offset = client.scroll(
                COLLECTION,
                scroll_filter=Filter(
                    must=[FieldCondition(key="source", match=MatchValue(value=source))]
                ),
                with_payload=False,
                limit=1000,
                offset=offset,
            )
            stale_ids = [r.id for r in records if r.id not in new_ids]
            if stale_ids:
                client.delete(COLLECTION, points_selector=stale_ids)
            if offset is None:
                break

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
