# Rows

Rows are read and changed with SQL sent through `psql`. Reads come back as JSON for `jq`; values go in through psql variables. The write recipes are written against the sandbox table from [tables](./tables.md) `create` (`id`, `name`, `payload`, `created_at`): keep their shape and replace the column list, `set` and `where` clauses for the table at hand.

Commands: `psql` heredoc, `psql -c "\copy …"`, `explain`.

## Operations

- `select` (read): the rows of a query as JSON.
- `count` (read): exact and estimated row count of a table.
- `explain` (read): the plan of a query, without running it.
- `export CSV` (read): a query's rows into a local CSV file.
- `insert` (write): one new row.
- `import CSV` (write): many new rows from a local CSV file.
- `update` (destructive): overwrite values in existing rows.
- `delete` (destructive): remove rows.

## Finding things

- `SCH`, `T`: schema and table; columns and keys from [tables](./tables.md) `describe`.
- `ID`: the primary-key value of one row, found with `select` on a column the user knows.
- `NAME`, `PAYLOAD`: the row values of the sandbox table; `PAYLOAD` is JSON text such as `{"k": 1}`.
- `OUT`, `FILE`: local paths; put them in the scratchpad.

## Recipes with psql

### select (read)

```bash
psql -XAt <<'SQL' | jq -c '.[]'
select coalesce(json_agg(t), '[]') from (
  select id, name, status, created_at from public.orders order by created_at desc limit 20
) t;
SQL
```

Returns one JSON object per row, keyed by column name. The inner query is the part to write; it always carries a `limit`. Filter by a value with a variable: add `-v status="$STATUS"` to the command and `where status = :'status'` to the query.

### count (read)

```bash
psql -XAt -v sch="$SCH" -v t="$T" <<'SQL' | jq -c .
select json_build_object('exact', (select count(*) from :"sch".:"t"), 'estimate', (select reltuples::bigint from pg_class where oid = format('%I.%I', :'sch', :'t')::regclass));
SQL
```

Returns `{exact, estimate}`. The exact count scans the table: about a second per few million rows.

### explain (read)

```bash
psql -XAt <<'SQL'
explain select id, quantity from public.order_items where order_id = '00000000-0000-0000-0000-000000000000';
SQL
```

Returns the plan as text lines (`Seq Scan on order_items …` or `Index Scan using …`), with estimated cost and rows. The statement is not run.

### export CSV (read)

```bash
psql -XAt -c "\copy (select id, name, status, created_at from public.orders order by created_at limit 1000) to '$OUT' with (format csv, header)"
```

Prints `COPY <n>`; the file has a header line and `n` rows. The query sits on one line: `\copy` ends at the newline.

### insert (write)

```bash
psql -XAtq -v ON_ERROR_STOP=1 -v sch="$SCH" -v t="$T" -v name="$NAME" -v payload="$PAYLOAD" <<'SQL' | jq -c .
insert into :"sch".:"t" as r (name, payload) values (:'name', :'payload'::jsonb) returning to_json(r);
SQL
```

Returns the stored row, e.g. `{"id":1,"name":"…","payload":{…},"created_at":"…"}`. Read-back: `update`'s preview with `ID` set to the returned `id` shows the same row.

### import CSV (write)

```bash
psql -XAt -v ON_ERROR_STOP=1 -c "\copy \"$SCH\".\"$T\" (name, payload) from '$FILE' with (format csv, header)"
```

Prints `COPY <n>`. The file's columns match the column list in order; all rows load or none. Read-back: `count` grew by `n`.

### update (destructive)

Preview first and show it to the user: the rows as they are now. For a `where` that matches many rows, show its `count(*)` and a `limit 5` sample instead.

```bash
psql -XAt -v sch="$SCH" -v t="$T" -v id="$ID" <<'SQL' | jq -c .
select to_json(r) from :"sch".:"t" r where r.id = :'id';
SQL
```

Only after their explicit yes, in a write session:

```bash
psql -XAtq -v ON_ERROR_STOP=1 -v sch="$SCH" -v t="$T" -v id="$ID" -v name="$NAME" <<'SQL' | jq -c .
update :"sch".:"t" r set name = :'name' where r.id = :'id' returning to_json(r);
SQL
```

Returns each changed row after the change; no output means the `where` matched nothing. Read-back: the preview shows the new value.

### delete (destructive)

Preview: the `update` preview with the same `where`, plus [tables](./tables.md) `describe` for `referenced_by` constraints that say `ON DELETE CASCADE`. Only after the user's explicit yes, in a write session:

```bash
psql -XAtq -v ON_ERROR_STOP=1 -v sch="$SCH" -v t="$T" -v id="$ID" <<'SQL' | jq -c .
delete from :"sch".:"t" r where r.id = :'id' returning to_json(r);
SQL
```

Returns each removed row; keep that output until the user confirms the result, since it is the only copy. Read-back: the preview prints nothing.

## Gotchas

- An `update` or `delete` without `where` changes every row. Write the `where` first and run it as the preview `select` before it goes into the write.
- `explain analyze` runs the statement. On an `insert`, `update` or `delete` it performs the change; use plain `explain` for writes.
- Several statements that must land together go in one heredoc wrapped in `begin; … commit;` with `-v ON_ERROR_STOP=1`: the first error then aborts the rest and the transaction rolls back when psql exits.
- `\copy` reads and writes files on this machine; server-side `copy … to '/path'` needs superuser and writes on the server.
- `timestamp without time zone` columns hold whatever local time the app wrote, with no offset; `timestamptz` columns print in the server's timezone (`show timezone`). Compare like with like.
- `uuid` and `jsonb` values pass as text and are cast in SQL: `:'id'::uuid`, `:'payload'::jsonb`. A malformed value fails the statement (`invalid input syntax for type …`) before any row changes.
- A `delete` on a parent row fails with `violates foreign key constraint` when child rows exist and the constraint has no `ON DELETE CASCADE`; delete the children first, as their own previewed step.
