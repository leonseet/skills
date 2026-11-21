# Schemas

A schema is a namespace of tables inside one database. Here `public` holds an app's live tables, and tests, evals and migration rehearsals each work in a schema of their own beside it, so a database collects many short-lived schemas that share table names.

Commands: `psql` over `pg_namespace`, `create schema`, `drop schema`.

## Operations

- `list` (read): every schema with owner, table count and size.
- `leftovers` (read): schemas matching a name pattern, to spot abandoned test schemas.
- `create` (write): a new empty schema.
- `drop` (destructive): a schema and everything in it.

## Finding things

- `SCH`: a schema name from `list`. The sandbox is `control_postgres_sandbox`.
- `PATTERN`: a POSIX regex over schema names, e.g. `^test_` or `^(test|qa_mig|eval)_`.
- The tables inside a schema: [tables](./tables.md) `list`.

## Recipes with psql

### list (read)

```bash
psql -XAtc "select coalesce(json_agg(t), '[]') from (select n.nspname as schema, pg_get_userbyid(n.nspowner) as owner, count(c.oid) as tables, pg_size_pretty(coalesce(sum(pg_total_relation_size(c.oid)), 0)) as size from pg_namespace n left join pg_class c on c.relnamespace = n.oid and c.relkind in ('r', 'p') where n.nspname !~ '^pg_' and n.nspname <> 'information_schema' group by n.oid order by coalesce(sum(pg_total_relation_size(c.oid)), 0) desc limit 100) t" | jq -c '.[]'
```

Returns one `{schema, owner, tables, size}` per line, largest first.

### leftovers (read)

```bash
psql -XAt -v pattern="$PATTERN" <<'SQL' | jq -c .
select json_build_object('count', count(*), 'size', pg_size_pretty(coalesce(sum(s.bytes), 0)), 'schemas', coalesce(json_agg(s.nspname order by s.nspname), '[]')) from (select n.nspname, coalesce((select sum(pg_total_relation_size(c.oid)) from pg_class c where c.relnamespace = n.oid and c.relkind in ('r', 'p')), 0) as bytes from pg_namespace n where n.nspname ~ :'pattern') s;
SQL
```

Returns `{count, size, schemas: [names]}`. A schema has no creation time; a date or issue number in its name is the only age hint.

### create (write)

```bash
psql -XAtq -v ON_ERROR_STOP=1 -v sch="$SCH" <<'SQL'
create schema :"sch";
SQL
```

Prints nothing on success. Read-back:

```bash
psql -XAt -v sch="$SCH" <<'SQL' | jq -c .
select json_build_object('schema', n.nspname, 'owner', pg_get_userbyid(n.nspowner), 'tables', (select count(*) from pg_class c where c.relnamespace = n.oid and c.relkind in ('r', 'p'))) from pg_namespace n where n.nspname = :'sch';
SQL
```

Returns `{schema, owner, tables: 0}`; no output means the schema does not exist.

### drop (destructive)

Preview first and show it to the user: every table that goes, with its size.

```bash
psql -XAt -v sch="$SCH" <<'SQL' | jq -c .
select json_build_object('schema', :'sch', 'objects', coalesce(json_agg(json_build_object('name', c.relname, 'est_rows', c.reltuples::bigint, 'size', pg_size_pretty(pg_total_relation_size(c.oid))) order by c.relname), '[]')) from pg_class c join pg_namespace n on n.oid = c.relnamespace where n.nspname = :'sch' and c.relkind in ('r', 'p', 'v', 'm');
SQL
```

Only after their explicit yes, in a write session:

```bash
psql -XAtq -v ON_ERROR_STOP=1 -v sch="$SCH" <<'SQL'
drop schema :"sch" cascade;
SQL
```

Prints `NOTICE: drop cascades to …` on stderr when the schema held objects. Read-back: the `create` read-back prints nothing.

## Gotchas

- `drop schema` without `cascade` refuses a non-empty schema (`cannot drop schema … because other objects depend on it`). `cascade` removes every table in it with no second question, which is why the preview comes first.
- `public` is owned by `postgres`: an app role can create tables in it but cannot drop or rename the schema itself.
- A test schema that looks abandoned may belong to a run in progress. Check [activity](./activity.md) `sessions` for a query naming it before proposing to drop it.
- `create schema` in a database other than the DSN's needs `CREATE` on that database; `whoami` reports it as `can_create_schema`.
