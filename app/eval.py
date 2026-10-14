"""Eval harness: the quality contract. Run in CI — regressions break the build.

For each golden item:
  1. retrieval check — is the expected runbook among retrieved sources?
  2. groundedness check — two layers:
     a. keyword gate (fast, deterministic): does the answer mention at
        least one expected runbook term?
     b. LLM-as-judge (semantic): does a separate judge call confirm every
        claim in the answer is supported by the retrieved context?
  3. refusal check — for unanswerable questions, does it refuse instead of hallucinating?

Exit 1 if any check fails. Thresholds live here, in code, like tests.

The judge uses the same local model with a separate judging prompt. It is a
second layer, not a replacement for the keyword gate: keywords catch
regressions cheaply, the judge catches fluent-but-ungrounded answers that
keywords miss. A FAIL from the judge is verified, not trusted: it must cite the added claim in quotes, and code checks the claim is genuinely absent from the context. A stronger judge model (or an external judge) is the natural
next upgrade; the interface stays the same.

Run:  python -m app.eval
"""
import json
import re
import sys
from pathlib import Path

import httpx

from .retrieve import retrieve

GOLDEN = Path(__file__).resolve().parent.parent / "evals" / "golden.json"
OLLAMA_URL = "http://localhost:11434"
LLM_MODEL = "llama3.2:3b"

JUDGE_PROMPT = """You are a strict evaluator. Decide whether the ANSWER is fully grounded in the CONTEXT.

Rules:
- Every step or claim in the ANSWER must be traceable to the CONTEXT.
- Paraphrasing the CONTEXT in different words is a PASS, not a FAIL.
- FAIL only when the ANSWER adds a step, command, or fact that is not in the CONTEXT, or contradicts the CONTEXT.
- In REASON, put the exact added or contradictory claim from the ANSWER in double quotes. If there is no added claim, write REASON: none.

CONTEXT:
{context}

QUESTION: {question}

ANSWER:
{answer}

Reply in exactly this format:
VERDICT: PASS or FAIL
REASON: one short sentence.
"""


def generate(question: str, chunks: list[dict]) -> str:
    context = "\n\n---\n\n".join(f"[{c['source']}]\n{c['text']}" for c in chunks)
    prompt = (
        "Answer using ONLY the context below. If the answer isn't in the context, "
        f'say "I don\'t have a runbook for that." Do not invent steps.\n\n'
        f"Context:\n{context}\n\nQuestion: {question}\n\nAnswer:"
    )
    r = httpx.post(f"{OLLAMA_URL}/api/generate",
                   json={"model": LLM_MODEL, "prompt": prompt, "stream": False,
                         "options": {"temperature": 0}},
                   timeout=120)
    r.raise_for_status()
    return r.json()["response"]


def judge(question: str, chunks: list[dict], answer: str) -> tuple[bool, str]:
    """Ask the judge model whether `answer` is grounded in `chunks`.

    Returns (passed, reason). The verdict is not trusted alone: a FAIL must
    cite the added claim in double quotes, and code checks whether that claim
    actually appears in the context. If it does, the judge contradicted its
    own evidence and the verdict is overruled to PASS (logged, not silent).
    Fails closed: an unparseable verdict is a failure.
    """
    context = "\n\n---\n\n".join(f"[{c['source']}]\n{c['text']}" for c in chunks)
    prompt = JUDGE_PROMPT.format(context=context, question=question, answer=answer)
    r = httpx.post(f"{OLLAMA_URL}/api/generate",
                   json={"model": LLM_MODEL, "prompt": prompt, "stream": False,
                         "options": {"temperature": 0}},
                   timeout=120)
    r.raise_for_status()
    raw = r.json()["response"]
    m = re.search(r"VERDICT:\s*(PASS|FAIL)", raw, re.IGNORECASE)
    reason = raw.strip().replace("\n", " ")[:300]
    if not m:
        return False, f"unparseable judge output: {reason}"
    if m.group(1).upper() == "PASS":
        return True, reason
    # FAIL: verify the cited evidence before trusting it. A FAIL must name
    # the added claim in double quotes; if that claim actually appears in
    # the context, the judge contradicted its own evidence.
    q = re.search(r'"([^"]+)"', raw)
    if q and len(q.group(1)) >= 8 and q.group(1).lower() in context.lower():
        return True, f"judge overruled: cited addition found in context: {q.group(1)}"
    return False, reason


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

        answer_raw = generate(q, chunks)
        answer = answer_raw.lower()

        # 2. unanswerable questions must refuse, not hallucinate
        if item.get("unanswerable"):
            if "don't have a runbook" not in answer and "do not have" not in answer:
                failures.append(f"[{i}] hallucinated instead of refusing: {q}")
            else:
                print(f"[{i}] PASS (refused) {q}")
            continue

        # 3a. groundedness, keyword gate: answer must reference at least one
        #     expected runbook term (any-match: a correct answer cites *some*
        #     step, not every step)
        keywords = item.get("expected_keywords", [])
        if keywords and not any(kw.lower() in answer for kw in keywords):
            failures.append(f"[{i}] no expected terms {keywords} in answer: {q}")
            continue
        print(f"[{i}] PASS {q}")

        # 3b. groundedness, LLM-as-judge: every claim must trace to the context
        passed, reason = judge(q, chunks, answer_raw)
        if not passed:
            failures.append(f"[{i}] judge FAIL: {reason} | Q: {q}")
        else:
            print(f"[{i}] PASS (judge) {q}")
            if "overruled" in reason:
                print(f"    note: {reason}")

    print(f"\n{len(items) - len(failures)}/{len(items)} evals passed")
    if failures:
        print("\nFAILURES:")
        for f in failures:
            print(" -", f)
        sys.exit(1)


if __name__ == "__main__":
    main()
