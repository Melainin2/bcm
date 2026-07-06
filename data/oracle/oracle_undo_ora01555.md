# Oracle — UNDO, Read Consistency and ORA-01555

## Read consistency and UNDO

Oracle uses UNDO segments (also called rollback segments) to provide read
consistency. When a query starts, Oracle guarantees it sees the data as of the
moment the query began. To reconstruct that point-in-time image, Oracle reads
the "before" values of changed rows from the UNDO tablespace.

## ORA-01555: snapshot too old

The error `ORA-01555: snapshot too old: rollback segment number ... too small`
occurs when a long-running query needs a consistent read of a block, but the
UNDO information required to reconstruct that block has already been overwritten
by other committed transactions. In other words, the UNDO was recycled before
the query finished.

Common causes:

- Long-running queries running concurrently with heavy DML (INSERT/UPDATE/DELETE).
- `UNDO_RETENTION` set too low for the duration of the longest query.
- An undersized UNDO tablespace that cannot honor the retention period.
- Frequent commits inside a loop that is also fetching across commits.

## How to fix ORA-01555

1. Increase `UNDO_RETENTION` so UNDO is kept at least as long as your longest query:
   ```sql
   ALTER SYSTEM SET UNDO_RETENTION = 3600;  -- seconds
   ```
2. Enlarge the UNDO tablespace, or enable AUTOEXTEND on its datafiles.
3. Enable retention guarantee to force Oracle to keep UNDO even if space is tight:
   ```sql
   ALTER TABLESPACE undotbs1 RETENTION GUARANTEE;
   ```
4. Avoid "fetch across commit": do not COMMIT inside a loop that keeps fetching
   from an open cursor over the same data.
5. Tune or split very long-running queries so they complete faster.

## Monitoring UNDO usage

```sql
SELECT begin_time, end_time, undoblks, maxquerylen
FROM   v$undostat
ORDER BY begin_time DESC;
```

`maxquerylen` shows the longest query (in seconds) during each interval — use it
to size `UNDO_RETENTION` correctly.
