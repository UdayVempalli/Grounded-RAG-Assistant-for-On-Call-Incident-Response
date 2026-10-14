"""Retrieval: question -> relevant runbook chunks.

Starts dense-only. TODO (your advanced task):
  1. sparse: rank-bm25 over the chunk corpus, top-20
  2. fuse dense + sparse with RRF (reciprocal rank fusion), keep top-10
  3. rerank top-10 with a cross-encoder, keep top-4
Return: list of {"text", "source", "score"} — sources become citations.

Model + client are loaded lazily on first use, not at import: importing this
module must never download weights or touch the network, so tests stay fast
and work offline.
"""
import os

from qdrant_client import QdrantClient
from sentence_transformers import SentenceTransformer

QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333")
COLLECTION = "runbooks"
EMBED_MODEL = "all-MiniLM-L6-v2"

_model = None
_client = None


def _get_model():
    global _model
    if _model is None:
        _model = SentenceTransformer(EMBED_MODEL)
    return _model


def _get_client():
    global _client
    if _client is None:
        _client = QdrantClient(url=QDRANT_URL)
    return _client


def retrieve(question: str, top_k: int = 4) -> list[dict]:
    vector = _get_model().encode(question).tolist()
    result = _get_client().query_points(COLLECTION, query=vector, limit=top_k)
    return [
        {"text": h.payload["text"], "source": h.payload["source"], "score": h.score}
        for h in result.points
    ]
