"""Unit tests: chunking, point IDs, judge evidence check.

No model calls, no live services — httpx is mocked for the judge tests.
Run:  python -m pytest tests/ -v
"""
import uuid
from unittest.mock import Mock, patch

from app.eval import judge
from app.ingest import _point_id, chunk_markdown


def test_chunk_markdown_splits_with_overlap():
    assert chunk_markdown("abcdefghij", size=4, overlap=1) == [
        "abcd", "defg", "ghij", "j",
    ]


def test_chunk_markdown_empty_and_blank():
    assert chunk_markdown("") == []
    assert chunk_markdown("   ") == []


def test_point_id_deterministic():
    assert _point_id("a.md", 0) == _point_id("a.md", 0)
    assert _point_id("a.md", 0) != _point_id("a.md", 1)
    assert _point_id("a.md", 0) != _point_id("b.md", 0)
    uuid.UUID(_point_id("a.md", 0))  # valid UUID format


def _mock_judge_response(text: str):
    resp = Mock()
    resp.json.return_value = {"response": text}
    resp.raise_for_status.return_value = None
    return resp


CHUNKS = [{"source": "failed-deploy.md", "text": "Roll back immediately: kubectl rollout undo"}]


@patch("app.eval.httpx.post")
def test_judge_pass(mock_post):
    mock_post.return_value = _mock_judge_response("VERDICT: PASS\nREASON: none.")
    passed, _ = judge("q?", CHUNKS, "Roll back immediately.")
    assert passed is True


@patch("app.eval.httpx.post")
def test_judge_fail_stands_when_claim_absent(mock_post):
    mock_post.return_value = _mock_judge_response(
        'VERDICT: FAIL\nREASON: The ANSWER adds a step "smoke query suite" not in the CONTEXT.'
    )
    passed, _ = judge("q?", CHUNKS, "Run the smoke query suite.")
    assert passed is False


@patch("app.eval.httpx.post")
def test_judge_fail_overruled_when_claim_present(mock_post):
    mock_post.return_value = _mock_judge_response(
        'VERDICT: FAIL\nREASON: The ANSWER adds a step "Roll back immediately" not in the CONTEXT.'
    )
    passed, reason = judge("q?", CHUNKS, "Roll back immediately.")
    assert passed is True
    assert "overruled" in reason


@patch("app.eval.httpx.post")
def test_judge_unparseable_fails_closed(mock_post):
    mock_post.return_value = _mock_judge_response("I am not sure about this one.")
    passed, reason = judge("q?", CHUNKS, "something")
    assert passed is False
    assert "unparseable" in reason


@patch("app.eval.httpx.post")
def test_judge_fail_without_quote_fails_closed(mock_post):
    mock_post.return_value = _mock_judge_response(
        "VERDICT: FAIL\nREASON: something is off."
    )
    passed, _ = judge("q?", CHUNKS, "something")
    assert passed is False


@patch("app.eval.httpx.post")
def test_judge_fail_stands_when_claim_not_in_answer(mock_post):
    # Quote is in the context but the answer never made that claim:
    # the judge cited the wrong evidence, so FAIL stands.
    mock_post.return_value = _mock_judge_response(
        'VERDICT: FAIL\nREASON: The ANSWER adds a step "Roll back immediately" not in the CONTEXT.'
    )
    passed, _ = judge("q?", CHUNKS, "Do something else entirely.")
    assert passed is False


@patch("app.eval.httpx.post")
def test_judge_fail_stands_when_any_cited_claim_absent(mock_post):
    # One cited claim is grounded, the other is not: FAIL stands.
    mock_post.return_value = _mock_judge_response(
        'VERDICT: FAIL\nREASON: The ANSWER adds "Roll back immediately" and "smoke query suite".'
    )
    passed, _ = judge("q?", CHUNKS, "Roll back immediately and run the smoke query suite.")
    assert passed is False
