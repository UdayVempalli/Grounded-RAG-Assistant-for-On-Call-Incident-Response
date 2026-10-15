# Ingress 502 Bad Gateway

## Symptoms
- Clients get `502 Bad Gateway` from the ingress.
- Direct `curl` to the Service (bypassing ingress) works.
- The 502 appears after a deploy or a Service change.

## Diagnosis
1. Check the ingress backend: `kubectl describe ingress <name>` — the backend Service and port must exist.
2. Check the Service: `kubectl get svc <name>` — a Service with no endpoints gives 502.
3. Check the pod: `kubectl get pods` — if the pod is not Ready, the ingress has no healthy backend.
4. Check the ingress controller logs: `kubectl logs -n ingress-nginx -l app.kubernetes.io/name=ingress-nginx` — look for `upstream` errors.

## Mitigation
- Fix the backend: point the ingress at the correct Service and port.
- Wait for readiness: if the pod is still starting, the 502 clears once it becomes Ready.
- Fix the Service: restore the endpoints (see Service Has No Endpoints).
- Check the ingress class: a wrong `ingressClassName` means no controller serves this ingress.

## Escalation
- Page the platform on-call if 502s exceed 1% of requests for more than 5 minutes.
