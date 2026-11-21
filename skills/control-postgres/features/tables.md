# Tables

A table is addressed as `schema.table`; the same table name usually exists in several schemas of one database (`public.orders`, `test_<hex>.orders`), so every recipe names the schema. App tables in `public` are created and changed by the app's migrations (alembic, for one); a table changed by hand drifts from them.

Commands: `postgres.py describe`, `pg_dump --schema-only`, `psql` over `pg_class`, `create table`, `alter table`, `create index`, `drop index`, `truncate`, `drop table`.

## Operations

- `list` (read): the tables of a schema with estimated rows and size.
- `describe` (read): one table's columns, constraints, indexes and incoming foreign keys.
- `ddl` (read): the `CREATE TABLE` and index statements that rebuild a table.
- `privileges` (read): who may do what on a table.
- `create` (write): a new table.
- `add column` (write): a new nullable column.
- `create index` (write): a new index, built without blocking writes.
- `drop index` (destructive): remove an index.
- `drop column` (destructive): remove a column and its data.
- `truncate` (destructive): remove every row, keep the table.
- `drop table` (destructive): remove the table and its data.

## Finding things

- `SCH`, `T`: schema and table. A table by part of its name, across schemas: `psql -XAtc "select schemaname || '.' || tablename from pg_tables where tablename ilike '%detect%' and schemaname !~ '^pg_' order by 1 limit 20"`.
- `COL`, `COLTYPE`: a column name and its SQL type (`text`, `integer`, `timestamptz`, `jsonb`). Existing columns: `describe`.
- `IDX`: an index name without schema. Existing ones: `describe`, under `indexes`.

## Recipes with psql

### list (read)

```bash
psql -XAt -v sch="$SCH" <<'SQL' | jq -c '.[]'
select coalesce(json_agg(t), '[]') from (select c.relname as table, case c.relkind when 'r' then 'table' when 'p' then 'partitioned' when 'v' then 'view' else 'matview' end as kind, c.reltuples::bigint as est_rows, pg_size_pretty(pg_total_relation_size(c.oid)) as size from pg_class c join pg_namespace n on n.oid = c.relnamespace where n.nspname = :'sch' and c.relkind in ('r', 'p', 'v', 'm') order by pg_total_relation_size(c.oid) desc limit 100) t;
SQL
```

Returns one `{table, kind, est_rows, size}` per line, largest first. Nothing printed means the schema is empty or absent.

### describe (read)

```bash
uv run ~/.agents/skills/control-postgres/scripts/postgres.py describe "$SCH.$T" \
  | jq -c '{table, est_rows, size, columns: [.columns[] | "\(.name) \(.type)" + (if .nullable then "" else " not null" end) + (if .default then " default \(.default)" else "" end)], constraints: [.constraints[] | "\(.name): \(.def)"], indexes: [.indexes[] | .def], referenced_by: [.referenced_by[] | "\(.table): \(.def)"]}'
```

The script returns `{table, kind, owner, est_rows, size, columns: [{name, type, nullable, default}], constraints: [{name, type, def}], indexes: [{name, def, size, valid}], referenced_by: [{table, name, def}]}`; the projection flattens it to strings. It needs no session line. A name with `-` or capitals is double-quoted inside the argument: `'"My-Schema".t'`.

### ddl (read)

```bash
pg_dump --schema-only --no-owner --no-privileges -t "\"$SCH\".\"$T\"" | grep -vE '^(--|SET |SELECT pg_catalog|\\(un)?restrict|$)|SET \(pg_attver='
```

Returns the `CREATE TABLE`, constraint and `CREATE INDEX` statements as SQL text. Use it to copy a table's shape into another schema. The filter also drops the `ALTER COLUMN … SET (pg_attver=…)` lines a `pg_dump` older than the server's minor version prints.

### privileges (read)

```bash
psql -XAt -v sch="$SCH" -v t="$T" <<'SQL' | jq -c .
select coalesce(json_object_agg(g.grantee, g.privs), '{}') from (select grantee, string_agg(privilege_type, ',' order by privilege_type) as privs from information_schema.table_privileges where table_schema = :'sch' and table_name = :'t' group by grantee) g;
SQL
```

Returns `{"<role>": "DELETE,INSERT,…"}`. It lists only grants the session's role made, received or owns.

### create (write)

```bash
psql -XAtq -v ON_ERROR_STOP=1 -v sch="$SCH" -v t="$T" <<'SQL'
create table :"sch".:"t" (
  id bigint generated always as identity primary key,
  name text not null,
  payload jsonb not null default '{}',
  created_at timestamptz not null default now()
);
SQL
```

The column list is the part to write for the task; this one is the sandbox table the [rows](./rows.md) recipes use. Prints nothing on success. Read-back: `describe` returns the columns and the `<t>_pkey` index.

### add column (write)

```bash
psql -XAtq -v ON_ERROR_STOP=1 -v sch="$SCH" -v t="$T" -v col="$COL" -v coltype="$COLTYPE" <<'SQL'
alter table :"sch".:"t" add column :"col" :coltype;
SQL
```

Read-back: `describe "$SCH.$T" | jq -c '.columns[-1]'` returns `{name, type, nullable: true, default: null}`. A nullable column without a default is added instantly at any table size.

### create index (write)

```bash
psql -XAtq -v ON_ERROR_STOP=1 -v sch="$SCH" -v t="$T" -v col="$COL" -v idx="$IDX" <<'SQL'
create index concurrently :"idx" on :"sch".:"t" (:"col");
SQL
```

Read-back: `describe "$SCH.$T" | jq -c '.indexes[] | {name, valid}'` lists the index with `valid: true`.

### drop index (destructive)

Preview: `describe "$SCH.$T" | jq -c '.indexes[]'`, and name the constraint it backs if any (`pk_…`, unique). Only after the user's explicit yes, in a write session:

```bash
psql -XAtq -v ON_ERROR_STOP=1 -v sch="$SCH" -v idx="$IDX" <<'SQL'
drop index concurrently :"sch".:"idx";
SQL
```

Read-back: `describe` no longer lists it.

### drop column (destructive)

Preview first and show it to the user: how many rows hold a value in the column.

```bash
psql -XAt -v sch="$SCH" -v t="$T" -v col="$COL" <<'SQL' | jq -c .
select json_build_object('column', :'col', 'rows', count(*), 'non_null', count(:"col")) from :"sch".:"t";
SQL
```

Only after their explicit yes, in a write session:

```bash
psql -XAtq -v ON_ERROR_STOP=1 -v sch="$SCH" -v t="$T" -v col="$COL" <<'SQL'
alter table :"sch".:"t" drop column :"col";
SQL
```

Read-back: `describe "$SCH.$T" | jq -c '[.columns[].name]'` no longer lists it.

### truncate (destructive)

Preview: [rows](./rows.md) `count` for the exact row count, and `describe` for `referenced_by`. Only after the user's explicit yes, in a write session:

```bash
psql -XAtq -v ON_ERROR_STOP=1 -v sch="$SCH" -v t="$T" <<'SQL'
truncate table :"sch".:"t";
SQL
```

Read-back: [rows](./rows.md) `count` returns `exact: 0`.

### drop table (destructive)

Preview: [rows](./rows.md) `count` for the exact row count, and `describe` for size and `referenced_by`. Only after the user's explicit yes, in a write session:

```bash
psql -XAtq -v ON_ERROR_STOP=1 -v sch="$SCH" -v t="$T" <<'SQL'
drop table :"sch".:"t";
SQL
```

Read-back: `list` no longer shows the table.

## Gotchas

- `create index concurrently` and `drop index concurrently` cannot run inside a transaction, so they stand alone in their heredoc and never under `psql -1`. A concurrent build that fails leaves an index with `valid: false`; drop it and build again.
- `alter table`, `truncate` and `drop table` take an exclusive lock. On a table the app is using, the write session's 10 s `lock_timeout` ends the attempt with `canceling statement due to lock timeout` instead of queueing every app query behind it.
- `truncate` and `drop table` refuse a table that others reference (`referenced_by` non-empty): `cannot truncate a table referenced in a foreign key constraint`. Adding `cascade` empties or unlinks the referencing tables too; preview those tables as well before proposing it.
- Adding a column with `not null` needs a default, and a volatile default (`now()` is fine, `gen_random_uuid()` is volatile) rewrites the whole table under the exclusive lock.
- `est_rows` comes from the last analyze: `-1` means never analyzed, and it lags after bulk changes.
- A hand-made change to an alembic-managed table (one with a `public.alembic_version`) is invisible to `alembic_version`; the next migration may fail on it. Schema changes to app tables belong in a migration.
