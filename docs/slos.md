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
- Note: the held-out set (12 untuned questions) measured 11/12 = 91.7%. The golden set is the gate; the holdout is the honest check.

## Refusal accuracy
- SLO: 100% on unanswerable questions (no answer when the corpus has no runbook).
- Basis: 5/5 golden unanswerable + 6/6 holdout refuse questions return empty retrieval, no LLM call.
- Note: the refusal is enforced by the reranker threshold (-6.0), not by the model.

## Availability
- SLO: 99% of /health checks succeed (demo deployment).
- Basis: the container HEALTHCHECK polls /health every 30s.

## Alerts
- See prometheus/alerts.yml (Prometheus rules). Alertmanager is not wired (no notification channel); alerts appear in the Prometheus UI.
