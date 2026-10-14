"""API tests: FastAPI TestClient with mocked retrieval + generation.

No model calls, no live Qdrant/Ollama — retrieve, _generate, and _check are mocked.
Run:  python -m pytest tests/ -v
"""
from unittest.mock import patch

import httpx
from fastapi.testclient import TestClient

from app.main import REFUSAL_TEXT, app

client = TestClient(app)

CHUNKS = [{"source": "k8s-crashloop.md", "text": "kubectl describe pod"}]


def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_metrics_exposes_runbookqa():
    r = client.get("/metrics")
    assert r.status_code == 200
    assert "runbookqa_ask_total" in r.text


@patch("app.main._check", side_effect=[(True, "HTTP 200"), (True, "HTTP 200")])
def test_ready_ok(mock_check):
    r = client.get("/ready")
    assert r.status_code == 200
    assert r.json()["status"] == "ready"


@patch("app.main._check", side_effect=[(False, "boom"), (True, "HTTP 200")])
def test_ready_not_ready(mock_check):
    r = client.get("/ready")
    assert r.status_code == 503
    assert r.json()["status"] == "not_ready"


@patch("app.main._generate", return_value={"response": "Do step one.", "prompt_eval_count": 10, "eval_count": 5})
@patch("app.main.retrieve", return_value=CHUNKS)
def test_ask_answered(mock_retrieve, mock_generate):
    r = client.post("/ask", json={"question": "What is step one?"})
    assert r.status_code == 200
    body = r.json()
    assert body["answer"] == "Do step one."
    assert body["sources"] == ["k8s-crashloop.md"]


@patch("app.main._generate")
@patch("app.main.retrieve", return_value=[])
def test_ask_empty_retrieval_refuses_without_model_call(mock_retrieve, mock_generate):
    r = client.post("/ask", json={"question": "What is the vacation policy?"})
    assert r.status_code == 200
    body = r.json()
    assert body["answer"] == REFUSAL_TEXT
    assert body["sources"] == []
    mock_generate.assert_not_called()


def test_ask_empty_question_400():
    r = client.post("/ask", json={"question": "   "})
    assert r.status_code == 400


def test_ask_overlong_question_422():
    r = client.post("/ask", json={"question": "x" * 2001})
    assert r.status_code == 422


@patch("app.main._generate", side_effect=httpx.HTTPError("down"))
@patch("app.main.retrieve", return_value=CHUNKS)
def test_ask_generation_down_503(mock_retrieve, mock_generate):
    r = client.post("/ask", json={"question": "What is step one?"})
    assert r.status_code == 503
    assert r.json()["detail"] == "generation service unavailable"
