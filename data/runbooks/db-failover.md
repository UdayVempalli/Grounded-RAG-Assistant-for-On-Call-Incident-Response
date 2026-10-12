# Runbook: Database Failover Verification

## Symptoms
Primary database failed over to a replica (automated or manual).

## Diagnosis
1. Confirm the new primary: check the cluster status endpoint — exactly one node must report primary.
2. Check replica lag on all remaining replicas: lag must be under 5 seconds before re-enabling writes.
3. Verify the app tier: connections should be read-write on the new primary, read-only on replicas.
4. Run the smoke query suite against the new primary before declaring all-clear.

## Mitigation
- Split-brain risk (two primaries): fence the old primary immediately, then page the DBA on-call.
- High replica lag: keep traffic read-only on the lagging replica until it catches up.

## Escalation
Record failover duration and data-loss window (should be zero with synchronous replication).
