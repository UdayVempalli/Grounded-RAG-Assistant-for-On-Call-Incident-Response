"""Turn thumbs-down feedback into golden-set candidates.

Every 👎 is a question the system answered badly in production. This script
drafts golden items from them; a human fills in expected_source and
expected_keywords (or marks the item unanswerable) and moves the reviewed
items into evals/golden.json. Questions already in the golden set, or
repeated in the feedback, are skipped.

Run:  python scripts/feedback_to_golden.py [feedback.jsonl] [out.json]
      defaults: data/feedback/feedback.jsonl -> evals/candidates.json
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def draft_candidates(feedback_lines: list[str], golden: list[dict]) -> list[dict]:
    known = {item["question"].strip().lower() for item in golden}
    candidates = []
    for line in feedback_lines:
        if not line.strip():
            continue
        entry = json.loads(line)
        q = entry["question"].strip()
        if entry.get("helpful") or q.lower() in known:
            continue
        known.add(q.lower())
        candidates.append({
            "question": q,
            "expected_source": "TODO: runbook filename, or null if unanswerable",
            "expected_keywords": ["TODO"],
            "_bad_answer": entry.get("answer", ""),
            "_request_id": entry.get("request_id"),
        })
    return candidates


def main() -> None:
    src = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "data" / "feedback" / "feedback.jsonl"
    out = Path(sys.argv[2]) if len(sys.argv) > 2 else ROOT / "evals" / "candidates.json"
    if not src.exists():
        raise SystemExit(f"no feedback file at {src}")
    golden = json.loads((ROOT / "evals" / "golden.json").read_text(encoding="utf-8"))
    candidates = draft_candidates(src.read_text(encoding="utf-8").splitlines(), golden)
    out.write_text(json.dumps(candidates, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"{len(candidates)} new candidate(s) -> {out} (review, fill the TODOs, then move into golden.json)")


if __name__ == "__main__":
    main()
