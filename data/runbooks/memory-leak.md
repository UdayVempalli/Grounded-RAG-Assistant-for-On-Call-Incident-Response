# Memory Leak

## Symptoms
- Pod memory usage grows steadily over hours or days (never drops).
- `kubectl top pod` shows memory climbing toward the limit.
- The pod is eventually OOMKilled, then the cycle repeats.

## Diagnosis
1. Confirm the growth: `kubectl top pod <name>` sampled over time — a leak grows monotonically; normal usage fluctuates.
2. Check the heap: `kubectl exec <pod> -- curl localhost:8080/debug/pprof/heap` (Go) or a heap dump (JVM/Node) — look for unbounded growth in one type.
3. Check for unbounded caches: a cache with no size limit or TTL grows forever.
4. Check for unclosed resources: unclosed connections, file handles, or goroutines accumulate.

## Mitigation
- Restart the pod as a stopgap (the leak returns; this buys time, not a fix).
- Cap the cache: set a max size + TTL, or an LRU eviction policy.
- Fix the leak: close resources, bound the cache, or fix the goroutine leak — then redeploy.
- Lower the memory limit temporarily so the pod is OOMKilled sooner (fail fast) instead of slowly starving the node.

## Escalation
- Page the owning team if the leak causes repeated OOMKills in production.
