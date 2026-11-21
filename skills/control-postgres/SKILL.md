---
name: control-postgres
description: "Operate a PostgreSQL server (the one the repo's DSN names) through psql: server and databases, schemas, tables (describe, DDL, indexes, create, alter, drop), rows (query as JSON, count, explain, CSV export and import, insert, update, delete) and activity (sessions, long queries, locks, cancel). Use whenever a task reads or changes anything in a Postgres database."
---

# Control Postgres

The server is the one the DSN names (proven on PostgreSQL 14). Every operation goes through `psql` (and `pg_dump` from the same package) inside a **session**: the `PG*` variables that `scripts/postgres.py env` builds from the current repo's DSN. `scripts/postgres.py` holds `doctor`, `env` and the `describe` chain.

## Session

Shell state does not carry between tool calls, so every shell call that runs a recipe starts with one session line, run from inside the repo whose `.env` holds the DSN:

```bash
eval "$(uv run ~/.agents/skills/control-postgres/scripts/postgres.py env)"           # read session
eval "$(uv run ~/.agents/skills/control-postgres/scripts/postgres.py env --write)"   # write session
```

- A **read session** is read-only on the server (`default_transaction_read_only=on`) with a 60 s statement timeout (`--timeout <s>` changes it). A write in it fails with `cannot execute … in a read-only transaction`. Every `read` recipe runs in a read session.
- A **write session** can change data and gives up after 10 s waiting on a lock (`lock_timeout`). Open one only for a `write` or `destructive` recipe.
- `--db <name>` targets another database on the server with the same role.
- The eval puts the password in the shell call's environment only. It never appears in output; keep it that way: never print `env`'s output or `$PGPASSWORD`.

## Setup

A new machine needs, in this order (`doctor` checks each and prints the fix for what is missing):

1. `uv`: `curl -LsSf https://astral.sh/uv/install.sh | sh`. `doctor` and `env` run on it.
2. `psql` and `pg_dump`, at the server's major version or newer. Debian/Ubuntu: `sudo apt install postgresql-client`. macOS: `brew install libpq && brew link --force libpq`.
3. `jq`: `sudo apt install jq` on Linux, `brew install jq` on macOS.
4. A DSN in the current repo's `.env`, or failing that the shell: `POSTGRES_DSN`, else `DATABASE_URL`, as `postgresql://<user>:<password>@<host>:5432/<database>`. The skill carries no default host. SQLAlchemy forms (`postgresql+psycopg://…`) are accepted as they are. Without a DSN, `POSTGRES_HOST`, `POSTGRES_PORT`, `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD` are used. When none is there, ask the user which server and database; they write the DSN in themselves, with the role its owner issued. Nothing is copied into `~/.pgpass` or `~/.pg_service.conf`; the DSN stays where the user put it.
5. A reachable host. `doctor` connects to the DSN's host and port. An internal host answers only on the network or VPN that serves it. Sessions use `sslmode=require` (`prefer` for localhost): encrypted, certificate not verified. To verify it, the user adds `?sslmode=verify-full&sslrootcert=/path/to/ca.pem` to the DSN.

## Doctor

```bash
uv run ~/.agents/skills/control-postgres/scripts/postgres.py doctor
```

One `ok`/`WARN`/`FAIL` line each: uv, psql and its version, pg_dump, jq, the connection and where it came from; then host reachable, auth (role and database), TLS, the read-session guard, and the server version against the one this map was proven on. Every `FAIL` has a `fix:` line under it. Run it first, and again whenever a command fails strangely.

On a `FAIL`, stop the task and walk the user through the `fix:` lines one at a time, offering to run each fix yourself; then rerun `doctor` until it is clean. Install commands and other system changes run only after the user's yes. The user writes the DSN into `.env` or their shell themselves, never into the chat. A `FAIL host` is usually a VPN that is down: say so and let the user connect. A `FAIL` with no fix you can apply is reported to the user, never worked around. A version `WARN` means a recipe may have drifted: check `psql --help` and `\?`.

## Instances & conventions

- **One server**: the one the DSN names. `doctor` reports the role, the database and the server version.
- **Instance notes**: `~/.config/control-postgres/instance.md`, this machine's notes on that server: which database belongs to which app, schema and naming conventions. Read it before the first recipe when it exists. For what it lacks, observe the server, then ask the user, and offer to record their answer there (names and conventions, never secrets).
- **The session's database is the one in the DSN.** A role can often connect to other databases on the server and list their tables. Stay in the DSN's database; use `--db` only for a database the user named.
- **Treat every database as backing a live app.** Outside the sandbox, write only to the schema and table the user named.
- **Recipe variables**: `DB` database, `SCH` schema, `T` table, `COL` column, `COLTYPE` column type, `IDX` index name, `PID` backend pid, `FILE` local input file, `OUT` local output file, plus the row values a feature names. Each feature's `Finding things` says how to get them.
- **Values and names reach SQL through psql variables**: `-v sch="$SCH"` on the command line, then `:"sch"` for a name and `:'val'` for a value inside a quoted heredoc (`<<'SQL'`). psql quotes them, so a `-` in a name or a `'` in a value is safe. `-c` does not expand them.
- **Sandbox**: schema `control_postgres_sandbox` in a database the user agreed to. Before the first proof write, tell the user which database the DSN points at and that the schema will be created there, and wait for their yes.

## Safety

Every operation in `features/` is tagged:

- **read**: run freely, in a read session.
- **write**: run when the user asked for that change, in a write session, then run the recipe's read-back and report what it shows.
- **destructive** (drop, truncate, delete, update over existing rows, terminate a session): show the user exactly what goes, using the recipe's preview, and run it only after their explicit yes in the conversation.

SQL of your own follows the same tags: a statement that changes or removes existing rows or objects is destructive, whatever recipe it started from. Passwords and DSNs never appear in your output, files, commits or messages.

## Operate

Read [`features/README.md`](features/README.md): the common-task chains, then one recipe file per resource area.

## Output shaping

Keep calls few and output small:

- `psql -XAt` always: `-X` skips `~/.psqlrc`, `-At` prints bare values. Add `-q` to a write so only its `returning` output prints.
- Rows come back as JSON: wrap the query as `select coalesce(json_agg(t), '[]') from (<query>) t` and pipe to a `jq` projection.
- Every query carries a `limit`. Cut wide `text` and `jsonb` columns in SQL: `left(col::text, 200)`.
- Large results go to a file with `\copy … to` (rows recipe `export CSV`), never through the conversation.
- Several statements in one call go in one heredoc; one connection costs about 0.1 s, a second tool call costs far more.

## Gotchas

- `psql: error: definition of service "control-postgres-env-failed" not found` means the session line failed: the current directory is not inside a repo whose `.env` holds a DSN, and the shell has none. `cd` into that repo, or run `doctor`.
- `ERROR: cannot execute <STATEMENT> in a read-only transaction` means a write ran in a read session. Open a write session, after checking the operation's tag.
- `ERROR: canceling statement due to statement timeout` in a read session: raise it with `env --timeout 300`, or narrow the query.
- `ERROR: canceling statement due to lock timeout` in a write session: another session holds the table. Find it with the activity recipe `blockers`; retry later rather than waiting inside a lock queue, which stalls the app behind you.
- `sslmode=verify-full` fails with `certificate verify failed` when `sslrootcert` does not hold the CA that signed the server's certificate (a self-signed server: its own certificate). `server does not support SSL, but SSL was required` means the server has TLS off: only a localhost server is reached that way, through `sslmode=prefer`.
- Names with `-` or capitals (`my-app-dev`, a role or a database) need double quotes in SQL: `"my-app-dev"`. `:"var"` adds them.
- A table's `est_rows` is `-1` for a table that was never analyzed; use the rows recipe `count` for the real number.
