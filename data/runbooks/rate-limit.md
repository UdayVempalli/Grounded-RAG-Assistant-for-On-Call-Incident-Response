# Rate Limit 429

## Symptoms
- Clients get `429 Too Many Requests` with a `Retry-After` header.
- The 429s start after a traffic spike or a new client.
- Only one client or one endpoint is affected (not a global outage).

## Diagnosis
1. Read the headers: `curl -i https://api.example.com/endpoint` — the `Retry-After` header says how long to wait.
2. Check the rate limiter: look for the limiter config (per-client, per-endpoint, or global) — a per-client limiter only affects one client.
3. Check the client: a retry loop or a new integration can exceed the limit (see retry storm in API Timeouts).
4. Check the traffic: compare request rate against the limit — a spike above the limit triggers 429s.

## Mitigation
- Back off: honor `Retry-After` (exponential backoff with jitter), never retry immediately.
- Raise the limit only if the backend can handle it (a higher limit on an overloaded backend causes timeouts).
- Add client-side throttling: queue requests and send them at the allowed rate.
- Distinguish 429 from 503: 429 means "slow down"; 503 means "the service is down". Do not retry 503 the same way.

## Escalation
- Page the owning team if 429s exceed 5% of requests for more than 5 minutes.
