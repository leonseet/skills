# Postgres control map

Read this index, then use the matching feature file as the recipe book. Setup, the session line, doctor, safety, the recipe variables and output shaping live in [`../SKILL.md`](../SKILL.md).

## Baseline

- `uv run ~/.agents/skills/control-postgres/scripts/postgres.py doctor` all `ok`, run from inside the repo whose `.env` holds the DSN.
- Every shell call starts with the session line from SKILL.md: `env` for `read` recipes, `env --write` for `write` and `destructive` ones. Recipes are runnable as written beneath it once their shell variables are set: `DB`, `SCH`, `T`, `COL`, `COLTYPE`, `IDX`, `PID`, `SECS`, `PATTERN`, `ID`, `NAME`, `PAYLOAD`, `FILE`, `OUT`. Each feature's `Finding things` says how to get them.
- Sandbox: schema `control_postgres_sandbox`, in the database SKILL.md's Sandbox rule settles. Prove write recipes there only.

## Common tasks

- **What is in this database?** [databases](./databases.md) `whoami` → [schemas](./schemas.md) `list` → [tables](./tables.md) `list` on the schema that matters.
- **What does this table look like?** [tables](./tables.md) `describe` → [rows](./rows.md) `select` with `limit 5`.
- **Answer a data question**: [tables](./tables.md) `describe` for columns and keys → [rows](./rows.md) `select`; `explain` first when the table is large and the filter has no index.
- **Hand someone the data**: [rows](./rows.md) `export CSV` into the scratchpad.
- **Fix a wrong value**: [rows](./rows.md) `select` to find the row → `update` preview → the user's yes → `update` → its read-back.
- **Copy a table's shape into a scratch schema**: [schemas](./schemas.md) `create` → [tables](./tables.md) `ddl`, with the schema name replaced, run in a write session → `describe`.
- **Why does my migration or query hang?** [activity](./activity.md) `blockers` → `sessions` for each `blocked_by` pid → `cancel`, then `terminate` with the user's yes.
- **Is the server running out of connections?** [activity](./activity.md) `connections` → `sessions`.
- **Clean up test schemas**: [schemas](./schemas.md) `leftovers` → `drop` preview per schema → the user's yes → `drop`.

## Feature entry contract

Each feature file has an H1, one paragraph saying what the resource is here, and a `Commands:` line naming the psql statements and script commands it covers, then exactly four H2s in this order:

1. `Operations`: one line each, tagged `read` / `write` / `destructive`.
2. `Finding things`: how to set the shell variables the recipes use.
3. `Recipes with psql`: one H3 per operation, `### <operation> (<tag>)`: the command, the output shape, and for writes, the read-back.
4. `Gotchas`.

A feature is one resource area. An operation shared between areas has one owner and the others link to it. To find the recipes a PostgreSQL upgrade touches, grep the `Commands:` lines.

## Features

Proven live on one PostgreSQL 14.24 server as an app's owner role: reads against that app's live database; writes and destructive recipes only on objects the proof created, in `control_postgres_sandbox` (table `proof`, dropped afterwards) and a throwaway `control_postgres_sandbox_proof_tmp` (created and dropped). `cancel` and `terminate` ran against the proof's own `pg_sleep` sessions. A recipe that fails is possible drift: check `psql --help`, `\?` and the PostgreSQL docs for the installed version, fix the recipe, and re-prove it.

| File | Covers | Proven | psql | PostgreSQL | Unproven |
| --- | --- | --- | --- | --- | --- |
| [databases](./databases.md) | whoami, list databases, roles, settings, other database | 2026-11-11 | 14.24 | 14.24 | none |
| [schemas](./schemas.md) | list, leftovers, create, drop | 2026-11-11 | 14.24 | 14.24 | none |
| [tables](./tables.md) | list, describe, ddl, privileges, create, add column, create index, drop index, drop column, truncate, drop table | 2026-11-11 | 14.24 | 14.24 | none |
| [rows](./rows.md) | select, count, explain, export CSV, insert, import CSV, update, delete | 2026-11-11 | 14.24 | 14.24 | none |
| [activity](./activity.md) | connections, sessions, long running, blockers, cancel, terminate | 2026-11-11 | 14.24 | 14.24 | `cancel` and `terminate` on another client's session |
