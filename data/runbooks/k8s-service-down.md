# Service Has No Endpoints

## Symptoms
- Requests to the Service fail with `connection refused` or `no endpoints available`.
- `kubectl get svc <name>` shows the Service exists, but `kubectl get endpoints <name>` is empty.
- The Service works after a redeploy, then breaks again.

## Diagnosis
1. Check endpoints: `kubectl get endpoints <name>` — empty means no pod matches the Service selector.
2. Check the selector: `kubectl get svc <name> -o yaml` — compare `selector` against the pod labels.
3. Check pod labels: `kubectl get pods --show-labels` — a renamed label breaks the match.
4. Check the port: `kubectl describe svc <name>` — the Service port must match the pod's `containerPort`.

## Mitigation
- Fix the selector: align the Service selector with the pod labels, then re-apply.
- Fix the labels: restore the label the Service expects (do not change the Service to match a typo).
- Fix the port: align the Service `targetPort` with the pod's `containerPort`.
- Check the namespace: a Service in the wrong namespace cannot see pods in another namespace.

## Escalation
- Page the platform on-call if the Service is down for more than 5 minutes.
