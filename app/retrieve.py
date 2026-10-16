"""Retrieval: hybrid (dense + BM25, RRF fusion) + cross-encoder rerank.

Pipeline:
  1. dense: embed question, Qdrant top-20
  2. sparse: BM25 over the chunk corpus, top-20
  3. RRF fuse: score = sum 1/(60 + rank) across both lists, keep top-10
  4. rerank: cross-encoder scores (question, chunk) pairs, keep top-4
  5. gate: best score below MIN_RERANK_SCORE -> [] (refuse, no LLM call)
  6. expand: the top chunk becomes its full runbook (small-to-big)
"""
import os
import re

from rank_bm25 import BM25Okapi

QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333")
COLLECTION = "runbooks"
RRF_K = 60
# Minimum cross-encoder score for a chunk to count as relevant. Set at -6.0
# on the 55-question golden set (max margin), and re-measured on Oct 16 with
# title-prefixed chunks on 20 runbooks: answerable golden questions bottom
# out at -1.01, unanswerable ones top out at -8.88, so -6.0 still sits well
# inside the gap. Re-measure whenever chunking or the corpus changes: the
# scores are not calibrated.
MIN_RERANK_SCORE = -6.0
# A second runbook whose best chunk scores within this margin of the top
# runbook is also expanded: the reranker cannot reliably separate them (a
# CrashLoopBackOff question ranked k8s-image-pull.md, which mentions
# CrashLoopBackOff in passing, above k8s-crashloop.md), so the model sees both.
EXPAND_MARGIN = 1.0

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
    # Page through all points: a single scroll caps at `limit`, so a corpus
    # larger than 1000 chunks would silently lose the rest from BM25.
    points: list = []
    offset = None
    while True:
        batch, offset = _get_client().scroll(
            COLLECTION, limit=1000, offset=offset, with_payload=True
        )
        points.extend(batch)
        if offset is None:
            break
    if not points:
        return [], None
    # Deterministic corpus order: never depend on Qdrant's scroll order.
    points.sort(key=lambda p: str(p.id))
    corpus = [
        {"id": p.id, "text": p.payload["text"], "source": p.payload["source"],
         # Full parent runbook; absent in indexes built before it was added.
         "doc": p.payload.get("doc")}
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
    if not corpus:
        # Empty index (fresh deploy, before ingest): no chunks to rank.
        # Return [] so /ask takes the refusal path instead of crashing
        # in BM25 (ZeroDivisionError on an empty corpus).
        return []
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

    if not order or rerank_scores[order[0]] < MIN_RERANK_SCORE:
        # Cheap refusal: even the best chunk is irrelevant, so the question
        # is out of corpus. Return [] so /ask refuses without a model call
        # (the pre-hybrid behavior for out-of-corpus questions).
        return []

    # Small-to-big, bounded: the best match is expanded to its whole runbook
    # so the model sees the full fix (Symptoms + Diagnosis + Mitigation);
    # the runner-up runbook too, only when it scores within EXPAND_MARGIN.
    # Everything else stays a section chunk. Expanding every hit tripled the
    # context (~880 -> ~2650 chars) and the 3B model began answering with
    # bare filenames or refusing questions the context answered (CI run #31).
    top_score = float(rerank_scores[order[0]])
    expanded: set[str] = set()
    results = []
    for i in order:
        c = by_id[fused[i]]
        if c["source"] in expanded:
            continue  # already inside an expanded runbook
        score = float(rerank_scores[i])
        if not expanded or (len(expanded) < 2 and top_score - score <= EXPAND_MARGIN):
            expanded.add(c["source"])
            results.append({"text": c.get("doc") or c["text"], "source": c["source"], "score": score})
        else:
            results.append({"text": c["text"], "source": c["source"], "score": score})
    return results
