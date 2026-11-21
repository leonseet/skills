# Server and databases

A shared server commonly hosts one database per app and environment, each owned by a login role. An app role is an ordinary owner, usually without superuser, `CREATEDB` or `CREATEROLE` (`whoami` tells): it owns its own database, can create schemas in it, and can connect to the others.

Commands: `psql -c`, `postgres.py env --db`.

## Operations

- `whoami` (read): the session's role, database, server version and what the role may do.
- `list databases` (read): every database with owner and size.
- `roles` (read): the server's roles and their attributes.
- `settings` (read): server settings that shape behaviour.
- `other database` (read): open a session on another database of this server.

## Finding things

- `DB`: a database name from `list databases`. The DSN's own database needs no variable; it is the session default.
- Which app owns a database: its owner role carries the app's name.

## Recipes with psql

### whoami (read)

```bash
psql -XAtc "select json_build_object('role', current_user, 'database', current_database(), 'server', split_part(current_setting('server_version'), ' ', 1), 'read_only', current_setting('transaction_read_only'), 'superuser', r.rolsuper, 'createdb', r.rolcreatedb, 'createrole', r.rolcreaterole, 'can_create_schema', has_database_privilege(current_database(), 'CREATE')) from pg_roles r where r.rolname = current_user" | jq -c .
```

Returns `{role, database, server, read_only, superuser, createdb, createrole, can_create_schema}`. `read_only` is `"on"` in a read session.

### list databases (read)

```bash
psql -XAtc "select coalesce(json_agg(t), '[]') from (select d.datname as name, pg_get_userbyid(d.datdba) as owner, pg_size_pretty(pg_database_size(d.datname)) as size from pg_database d where not d.datistemplate order by pg_database_size(d.datname) desc limit 60) t" | jq -c '.[]'
```

Returns one `{name, owner, size}` per line, largest first.

### roles (read)

```bash
psql -XAtc "select coalesce(json_agg(t), '[]') from (select rolname as role, rolsuper as superuser, rolcreatedb as createdb, rolcanlogin as login from pg_roles where rolname !~ '^pg_' order by rolname limit 100) t" | jq -c '.[]'
```

Returns one `{role, superuser, createdb, login}` per line.

### settings (read)

```bash
psql -XAtc "select json_object_agg(name, setting || coalesce(' ' || unit, '')) from pg_settings where name in ('max_connections', 'TimeZone', 'server_encoding', 'search_path', 'work_mem', 'shared_buffers', 'password_encryption')" | jq -c .
```

Returns one object, e.g. `{"max_connections":"100","shared_buffers":"16384 8kB","TimeZone":"Etc/UTC",…}`: a value, then its unit when it has one (`16384 8kB` is 16384 pages of 8 kB). `statement_timeout`, `lock_timeout` and `default_transaction_read_only` would show the session's own values, not the server's.

### other database (read)

```bash
eval "$(uv run ~/.agents/skills/control-postgres/scripts/postgres.py env --db "$DB")"
psql -XAtc "select json_build_object('database', current_database(), 'schemas', (select count(*) from pg_namespace where nspname !~ '^pg_' and nspname <> 'information_schema'), 'tables', (select count(*) from pg_tables where schemaname !~ '^pg_' and schemaname <> 'information_schema'))" | jq -c .
```

Returns `{database, schemas, tables}` for `DB`. Every later recipe in the same shell call runs against `DB`.

## Gotchas

- Creating, renaming or dropping a database or a role needs `CREATEDB`, `CREATEROLE` or superuser, which most app roles lack: `ERROR: permission denied to create database`. Those go to the infra team.
- `psql -l` and `\l` print a wide human table; the `list databases` recipe is the compact form.
- Connecting to another app's database succeeds and its table names are visible, so nothing on the server stops a session from wandering. A `permission denied for table` there is the expected boundary, not a fault to fix.
