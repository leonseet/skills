# Activity

Activity is what the server is doing now: one backend process (`pid`) per client connection, its current statement, and the locks it holds or waits on. A session's role sees the statements of its own role's backends only; other roles' backends show up in counts with their query hidden. All apps share the server's `max_connections`.

Commands: `psql` over `pg_stat_activity`, `pg_blocking_pids`, `pg_cancel_backend`, `pg_terminate_backend`.

## Operations

- `connections` (read): connection counts for the server and this database.
- `sessions` (read): this database's backends with state and current statement.
- `long running` (read): statements and open transactions older than a threshold.
- `blockers` (read): who waits on a lock, and which backend holds it.
- `cancel` (write): stop a backend's current statement; its connection stays.
- `terminate` (destructive): close a backend's connection; its open transaction rolls back.

## Finding things

- `PID`: the `pid` of a backend from `sessions`, `long running` or `blockers` (`blocked_by` lists the holders).
- `SECS`: an age threshold in seconds, e.g. `30`.
- Which program a backend belongs to: `app` (the client's `application_name`; this skill's sessions are `control-postgres`, most apps leave it empty) and `client` (its address).

## Recipes with psql

### connections (read)

```bash
psql -XAtc "select json_build_object('server', (select count(*) from pg_stat_activity where backend_type = 'client backend'), 'max', current_setting('max_connections')::int, 'this_database', (select json_object_agg(s.state, s.n) from (select coalesce(state, 'none') as state, count(*) as n from pg_stat_activity where datname = current_database() group by 1) s))" | jq -c .
```

Returns `{server, max, this_database: {"idle": n, "active": n, …}}`.

### sessions (read)

```bash
psql -XAtc "select coalesce(json_agg(t), '[]') from (select pid, usename as role, application_name as app, client_addr as client, state, wait_event_type as waiting, date_trunc('second', now() - state_change)::text as in_state, left(query, 120) as query from pg_stat_activity where datname = current_database() and pid <> pg_backend_pid() order by state_change limit 50) t" | jq -c '.[]'
```

Returns one `{pid, role, app, client, state, waiting, in_state, query}` per line, longest in its state first. `state` is `active`, `idle`, or `idle in transaction`; for an idle backend `query` is its last statement.

### long running (read)

```bash
psql -XAt -v secs="$SECS" <<'SQL' | jq -c '.[]'
select coalesce(json_agg(t), '[]') from (select pid, application_name as app, state, date_trunc('second', now() - xact_start)::text as xact_age, date_trunc('second', now() - query_start)::text as query_age, left(query, 160) as query from pg_stat_activity where datname = current_database() and pid <> pg_backend_pid() and state <> 'idle' and now() - coalesce(xact_start, query_start) > make_interval(secs => :'secs'::int) order by coalesce(xact_start, query_start) limit 20) t;
SQL
```

Returns one `{pid, app, state, xact_age, query_age, query}` per line, oldest first; nothing printed means no statement or transaction is older than `SECS`.

### blockers (read)

```bash
psql -XAtc "select coalesce(json_agg(t), '[]') from (select a.pid as waiting_pid, pg_blocking_pids(a.pid) as blocked_by, date_trunc('second', now() - a.query_start)::text as waiting_for, left(a.query, 120) as query from pg_stat_activity a where a.datname = current_database() and cardinality(pg_blocking_pids(a.pid)) > 0 order by a.query_start limit 20) t" | jq -c '.[]'
```

Returns one `{waiting_pid, blocked_by: [pids], waiting_for, query}` per line; nothing printed means nobody waits on a lock. Look up each `blocked_by` pid in `sessions`; an `idle in transaction` holder is a client that began a transaction and stopped.

### cancel (write)

```bash
psql -XAt -v pid="$PID" <<'SQL'
select pg_cancel_backend(:'pid'::int);
SQL
```

Prints `t` when the signal was sent. It runs in a read session. Read-back, a moment later:

```bash
psql -XAt -v pid="$PID" <<'SQL' | jq -c .
select coalesce((select json_build_object('pid', pid, 'state', state, 'query', left(query, 80)) from pg_stat_activity where pid = :'pid'::int), json_build_object('pid', :'pid'::int, 'state', 'gone'));
SQL
```

Returns `{pid, state, query}`: `state` is `idle` (or `gone`, if the client disconnected on the error) instead of `active`.

### terminate (destructive)

Preview first and show it to the user: the `cancel` read-back for `PID`, which names the backend's state and statement. Try `cancel` first. Only after their explicit yes:

```bash
psql -XAt -v pid="$PID" <<'SQL'
select pg_terminate_backend(:'pid'::int);
SQL
```

Prints `t`. Read-back: the `cancel` read-back returns `state: "gone"`.

## Gotchas

- `pg_cancel_backend` and `pg_terminate_backend` reach only backends of the session's own role; on another role's backend they fail with `must be a member of the role whose process is being terminated`. `f` with `WARNING: PID … is not a PostgreSQL server process` means the pid no longer exists.
- Terminating an app's pooled connection makes the app's next use of it fail once (`server closed the connection unexpectedly`) before the pool reconnects.
- `idle` backends are pool connections at rest and normal; `idle in transaction` for minutes is the one that holds locks and blocks migrations.
- A cancelled statement's client receives `ERROR: canceling statement due to user request`; a client that retries on error will run it again.
