"""Retrieval: hybrid (dense + BM25, RRF fusion) + cross-encoder rerank.

Pipeline:
  1. dense: embed question, Qdrant top-20
  2. sparse: BM25 over the chunk corpus, top-20
  3. RRF fuse: score = sum 1/(60 + rank) across both lists, keep top-10
  4. rerank: cross-encoder scores (question, chunk) pairs, keep top-4
"""
import os
import re

from rank_bm25 import BM25Okapi

QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333")
COLLECTION = "runbooks"
RRF_K = 60

_model = None
_reranker = None
_client = None


def _get_model():
    global _model
    if _model is None:
        # Imported here, not at module top: importing sentence_transformers
        # pulls in torch (~20s). Models load on first use, never at import,
        # so tests stay fast and work offline.
        from sentence_transformers import SentenceTransformer

        _model = SentenceTransformer("all-MiniLM-L6-v2")
    return _model


def _get_reranker():
    global _reranker
    if _reranker is None:
        from sentence_transformers import CrossEncoder

        _reranker = CrossEncoder("cross-encoder/ms-marco-MiniLM-L-6-v2")
    return _reranker


def _get_client():
    global _client
    if _client is None:
        from qdrant_client import QdrantClient

        _client = QdrantClient(url=QDRANT_URL)
    return _client




def _tokenize(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", text.lower())


def _load_corpus():
    # No cache: reload on every query so a re-ingest is visible without an
    # API restart. The scroll is ~ms at this corpus size.
    points, _ = _get_client().scroll(COLLECTION, limit=1000, with_payload=True)
    # Deterministic corpus order: never depend on Qdrant's scroll order.
    points.sort(key=lambda p: str(p.id))
    corpus = [
        {"id": p.id, "text": p.payload["text"], "source": p.payload["source"]}
        for p in points
    ]
    bm25 = BM25Okapi([_tokenize(c["text"]) for c in corpus])
    return corpus, bm25


def _rrf_fuse(dense_ids: list, sparse_ids: list, top_n: int = 10) -> list:
    scores: dict = {}
    for rank, pid in enumerate(dense_ids):
        scores[pid] = scores.get(pid, 0) + 1 / (RRF_K + rank + 1)
    for rank, pid in enumerate(sparse_ids):
        scores[pid] = scores.get(pid, 0) + 1 / (RRF_K + rank + 1)
    # Tie-break by point ID so fusion is deterministic.
    return sorted(scores, key=lambda pid: (scores[pid], str(pid)), reverse=True)[:top_n]


def retrieve(question: str, top_k: int = 4) -> list[dict]:
    corpus, bm25 = _load_corpus()
    by_id = {c["id"]: c for c in corpus}

    # 1. dense
    vector = _get_model().encode(question).tolist()
    dense = _get_client().query_points(COLLECTION, query=vector, limit=20)
    dense_ids = [p.id for p in dense.points]

    # 2. sparse
    sparse_scores = bm25.get_scores(_tokenize(question))
    ranked = sorted(range(len(corpus)),
                    key=lambda i: (sparse_scores[i], str(corpus[i]["id"])), reverse=True)[:20]
    sparse_ids = [corpus[i]["id"] for i in ranked]

    # 3. fuse
    fused = _rrf_fuse(dense_ids, sparse_ids, top_n=10)

    # 4. rerank (question, chunk) pairs, keep top-k
    pairs = [[question, by_id[pid]["text"]] for pid in fused]
    rerank_scores = _get_reranker().predict(pairs)
    order = sorted(range(len(fused)),
                   key=lambda i: (rerank_scores[i], str(fused[i])), reverse=True)[:top_k]

    return [
        {"text": by_id[fused[i]]["text"],
         "source": by_id[fused[i]]["source"],
         "score": float(rerank_scores[i])}
        for i in order
    ]
