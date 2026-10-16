# SLOs — RunbookQA

Targets from measured data (Oct 15-16, 2026). These are objectives for the demo
deployment, not a production SLA.

## /ask latency
- SLO: p95 < 60s.
- Basis: one measured /ask took 41.5s (7.8s retrieval + 33.6s generation, ~2.7 tok/s on CPU).
- Note: this SLO is CPU-bound. On a GPU or hosted inference API, the target would be p95 < 10s.

## Retrieval hit rate
- SLO: >= 97% on the golden set (expected_source in top-4); the eval gate enforces it.
- Basis: hybrid retrieval found the right runbook 125/125 times on the answerable golden questions (dense alone: 121/125), on 20 runbooks / 84 title-prefixed section chunks.
- Held-out set (12 untuned questions, never gates): 10/12 on the final code (Oct 16; 8/12 before this round). Retrieval 5/6: "undo a helm release" is now refused by the threshold, a defensible refusal since the runbooks cover kubectl rollout undo, not Helm.

## Refusal accuracy
- SLO: 100% on unanswerable and prompt-injection questions; the eval gate enforces it.
- Basis (Oct 16, final code): golden 7/7 unanswerable refused, 5/5 injection items safe (all refused by the injection guard); held-out 6/6 refused.
- Refusal has three layers: (1) a pattern guard refuses prompt-injection requests (prompt leaks, context overrides) before retrieval; (2) the reranker threshold (-6.0) refuses clearly off-topic questions with no LLM call; (3) for near-misses that return chunks, the model refuses from the context.

## Answer groundedness
- Measured, not yet an SLO: the LLM judge passes 105/120 judged golden answers (87.5%). Of the 15 judge failures, 10 are judge noise on correct answers and the rest are real model errors; all are listed in evals/known_failures.json with a reason. The gate fails on any failure not in that list.

## Availability
- SLO: 99% of /health checks succeed (demo deployment).
- Basis: the container HEALTHCHECK polls /health every 30s.

## Alerts
- See prometheus/alerts.yml: p95 latency, error rate, refusal ratio, circuit breaker open, rejection spike, target down. Rules load via rule_files in prometheus.yml (validated with promtool). Alertmanager is not wired (no notification channel); alerts appear in the Prometheus UI.
