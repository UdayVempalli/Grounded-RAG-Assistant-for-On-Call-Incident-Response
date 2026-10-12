"""Retrieval: question -> relevant runbook chunks.

Starts dense-only. TODO (your advanced task):
  1. sparse: rank-bm25 over the chunk corpus, top-20
  2. fuse dense + sparse with RRF (reciprocal rank fusion), keep top-10
  3. rerank top-10 with a cross-encoder, keep top-4
Return: list of {"text", "source", "score"} — sources become citations.
"""
import os

from qdrant_client import QdrantClient
from sentence_transformers import SentenceTransformer

QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333")
COLLECTION = "runbooks"

_model = SentenceTransformer("all-MiniLM-L6-v2")
_client = QdrantClient(url=QDRANT_URL)


def retrieve(question: str, top_k: int = 4) -> list[dict]:
    vector = _model.encode(question).tolist()
    result = _client.query_points(COLLECTION, query=vector, limit=top_k)
    return [
        {"text": h.payload["text"], "source": h.payload["source"], "score": h.score}
        for h in result.points
    ]
