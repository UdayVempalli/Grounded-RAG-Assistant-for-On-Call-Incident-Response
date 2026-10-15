# Slow Pod Startup

## Symptoms
- Pod takes minutes to become Ready (not Pending, not CrashLoopBackOff — just slow).
- `kubectl get pods` shows the pod in `Running` but not Ready.
- Readiness probe fails repeatedly, then passes.

## Diagnosis
1. Check the startup time: `kubectl describe pod <name>` — compare `Started` against `Ready` timestamps.
2. Check the init container: `kubectl logs <pod> -c <init-container>` — a slow init container delays the main container.
3. Check the readiness probe: `kubectl describe pod <name>` — a probe with a short `initialDelaySeconds` fails while the app is still warming up.
4. Check the image pull: a large image takes minutes to pull (see ImagePullBackOff if it never finishes).

## Mitigation
- Add a startup probe: `startupProbe` gives the app time to warm up before the readiness probe starts.
- Increase `initialDelaySeconds` on the readiness probe to match the app's warm-up time.
- Speed up init: cache dependencies, shrink the image, or move setup out of the init container.
- Pre-pull the image: use a DaemonSet to pre-pull large images onto nodes before the deploy.

## Escalation
- Page the platform on-call if slow startup delays a production deploy by more than 10 minutes.
