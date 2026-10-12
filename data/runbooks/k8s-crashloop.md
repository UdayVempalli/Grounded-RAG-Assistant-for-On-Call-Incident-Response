# Runbook: Pod CrashLoopBackOff

## Symptoms
Pod restarts repeatedly; `kubectl get pods` shows `CrashLoopBackOff`.

## Diagnosis
1. `kubectl describe pod <pod>` — check the Last State exit code and reason (OOMKilled, Error).
2. `kubectl logs <pod> --previous` — read logs from the crashed container, not the fresh one.
3. If OOMKilled (exit 137): the container exceeded its memory limit. Check `kubectl top pod` and compare against the limit in the deployment spec.
4. Check recent config or image changes: `kubectl rollout history deploy/<name>`.

## Mitigation
- OOMKilled: raise the memory limit temporarily, then profile the app for the leak.
- Bad image/config: `kubectl rollout undo deploy/<name>` to the last known-good revision.
- Never just raise restart counts without finding the exit reason.

## Escalation
Page the service owner if the pod serves a critical path and mitigation doesn't stabilize within 15 minutes.
