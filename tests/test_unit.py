"""Unit tests: chunking, point IDs, judge evidence check.

No model calls, no live services — httpx is mocked for the judge tests.
Run:  python -m pytest tests/ -v
"""
import uuid
from unittest.mock import Mock, patch

from app.eval import _normalize_quote, judge
from app.ingest import _point_id, chunk_markdown


def test_chunk_markdown_never_splits_mid_word():
    # A spaceless string is one word: kept whole, never dropped or split.
    assert chunk_markdown("abcdefghij", size=4, overlap=1) == ["abcdefghij"]
    # A long block splits at word boundaries, never mid-word.
    assert chunk_markdown("aaa bbb ccc", size=5, overlap=1) == ["aaa", "bbb", "ccc"]


def test_chunk_markdown_heading_sections():
    assert chunk_markdown("## A\n\nhello\n\n## B\n\nworld") == [
        "## A\nhello",
        "## B\nworld",
    ]


def test_chunk_markdown_heading_prepended():
    # Chunks starting mid-section carry their section heading.
    assert chunk_markdown("## Sec\n\nhello\nworld\nfoo\nbar", size=12, overlap=0) == [
        "## Sec\nhello",
        "## Sec\nworld\nfoo",
        "## Sec\nbar",
    ]


def test_chunk_markdown_oversized_block():
    # One long line splits at word boundaries; no bare-heading chunk.
    assert chunk_markdown("## Sec\n\nhello world foo bar", size=12, overlap=0) == [
        "## Sec\nhello world",
        "## Sec\nfoo bar",
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


def test_ingest_upserts_before_deleting_stale():
    # Upload-then-delete: for each runbook, upsert must precede any delete
    # of that runbook's stale chunks, so queries never see a gap.
    # Model + client are injected (not patched): patching the source modules
    # would import sentence_transformers, which pulls in torch (~18s).
    from app.ingest import main as ingest_main

    mock_client = Mock()
    stale = Mock(id="stale-id-1")
    mock_client.scroll.side_effect = [([stale], None)] * 5 + [([], None)]
    mock_model = Mock()
    mock_model.encode.return_value = [Mock(tolist=lambda: [0.1, 0.2])]
    ingest_main(model=mock_model, client=mock_client)
    calls = [c[0] for c in mock_client.method_calls]
    assert calls.index("upsert") < calls.index("delete")


def test_normalize_quote_strips_filler_verb():
    assert _normalize_quote("use `kubectl drain <node>`") == "`kubectl drain <node>`"
    assert _normalize_quote("`kubectl get pods`") == "`kubectl get pods`"
    assert _normalize_quote("Run `kubectl get pods`") == "`kubectl get pods`"


def test_retrieve_empty_corpus_returns_empty():
    from unittest.mock import Mock, patch
    from app.retrieve import retrieve
    mock_client = Mock()
    mock_client.scroll.return_value = ([], None)
    with patch("app.retrieve._get_client", return_value=mock_client):
        assert retrieve("anything") == []


def test_load_corpus_pages_through_scroll():
    from unittest.mock import Mock, patch
    from app.retrieve import _load_corpus

    def point(pid, text):
        m = Mock()
        m.id = pid
        m.payload = {"text": text, "source": "s"}
        return m

    mock_client = Mock()
    mock_client.scroll.side_effect = [
        ([point("1", "a"), point("2", "b")], "next"),
        ([point("3", "c")], None),
    ]
    with patch("app.retrieve._get_client", return_value=mock_client):
        corpus, _ = _load_corpus()
    assert [c["id"] for c in corpus] == ["1", "2", "3"]


def test_retrieve_below_threshold_returns_empty():
    from unittest.mock import Mock, patch
    import app.retrieve as R
    from app.retrieve import retrieve
    corpus = [{"id": "1", "text": "vacuum the journal", "source": "disk-pressure.md"}]
    bm25 = Mock()
    bm25.get_scores.return_value = [0.0]
    mock_client = Mock()
    mock_client.query_points.return_value = Mock(points=[Mock(id="1")])
    mock_model = Mock()
    mock_model.encode.return_value = Mock(tolist=lambda: [0.0])
    mock_reranker = Mock()
    mock_reranker.predict.return_value = [-10.0]
    with (
        patch.object(R, "_load_corpus", return_value=(corpus, bm25)),
        patch.object(R, "_get_model", return_value=mock_model),
        patch.object(R, "_get_client", return_value=mock_client),
        patch.object(R, "_get_reranker", return_value=mock_reranker),
    ):
        assert retrieve("What is the vacation policy?") == []


def test_retrieve_above_threshold_returns_chunks():
    from unittest.mock import Mock, patch
    import app.retrieve as R
    from app.retrieve import retrieve
    corpus = [{"id": "1", "text": "vacuum the journal", "source": "disk-pressure.md"}]
    bm25 = Mock()
    bm25.get_scores.return_value = [0.0]
    mock_client = Mock()
    mock_client.query_points.return_value = Mock(points=[Mock(id="1")])
    mock_model = Mock()
    mock_model.encode.return_value = Mock(tolist=lambda: [0.0])
    mock_reranker = Mock()
    mock_reranker.predict.return_value = [5.0]
    with (
        patch.object(R, "_load_corpus", return_value=(corpus, bm25)),
        patch.object(R, "_get_model", return_value=mock_model),
        patch.object(R, "_get_client", return_value=mock_client),
        patch.object(R, "_get_reranker", return_value=mock_reranker),
    ):
        result = retrieve("How do I free disk?")
    assert len(result) == 1 and result[0]["source"] == "disk-pressure.md"
