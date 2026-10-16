# SLOs — RunbookQA

Targets from measured data (Oct 15, 2026). These are objectives for the demo
deployment, not a production SLA.

## /ask latency
- SLO: p95 < 60s.
- Basis: one measured /ask took 41.5s (7.8s retrieval + 33.6s generation, ~2.7 tok/s on CPU).
- Note: this SLO is CPU-bound. On a GPU or hosted inference API, the target would be p95 < 10s.

## Retrieval hit rate
- SLO: >= 95% on the golden set (expected_source in top-4).
- Basis: measured 130/130 = 100% (20 runbooks, 104 chunks).
- Note: the held-out set (12 untuned questions) measured 8/12 = 66.7% (20-runbook corpus, small-to-big + two-layer refusal). Breakdown: 3 near-miss refusals pass via the LLM layer; 3 answerable over-refuse on vague questions (3B-model long-context limit); 1 judge false-FAIL on a correct answer; 1 out-of-corpus helm question. The golden set is the gate; the holdout is the honest check.

## Refusal accuracy
- SLO: 100% on unanswerable questions (no answer when the corpus has no runbook).
- Basis: 5/5 golden unanswerable return empty retrieval (no LLM call); 3/6 holdout refuse questions return empty retrieval, 3/6 pass via the LLM refusing from the context.
- Note: refusal is two-layer: the reranker threshold (-6.0) catches clearly off-topic questions; for near-misses that return chunks, the model itself must refuse from the context.

## Availability
- SLO: 99% of /health checks succeed (demo deployment).
- Basis: the container HEALTHCHECK polls /health every 30s.

## Alerts
- See prometheus/alerts.yml (Prometheus rules). Alertmanager is not wired (no notification channel); alerts appear in the Prometheus UI.
