# Databases

A database is a namespace, usually one app's; `default` always exists. Collection names only need to be unique within a database, so every collection command takes `--db`.

Commands: `milvus.py dbs`, `db-create`, `db-drop`.

## Operations

- `list` (read): every database, its collection count, and whether it is scratch.
- `create` (write): an empty database.
- `drop` (destructive): remove an empty database.

## Finding things

- `DB`: from `list`. An app's database is named in its config as `db_name` (or `MILVUS_DB`); without one, the app uses `default`.

## Recipes with milvus.py

### list (read)

```bash
uv run -q "$M" dbs | jq -c '.[]'
```

One line per database: `{"db","collections","scratch"}`. `scratch: false` means live app data: writes there need `--live`.

### create (write)

```bash
uv run -q "$M" db-create "$DB"
```

Prints `{"created": DB}`; refuses a name that exists. Read-back: `uv run -q "$M" dbs | jq -c --arg db "$DB" '.[] | select(.db == $db)'` shows it with `collections: 0`. A new database is live (`scratch: false`) unless its name starts with `control_sandbox`.

### drop (destructive)

```bash
uv run -q "$M" db-drop "$DB"
```

Refuses while the database has collections: drop those first ([collections](./collections.md) `drop`). With none left, it prints the preview and exits 3. Show it to the user; after their explicit yes rerun with `--yes` (and `--live` for a live database). Read-back: `dbs` no longer lists it.

## Gotchas

- Dropping a database cannot be undone, and with authentication off nothing on the server asks twice.
- `default` may hold real collections; treat it as live like the others.
