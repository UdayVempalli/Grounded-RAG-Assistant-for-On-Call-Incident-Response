"""Eval harness: the quality contract. Run in CI — regressions break the build.

For each golden item:
  1. retrieval check — is the expected runbook among retrieved sources?
  2. groundedness check — does the answer mention the expected keywords
     (proxy for faithfulness until the LLM-judge TODO is wired)?
  3. refusal check — for unanswerable questions, does it refuse instead of hallucinating?

Exit 1 if any check fails. Thresholds live here, in code, like tests.

Run:  python -m app.eval
"""
import json
import sys
from pathlib import Path

import httpx

from .retrieve import retrieve

GOLDEN = Path(__file__).resolve().parent.parent / "evals" / "golden.json"
OLLAMA_URL = "http://localhost:11434"
LLM_MODEL = "llama3.2:3b"


def generate(question: str, chunks: list[dict]) -> str:
    context = "\n\n---\n\n".join(f"[{c['source']}]\n{c['text']}" for c in chunks)
    prompt = (
        "Answer using ONLY the context below. If the answer isn't in the context, "
        f'say "I don\'t have a runbook for that." Do not invent steps.\n\n'
        f"Context:\n{context}\n\nQuestion: {question}\n\nAnswer:"
    )
    r = httpx.post(f"{OLLAMA_URL}/api/generate",
                   json={"model": LLM_MODEL, "prompt": prompt, "stream": False},
                   timeout=120)
    r.raise_for_status()
    return r.json()["response"]


def main() -> None:
    items = json.loads(GOLDEN.read_text())
    failures = []

    for i, item in enumerate(items):
        q = item["question"]
        chunks = retrieve(q, top_k=4)
        sources = {c["source"] for c in chunks}

        # 1. retrieval: expected runbook must be cited
        if item.get("expected_source") and item["expected_source"] not in sources:
            failures.append(f"[{i}] retrieval miss: {item['expected_source']} not in {sources}")
            continue

        answer = generate(q, chunks).lower()

        # 2. unanswerable questions must refuse, not hallucinate
        if item.get("unanswerable"):
            if "don't have a runbook" not in answer and "do not have" not in answer:
                failures.append(f"[{i}] hallucinated instead of refusing: {q}")
            else:
                print(f"[{i}] PASS (refused) {q}")
            continue

        # 3. groundedness: answer must reference at least one expected
        #    runbook term (any-match: a correct answer cites *some* step,
        #    not every step)
        keywords = item.get("expected_keywords", [])
        if keywords and not any(kw.lower() in answer for kw in keywords):
            failures.append(f"[{i}] no expected terms {keywords} in answer: {q}")
        else:
            print(f"[{i}] PASS {q}")

    print(f"\n{len(items) - len(failures)}/{len(items)} evals passed")
    if failures:
        print("\nFAILURES:")
        for f in failures:
            print(" -", f)
        sys.exit(1)


if __name__ == "__main__":
    main()
