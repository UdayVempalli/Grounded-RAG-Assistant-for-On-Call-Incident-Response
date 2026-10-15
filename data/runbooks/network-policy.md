# NetworkPolicy Blocking Traffic

## Symptoms
- Pods cannot reach a Service they could reach before a NetworkPolicy change.
- `curl` times out (not refused — the connection hangs).
- Only pods in one namespace are affected.

## Diagnosis
1. List the policies: `kubectl get networkpolicy` — a new or changed policy is the prime suspect.
2. Describe the policy: `kubectl describe networkpolicy <name>` — check `podSelector`, `ingress`, and `egress` rules.
3. Check the labels: `kubectl get pods --show-labels` — a pod must match the policy's `podSelector` to be affected.
4. Check the namespace: `kubectl get namespace <name> --show-labels` — a policy using `namespaceSelector` only applies to matching namespaces.

## Mitigation
- Allow the traffic: add an `ingress` rule for the source pod/namespace, or an `egress` rule for the destination.
- Remove the policy as a test: if traffic flows, the policy is the cause (re-add it with the fix).
- Check the default deny: a policy with no `ingress` rules denies all ingress to matching pods.
- Never debug by deleting all policies in production; test in a staging namespace first.

## Escalation
- Page the platform on-call if a NetworkPolicy blocks production traffic for more than 5 minutes.
