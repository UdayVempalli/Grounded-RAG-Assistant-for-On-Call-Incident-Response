# Interview Lessons — RunbookQA

What broke, what fixed it, and what I would say in an interview. Each lesson is a
challenge, what happened, the fix, and the takeaway.

## 1. Generator inversion
- Challenge: the generator model echoed the question back instead of answering.
- Fix: temperature 0, and a prompt that forces an answer from the context.
- Lesson: a small model with a loose prompt will parrot; constrain it.

## 2. Judge paraphrase false positive
- Challenge: the judge failed answers that were semantically right but worded differently.
- Fix: paraphrase-tolerant judge prompt + an evidence-checked override (see #3).
- Lesson: an LLM judge needs a second, deterministic check.

## 3. Judge self-contradiction
- Challenge: the judge said PASS and FAIL on the same answer across runs.
- Fix: evidence-checked judge + override: a cited claim must appear in BOTH context and answer.
- Lesson: never trust a single LLM verdict; verify against source text.

## 4. Brittle keywords
- Challenge: the keyword gate required ALL keywords; good answers failed (3/6).
- Fix: any-match (one keyword suffices); the judge is the real check.
- Lesson: the keyword gate is a smoke test, not the verdict.

## 5. Retrieval always returns something
- Challenge: the retriever returned chunks even for out-of-corpus questions.
- Fix: minimum reranker score threshold (-6.0, measured from the golden set).
- Lesson: retrieval needs a relevance floor, or every question gets an answer.

## 6. Retrieval noise
- Challenge: answers cited irrelevant runbooks (DiskPressure answer cited k8s-crashloop).
- Fix: hybrid retrieval (dense + BM25 + RRF) + cross-encoder rerank.
- Lesson: ranking matters as much as retrieval; rerank before answering.

## 7. Mid-word chunk splits
- Challenge: fixed-window chunking cut words in half.
- Fix: boundary-aware chunking (headings, word boundaries, heading prepend).
- Lesson: chunk boundaries are part of retrieval quality.

## 8. 41s CPU inference
- Challenge: one /ask took 41.5s (7.8s retrieval + 33.6s generation, ~2.7 tok/s on CPU).
- Fix (design): GPU inference or hosted API for real speed; on CPU: smaller model, shorter outputs, no live judge, caching, extractive fallback.
- Lesson: measure the split (retrieval vs generation) before optimizing.

## 9. Empty-reply race
- Challenge: the API returned an empty reply right after startup (model not ready).
- Fix: logs + retry; readiness probe waits for the model.
- Lesson: a service is not ready when the port is open; it is ready when it can answer.

## 10. Stale Grafana
- Challenge: the dashboard showed old data after a restart.
- Fix: restart Grafana; the series re-syncs.
- Lesson: dashboards cache; verify against the raw metric.

## 11. Metric series split
- Challenge: a label change split one metric into two series.
- Fix: use sum() over the metric, not a single series.
- Lesson: labels are part of the metric's identity; aggregate.

## 12. Stale pie slice
- Challenge: the outcome pie showed a third slice from a pre-restart series.
- Fix: it ages out (the old series stops receiving samples).
- Lesson: Prometheus series die when they stop getting samples; wait.

## 13. /health lied
- Challenge: /health returned ok while the model was still loading.
- Fix: separate /ready (model loaded + Qdrant reachable) from /health (process alive).
- Lesson: liveness != readiness.

## 14. Eval tested pieces, not the API
- Challenge: the eval tested retrieval + generation functions, not the /ask endpoint.
- Fix: API tests (TestClient) covering the real /ask path, auth, and rate limiting.
- Lesson: test the contract the client sees.

## 15. Prompt drift
- Challenge: the eval used a different prompt than production.
- Fix: the eval calls the production generate() (single source of truth).
- Lesson: one prompt, used by both prod and eval.

## 16. Docker 626s -> 7s
- Challenge: cold Docker build took 626s.
- Fix: layer caching (pinned base, lockfile, bake models); cached builds take ~7s.
- Lesson: put slow, stable layers (deps, models) early in the Dockerfile.

## 17. HF Hub unauthenticated
- Challenge: model downloads hit unauthenticated Hub rate limits.
- Fix: HF_TOKEN from env; bake models into the image; HF_HUB_OFFLINE=1 at runtime.
- Lesson: never download models at request time.

## 18. CI never ran pytest
- Challenge: CI only ran the eval; unit tests never ran.
- Fix: pytest step in the workflow; eval runs after it.
- Lesson: the fast gate (pytest) must run before the slow gate (eval).

## 19. Unpinned deps
- Challenge: unpinned deps broke a build when a transitive dep moved.
- Fix: lockfile (requirements-lock.txt) + digest-pinned images.
- Lesson: pin everything; a build that works today must work tomorrow.

## 20. Python 3.11 vs 3.14 drift
- Challenge: local venv ran Python 3.14, Docker/CI pinned 3.11.
- Fix: Docker/CI pin 3.11; local venv is dev-only (documented drift).
- Lesson: pin the runtime in every environment that matters.

## 21. Dockerfile had no CMD
- Challenge: the container started but did nothing (no CMD).
- Fix: Dockerfile CMD is the single source; compose does not override it.
- Lesson: one entrypoint, defined once.

## 22. Patch-script failures
- Challenge: patches half-applied (asserts passed but the write was partial; paste garbling).
- Fix: assert every replacement, write only after all asserts pass; verify with grep after every patch.
- Lesson: a patch that fails must leave the file unchanged.

## 23. Chunking regression (51/55)
- Challenge: boundary-aware chunking changed retrieval; the eval dropped 55 -> 51.
- Fix: diagnosed via retrieve() (retrieval was fine); fixed 3 question wordings + the judge override.
- Lesson: a retrieval change needs a full eval re-run; the gate catches what unit tests miss.

## 24. Judge false positives, three times
- Challenge: the judge failed [31] ("use kubectl drain"), [18] ("A cache stampede"), [34] ("Check for panics") — all filler words the override did not strip.
- Fix: word-based filler stripping (articles, prepositions, imperative verbs).
- Lesson: the judge quotes claims with filler; strip the filler, compare the core.

## 25. Threshold tuned on the test set
- Challenge: the reranker threshold (-6.0) was tuned on the golden set, so the golden set could not measure it fairly.
- Fix: held-out set (evals/holdout.json, 12 untuned questions, 8/12 on the 20-runbook corpus with small-to-big + two-layer refusal) + report-only runner.
- Lesson: never evaluate on the set you tuned on.

## 26. CI speedup is not thread speedup
- Challenge: CI took ~18 min; parallelizing the eval with threads did not help.
- Fix (understanding): Ollama serializes LLM calls on CPU and the embedding model shares the same cores — threads do not create CPU. The real lever is splitting pytest into its own parallel job (fast signal).
- Lesson: profile before parallelizing; a CPU-bound pipeline does not speed up with threads.

## 27. Batch runbooks, same loop
- Challenge: growing from 5 to 20 runbooks one-by-one took too many turns.
- Fix: batch 3 (then all) at a time — same 4-step loop (write, ingest, questions, retrieval check), one ingest + one check + one commit per batch.
- Lesson: batch the work, not the verification — the checks stay per-batch, never skipped.

## 28. Model hallucinated across runbooks ([2])
- Challenge: the model answered a DiskPressure question with db-failover content ("replica lag") and cited disk-pressure.md.
- Fix: the keyword gate caught it (no df/journalctl/disk-usage). Diagnosis showed the top-4 was clean on the larger corpus — the failure was the old 6-runbook context (or flakiness). The larger corpus (20 runbooks) outranked the contaminating chunk.
- Lesson: a bigger, better-separated corpus improves generation, not just retrieval. And the gate catches what the model invents.

## Deferred items (done Oct 15)
- Feedback endpoint: thumbs down posts to Slack (no-op if unset, never fail the request); feedback feeds the golden set.
- SLOs from measured data: p95 < 60s (measured 41.5s), hit rate >= 95% (measured 100%), refusal 100%. Targets from data, not aspiration.
- Auto-ingest: mount runbooks read-only + POST /ingest (no watcher, no rebuild). Works locally; CI's Qdrant is ephemeral.
- K8s: 1 replica (rate limiter is in-process); Ollama external via env (needs a GPU node for real speed).
- Streaming: SSE with the same retrieval + refusal as /ask; first token fast.
- Tracing without deps: request_id in the response + span logs (retrieve/generate ms). No OTel SDK needed for correlation.
- Slack: webhook from env, no-op if unset. A notification must never break the request it reports on.
- Stronger judge: rubric (claims, citations, relevance, no invention). The citations check catches cross-runbook mixing (the [2] failure).
