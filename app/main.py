"""FastAPI service: grounded answers over runbooks, with citations.

POST /ask {"question": "..."} -> {"answer": "...", "sources": [...]}
GET  /health
GET  /metrics  (Prometheus)
"""
import os
import time

import httpx
from fastapi import FastAPI
from prometheus_client import Counter, Histogram, generate_latest
from pydantic import BaseModel

from .retrieve import retrieve

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
OLLAMA_BIN = os.getenv("OLLAMA_BIN", "ollama")
LLM_MODEL = os.getenv("LLM_MODEL", "llama3.2:3b")

ASK_LATENCY = Histogram("runbookqa_ask_latency_seconds", "Latency of /ask")
ASK_COUNT = Counter("runbookqa_ask_total", "Total /ask requests")

PROMPT = """Answer the on-call engineer's question using ONLY the runbook context below.
If the context doesn't contain the answer, say "I don't have a runbook for that." Do not invent steps.
Cite the runbook filename for each step you reference.

Context:
{context}

Question: {question}

Answer:"""

app = FastAPI(title="RunbookQA")


class AskRequest(BaseModel):
    question: str


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/metrics")
def metrics():
    from fastapi.responses import Response
    return Response(generate_latest(), media_type="text/plain")


@app.post("/ask")
def ask(req: AskRequest):
    start = time.time()
    ASK_COUNT.inc()
    try:
        chunks = retrieve(req.question)
        context = "\n\n---\n\n".join(
            f"[{c['source']}]\n{c['text']}" for c in chunks
        )
        resp = httpx.post(
            f"{OLLAMA_URL}/api/generate",
            json={"model": LLM_MODEL, "prompt": PROMPT.format(
                context=context, question=req.question), "stream": False},
            timeout=120,
        )
        resp.raise_for_status()
        answer = resp.json()["response"]
        sources = sorted({c["source"] for c in chunks})
        return {"answer": answer, "sources": sources}
    finally:
        ASK_LATENCY.observe(time.time() - start)
