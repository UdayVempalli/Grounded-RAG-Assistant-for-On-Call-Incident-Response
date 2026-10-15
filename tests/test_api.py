"""API tests: FastAPI TestClient with mocked retrieval + generation.

No model calls, no live Qdrant/Ollama — retrieve, _generate, and _check are mocked.
Run:  python -m pytest tests/ -v
"""
from unittest.mock import patch

import httpx
import pytest
from fastapi.testclient import TestClient

from app.main import REFUSAL_TEXT, _RATE_BUCKETS, app

client = TestClient(app)

HEADERS = {"Authorization": "Bearer test-key"}


@pytest.fixture(autouse=True)
def _auth_env(monkeypatch):
    """Every /ask test runs with a configured API key and a fresh rate bucket."""
    monkeypatch.setenv("RUNBOOKQA_API_KEY", "test-key")
    monkeypatch.setenv("RUNBOOKQA_RATE_LIMIT", "100")
    monkeypatch.setenv("RUNBOOKQA_RATE_WINDOW_S", "60")
    _RATE_BUCKETS.clear()
    yield
    _RATE_BUCKETS.clear()

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
    r = client.post("/ask", json={"question": "What is step one?"}, headers=HEADERS)
    assert r.status_code == 200
    body = r.json()
    assert body["answer"] == "Do step one."
    assert body["sources"] == ["k8s-crashloop.md"]


@patch("app.main._generate")
@patch("app.main.retrieve", return_value=[])
def test_ask_empty_retrieval_refuses_without_model_call(mock_retrieve, mock_generate):
    r = client.post("/ask", json={"question": "What is the vacation policy?"}, headers=HEADERS)
    assert r.status_code == 200
    body = r.json()
    assert body["answer"] == REFUSAL_TEXT
    assert body["sources"] == []
    mock_generate.assert_not_called()


def test_ask_empty_question_400():
    r = client.post("/ask", json={"question": "   "}, headers=HEADERS)
    assert r.status_code == 400


def test_ask_overlong_question_422():
    r = client.post("/ask", json={"question": "x" * 2001}, headers=HEADERS)
    assert r.status_code == 422


@patch("app.main._generate", side_effect=httpx.HTTPError("down"))
@patch("app.main.retrieve", return_value=CHUNKS)
def test_ask_generation_down_503(mock_retrieve, mock_generate):
    r = client.post("/ask", json={"question": "What is step one?"}, headers=HEADERS)
    assert r.status_code == 503
    assert r.json()["detail"] == "generation service unavailable"


def test_ask_wrong_key_401():
    r = client.post(
        "/ask",
        json={"question": "What is step one?"},
        headers={"Authorization": "Bearer wrong"},
    )
    assert r.status_code == 401


def test_ask_unconfigured_503(monkeypatch):
    monkeypatch.delenv("RUNBOOKQA_API_KEY", raising=False)
    r = client.post("/ask", json={"question": "What is step one?"}, headers=HEADERS)
    assert r.status_code == 503


@patch("app.main._generate", return_value={"response": "Do step one.", "prompt_eval_count": 10, "eval_count": 5})
@patch("app.main.retrieve", return_value=CHUNKS)
def test_ask_rate_limited_429(mock_retrieve, mock_generate, monkeypatch):
    monkeypatch.setenv("RUNBOOKQA_RATE_LIMIT", "1")
    r1 = client.post("/ask", json={"question": "What is step one?"}, headers=HEADERS)
    assert r1.status_code == 200
    r2 = client.post("/ask", json={"question": "What is step one?"}, headers=HEADERS)
    assert r2.status_code == 429
    assert "Retry-After" in r2.headers
