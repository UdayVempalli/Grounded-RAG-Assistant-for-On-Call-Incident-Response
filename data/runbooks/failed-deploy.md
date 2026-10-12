# Runbook: Failed Deployment / Error Spike After Rollout

## Symptoms
Error rate or latency spikes within minutes of a deployment completing.

## Diagnosis
1. Confirm correlation: `kubectl rollout history deploy/<name>` — match the spike timestamp to the rollout.
2. Check the new revision's logs for panics, config errors, or failed migrations.
3. Diff the config: `kubectl rollout history deploy/<name> --revision=<N>`.

## Mitigation
1. Roll back immediately: `kubectl rollout undo deploy/<name> --to-revision=<last-good>`.
2. Verify error rates recover before investigating the bad revision.
3. Freeze further deploys of that service until the root cause is found.

## Escalation
Write a postmortem if customer-facing impact exceeded 5 minutes. Attach the bad revision diff.
