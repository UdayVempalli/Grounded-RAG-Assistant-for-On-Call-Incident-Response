# Runbook: Node DiskPressure

## Symptoms
Node shows `DiskPressure` condition; kubelet starts evicting pods.

## Diagnosis
1. `df -h` on the node — confirm which filesystem is full (usually /var/lib/docker or /var/log).
2. Check journal size: `journalctl --disk-usage`. Runaway logging is the most common cause.
3. Check for unrotated container logs and dangling images: `docker system df`.

## Mitigation
1. Vacuum the journal: `journalctl --vacuum-size=500M`.
2. Prune unused images: `crictl rmi --prune` (never prune on a node running critical singletons without draining first).
3. If pressure persists, cordon the node and evict pods gracefully: `kubectl drain <node> --ignore-daemonsets`.

## Escalation
Page infra if more than one node hits DiskPressure within an hour — that signals a systemic logging or image problem.
