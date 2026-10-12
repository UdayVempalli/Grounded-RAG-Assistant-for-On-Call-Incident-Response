# Runbook: High API Latency

## Symptoms
p99 latency above the 500ms SLO; alerts firing on the latency burn-rate.

## Diagnosis
1. Check the Grafana latency dashboard: is the spike in p50 or only p99? p99-only usually means a downstream dependency, not the API itself.
2. Correlate with downstream dashboards (database, cache, third-party APIs).
3. Pull a distributed trace for a slow request; find which span dominates.
4. Check for deploy correlation: did latency start at a release boundary?

## Mitigation
- Downstream DB slow: check for missing indexes, connection pool exhaustion, replica lag.
- Cache stampede: verify cache hit ratio; warm the cache before re-enabling traffic.
- Bad deploy: roll back first, investigate second.

## Escalation
If p99 stays above SLO for 10 minutes after mitigation, page the on-call lead.
