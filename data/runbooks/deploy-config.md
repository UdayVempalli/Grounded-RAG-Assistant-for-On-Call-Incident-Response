# Bad Config Change

## Symptoms
- The service fails to start or crashes immediately after a config change (no code deploy).
- Logs show `missing required config`, `invalid value`, or `failed to parse config`.
- The service works on one environment but not another (config drift).

## Diagnosis
1. Diff the config: `kubectl get configmap <name> -o yaml` — compare against the last known good version.
2. Check the rollout history: `kubectl rollout history deploy/<name>` — a config change triggers a new revision.
3. Check for a missing key: `kubectl describe configmap <name>` — a renamed or deleted key breaks the service.
4. Check secrets: `kubectl get secret <name>` — a rotated or expired secret looks like a config error.

## Mitigation
- Roll back the config to the last known good revision (same mechanism as a bad code deploy).
- Fix the key: restore the deleted key or correct the value, then re-apply the ConfigMap.
- Validate before applying: run a config schema check in CI (reject unknown keys, wrong types, missing required keys).
- Never edit a ConfigMap by hand in production; always apply from version control.

## Escalation
- Page the owning team if the config change broke a production service for more than 5 minutes.
