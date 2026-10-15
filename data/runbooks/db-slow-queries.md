# Slow Database Queries

## Symptoms
- API latency elevated; traces show most time in database calls.
- `pg_stat_statements` shows a few queries with high mean execution time.
- Application logs show query timeouts or connection pool exhaustion.

## Diagnosis
1. Find the slowest queries: `SELECT query, mean_exec_time FROM pg_stat_statements ORDER BY mean_exec_time DESC LIMIT 10;`
2. Check for missing indexes: `EXPLAIN ANALYZE <query>;` — look for sequential scans on large tables.
3. Check for locks: `SELECT * FROM pg_locks WHERE NOT granted;` shows queries waiting on locks.
4. Check connection count: `SELECT count(*) FROM pg_stat_activity;` — a saturated pool looks like slow queries.

## Mitigation
- Missing index: `CREATE INDEX CONCURRENTLY idx_orders_created ON orders (created_at);` — never `CREATE INDEX` without `CONCURRENTLY` on a live table (it locks writes).
- Lock contention: kill the blocking session: `SELECT pg_terminate_backend(<pid>);` then retry the query.
- Pool exhaustion: raise the pool size temporarily, then find the leak (unclosed connections).
- Hot query: add a covering index or cache the result; do not add a read replica for a single hot query.

## Escalation
- Page the DBA on-call if a query holds a lock for more than 5 minutes or if read-replica delay exceeds 60 seconds.
