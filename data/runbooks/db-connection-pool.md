# Connection Pool Exhaustion

## Symptoms
- Application logs show `too many clients already`, `timeout waiting for connection`, or `FATAL: remaining connection slots are reserved`.
- New requests fail, but existing connections keep working.
- `SELECT count(*) FROM pg_stat_activity;` shows the count at or near `max_connections`.

## Diagnosis
1. Check the connection count: `SELECT count(*) FROM pg_stat_activity;` — compare against `SHOW max_connections;`.
2. Check for idle connections: `SELECT state, count(*) FROM pg_stat_activity GROUP BY state;` — many `idle` connections mean a leak.
3. Check for long transactions: `SELECT pid, now() - xact_start AS duration FROM pg_stat_activity WHERE state = 'idle in transaction';` — an idle-in-transaction session holds a connection open.
4. Check the pooler: if PgBouncer is in front, check `SHOW POOLS;` — the pooler's `max_client_conn` may be the bottleneck, not the database.

## Mitigation
- Kill the leak: `SELECT pg_terminate_backend(<pid>);` for idle-in-transaction sessions older than 5 minutes.
- Lower the pool size per instance: if 10 app instances each hold 50 connections, the database sees 500.
- Add PgBouncer in transaction mode: it multiplexes many app connections onto fewer database connections.
- Never raise `max_connections` without checking memory (each connection uses work_mem + overhead).

## Escalation
- Page the DBA on-call if pool exhaustion blocks writes for more than 5 minutes.
