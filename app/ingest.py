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


def _split_words(block: str, size: int, overlap: int) -> list[str]:
    """Split one oversized block at word boundaries, never mid-word.

    A single word longer than `size` is kept whole, never split or dropped.
    Overlap is word-level: the next window starts `overlap` chars before
    the cut, snapped forward to a word start.
    """
    parts, start = [], 0
    n = len(block)
    while start < n:
        if n - start <= size:
            parts.append(block[start:].strip())
            break
        end = start + size
        space = block.rfind(" ", start, end)
        if space > start:
            parts.append(block[start:space].strip())
            nxt_start = max(space - overlap, start + 1)
            s = block.find(" ", nxt_start, space)
            start = s + 1 if s != -1 else space + 1
            continue
        nxt = block.find(" ", start)
        if nxt == -1:
            parts.append(block[start:].strip())
            break
        parts.append(block[start:nxt].strip())
        start = nxt + 1
    return [p for p in parts if p]




def chunk_markdown(text: str, size: int = 500, overlap: int = 50) -> list[str]:
    """Boundary-aware chunking: split on markdown headings and blank lines,
    pack whole blocks into chunks up to `size`; a block longer than `size`
    is split at word boundaries, never mid-word. Each chunk is prefixed
    with its section heading so it stays self-contained."""
    blocks = []
    for line in text.splitlines():
        s = line.strip()
        if not s:
            continue
        blocks.append(("heading" if s.startswith("#") else "para", s))
    chunks: list[str] = []
    cur: list[tuple[str, str]] = []
    cur_len = 0
    cur_heading = ""

    def flush() -> None:
        nonlocal cur, cur_len
        if not cur:
            return
        body = "\n".join(b for _, b in cur)
        if cur_heading and not cur[0][1].startswith("#"):
            body = cur_heading + "\n" + body
        chunks.append(body)
        cur, cur_len = [], 0

    for kind, b in blocks:
        if kind == "heading":
            flush()
            cur_heading = b
            cur = [("heading", b)]
            cur_len = len(b)
            continue
        if len(b) > size:
            # If the current chunk is just the section heading, drop it
            # without emitting: the heading is prepended to the pieces.
            if len(cur) == 1 and cur[0][0] == "heading":
                cur, cur_len = [], 0
            else:
                flush()
            for piece in _split_words(b, size, overlap):
                chunks.append(cur_heading + "\n" + piece if cur_heading else piece)
            continue
        if cur and cur_len + 1 + len(b) > size:
            flush()
        cur.append((kind, b))
        cur_len += 1 + len(b)
    flush()
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
