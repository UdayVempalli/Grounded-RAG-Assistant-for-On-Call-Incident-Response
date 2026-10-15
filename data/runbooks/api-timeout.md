# API Timeouts

## Symptoms
- Clients report `504 Gateway Timeout` or `context deadline exceeded` errors.
- API latency is normal for most requests, but a subset times out after 30s.
- Upstream dependency dashboards show elevated latency or connection errors.

## Diagnosis
1. Check the timeout budget: `curl -w "%{time_total}" https://api.example.com/health` — if the upstream takes longer than the client timeout, the client gives up first.
2. Check the downstream: if the API calls a database or another service, time that call separately.
3. Check connection pooling: `netstat -an | grep ESTABLISHED | wc -l` — an exhausted pool makes new requests wait, then time out.
4. Check for retries: a retry storm (every timeout retried immediately) amplifies load and causes more timeouts.

## Mitigation
- Raise the client timeout only if the upstream is healthy but slow; otherwise you hide the problem.
- Add a circuit breaker: stop calling a failing downstream after N consecutive timeouts, return a fast error instead.
- Set a deadline per request: never let a request wait forever (e.g., a 5s timeout on the client call).
- Back off retries: exponential backoff with jitter (`1s, 2s, 4s, ...`), never retry immediately.

## Escalation
- Page the owning team if timeouts exceed 1% of requests for more than 5 minutes.
