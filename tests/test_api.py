"""API tests: FastAPI TestClient with mocked retrieval + generation.

No model calls, no live Qdrant/Ollama — retrieve, _generate, and _check are mocked.
Run:  python -m pytest tests/ -v
"""
import json
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


def test_ask_non_ascii_key_401():
    r = client.post(
        "/ask",
        json={"question": "What is step one?"},
        headers={"Authorization": "Bearer caf\u00e9".encode("latin-1")},
    )
    assert r.status_code == 401


def test_ask_unauthenticated_bad_body_401():
    # Auth runs before body validation: no key + bad body -> 401, not 422.
    r = client.post("/ask", json={"question": "x" * 2001})
    assert r.status_code == 401


def test_feedback_ok(tmp_path, monkeypatch):
    monkeypatch.setattr("app.main.FEEDBACK_PATH", tmp_path / "feedback.jsonl")
    r = client.post("/feedback", json={"question": "q", "answer": "a", "helpful": True}, headers=HEADERS)
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}
    lines = (tmp_path / "feedback.jsonl").read_text().strip().splitlines()
    assert len(lines) == 1
    entry = json.loads(lines[0])
    assert entry["question"] == "q" and entry["helpful"] is True


def test_feedback_unauthenticated_401():
    r = client.post("/feedback", json={"question": "q", "answer": "a", "helpful": True})
    assert r.status_code == 401



def test_ingest_ok(monkeypatch):
    monkeypatch.setattr("app.ingest.main", lambda model=None, client=None: "ingested 1 chunks from 1 runbooks")
    monkeypatch.setattr("app.retrieve._get_model", lambda: "model")
    monkeypatch.setattr("app.retrieve._get_client", lambda: "client")
    r = client.post("/ingest", headers=HEADERS)
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_ingest_unauthenticated_401():
    r = client.post("/ingest")
    assert r.status_code == 401



def test_ask_stream_ok(monkeypatch):
    monkeypatch.setattr("app.main.retrieve", lambda q: [{"source": "db-failover.md", "text": "fence the old primary"}])
    monkeypatch.setattr("app.main._generate_stream", lambda q, c, rid: iter(["hello", " world"]))
    with client.stream("POST", "/ask/stream", json={"question": "q"}, headers=HEADERS) as r:
        assert r.status_code == 200
        body = r.read().decode()
    assert "hello" in body and "world" in body and "done" in body


def test_ask_stream_refusal(monkeypatch):
    monkeypatch.setattr("app.main.retrieve", lambda q: [])
    with client.stream("POST", "/ask/stream", json={"question": "q"}, headers=HEADERS) as r:
        assert r.status_code == 200
        body = r.read().decode()
    assert "I don't have a runbook for that" in body


def test_ask_includes_request_id(monkeypatch):
    monkeypatch.setattr("app.main.retrieve", lambda q: [{"source": "db-failover.md", "text": "fence"}])
    monkeypatch.setattr("app.main._generate", lambda q, c, rid: {"response": "fence it"})
    r = client.post("/ask", json={"question": "q"}, headers=HEADERS)
    assert r.status_code == 200
    assert r.json()["request_id"]


def test_feedback_thumbs_down_notifies_slack(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr("app.main._notify_slack", lambda text: calls.append(text))
    monkeypatch.setattr("app.main.FEEDBACK_PATH", tmp_path / "f.jsonl")
    r = client.post("/feedback", json={"question": "q", "answer": "a", "helpful": False}, headers=HEADERS)
    assert r.status_code == 200
    assert len(calls) == 1 and "q" in calls[0]


def test_feedback_thumbs_up_no_slack(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr("app.main._notify_slack", lambda text: calls.append(text))
    monkeypatch.setattr("app.main.FEEDBACK_PATH", tmp_path / "f.jsonl")
    r = client.post("/feedback", json={"question": "q", "answer": "a", "helpful": True}, headers=HEADERS)
    assert r.status_code == 200
    assert calls == []


def test_notify_slack_no_webhook_noop(monkeypatch):
    calls = []
    monkeypatch.delenv("SLACK_WEBHOOK_URL", raising=False)
    monkeypatch.setattr("app.main.httpx.post", lambda *a, **k: calls.append((a, k)))
    from app.main import _notify_slack
    _notify_slack("hi")
    assert calls == []


def test_notify_slack_posts_when_configured(monkeypatch):
    calls = []
    monkeypatch.setenv("SLACK_WEBHOOK_URL", "https://hooks.slack.com/test")
    monkeypatch.setattr("app.main.httpx.post", lambda *a, **k: calls.append((a, k)))
    from app.main import _notify_slack
    _notify_slack("hello")
    assert len(calls) == 1
    assert calls[0][0][0] == "https://hooks.slack.com/test"


def test_ask_stream_ollama_error(monkeypatch):
    monkeypatch.setattr("app.main.retrieve", lambda q: [{"source": "db-failover.md", "text": "fence"}])
    def boom(q, c, rid):
        raise httpx.HTTPError("boom")
    monkeypatch.setattr("app.main._generate_stream", boom)
    with client.stream("POST", "/ask/stream", json={"question": "q"}, headers=HEADERS) as r:
        assert r.status_code == 200
        body = r.read().decode()
    assert "generation service unavailable" in body


def test_ingest_concurrent_409():
    from app.main import INGEST_LOCK
    INGEST_LOCK.acquire()
    try:
        r = client.post("/ingest", headers=HEADERS)
        assert r.status_code == 409
    finally:
        INGEST_LOCK.release()
