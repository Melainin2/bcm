# PostgreSQL — Performance Tuning

## Overview

Improving PostgreSQL performance usually comes down to four areas: proper
indexing, good query plans, sensible memory configuration, and regular
maintenance.

## 1. Indexing

- Create indexes on columns used in `WHERE`, `JOIN`, and `ORDER BY` clauses.
- Use B-tree indexes for equality and range queries (the default).
- Use partial indexes when queries filter on a fixed condition:
  ```sql
  CREATE INDEX idx_orders_open ON orders (customer_id) WHERE status = 'open';
  ```
- Drop unused indexes — they slow down writes without helping reads. Check
  `pg_stat_user_indexes` for indexes with `idx_scan = 0`.

## 2. Analyze query plans with EXPLAIN

```sql
EXPLAIN (ANALYZE, BUFFERS) SELECT * FROM orders WHERE customer_id = 42;
```

Look for sequential scans on large tables (often a missing index) and rows
estimates that differ greatly from actual rows (often stale statistics — run
`ANALYZE`).

## 3. Memory configuration (postgresql.conf)

- `shared_buffers` : 25% of total RAM is a good starting point.
- `work_mem` : memory per sort/hash operation. Increase for complex queries, but
  remember it is allocated per operation per connection.
- `effective_cache_size` : set to roughly 50-75% of RAM so the planner knows how
  much OS cache is available.
- `maintenance_work_mem` : raise it to speed up index creation and VACUUM.

## 4. Maintenance and statistics

- Keep autovacuum enabled so dead tuples are cleaned and statistics stay fresh.
- Run `ANALYZE` after large data loads so the planner has accurate statistics.
- Use connection pooling (e.g. PgBouncer) to avoid exhausting `max_connections`.

## 5. Find slow queries

Enable `pg_stat_statements` to identify the most expensive queries:

```sql
SELECT query, calls, mean_exec_time
FROM   pg_stat_statements
ORDER BY mean_exec_time DESC
LIMIT 10;
```
