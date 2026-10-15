# CPU Throttling

## Symptoms
- Pod latency elevated, but CPU usage looks well below the limit.
- `kubectl top pod` shows the pod using far less CPU than its limit.
- The application is slow under load, but no OOMKilled or restarts.

## Diagnosis
1. Check the throttle count: `cat /sys/fs/cgroup/cpu.stat` inside the pod — look for `nr_throttled` (times the pod was throttled) and `throttled_time`.
2. Check the limit: `kubectl describe pod <name>` — compare `limits.cpu` against the pod's actual need.
3. Check the quota: if the node is overcommitted, the kernel throttles every pod on it.
4. Check the pattern: throttling shows as flat-topped CPU graphs (the pod hits the limit, then is paused).

## Mitigation
- Raise the CPU limit: `limits.cpu` should be above the pod's p95 usage, not at it.
- Remove the limit only if the pod is latency-critical and the node has headroom (no limit = no throttle, but a runaway pod can starve others).
- Right-size requests: `requests.cpu` controls scheduling; `limits.cpu` controls throttling. Do not confuse them.
- Split the work: if one container throttles, split it into two pods (horizontal scale) instead of raising the limit.

## Escalation
- Page the platform on-call if throttling affects a latency-critical service for more than 5 minutes.
