# Collections

A collection is one vector store inside a database: a fixed schema, its indexes, an optional BM25 function, and a load state. A schema cannot change in place, so a new schema or chunking strategy becomes a new collection (commonly the next `<name>_v<N>`), and an alias, when an app uses one, is how traffic moves to it.

Commands: `milvus.py cols`, `col-show`, `col-spec`, `col-create`, `col-load`, `col-release`, `alias-set`, `alias-drop`, `col-drop`.

## Operations

- `list` (read): collections in a database with stored rows, load state, aliases, vector fields.
- `show` (read): one collection's fields, functions, indexes, aliases, partitions and live row count.
- `spec` (read): schema + functions + indexes as a JSON spec that `create` accepts.
- `create new version` (write): a new collection with the same spec as an existing one.
- `create from spec` (write): a new collection from a spec file.
- `load` (write): load into memory so it can be queried and searched.
- `release` (write): free its memory; queries and searches on it fail until loaded again.
- `point alias` (write): create an alias or move it to another collection.
- `drop alias` (destructive).
- `drop` (destructive): the collection and all its data.

## Finding things

- `COL`: from `list`. The highest `_v<N>` is usually the current version; confirm against the app's config (`collection_name`) when it matters.
- `SRC`: an existing collection as `<db>/<col>`, e.g. `control_sandbox/docs_v1`.
- `ALIAS`: from `list` (`aliases`), or the name the app's config uses.
- `FILE`: a spec JSON, usually `col-spec` output edited with `jq`.

## Recipes with milvus.py

### list (read)

```bash
uv run -q "$M" cols --db "$DB" | jq -c '.[]'
```

One line per collection: `{"col","stored_rows","load","aliases","vectors":{"<field>": <dim>|"sparse"}}`. `stored_rows` is approximate (see Gotchas); use `show` or [entities](./entities.md) `count` for the real number.

### show (read)

```bash
uv run -q "$M" col-show --db "$DB" --col "$COL" | jq '{col, load, rows, aliases, functions, indexes, fields: [.fields[] | "\(.name):\(.type)\(if .dim then "(\(.dim))" else "" end)\(if .is_primary then "*" else "" end)"]}'
```

Returns load state, live `rows` (null when not loaded), aliases, `functions` (`[{name,type:"BM25",input,output}]`), `indexes` (`[{field,type,metric,state,pending}]`) and fields as `name:TYPE(dim)`, `*` on the primary key. `pending > 0` means rows not yet indexed.

### spec (read)

```bash
uv run -q "$M" col-spec --db "$DB" --col "$COL" > "$FILE"
```

Writes `{description, auto_id, enable_dynamic_field, consistency_level, fields:[{name,type,is_primary?,dim?,max_length?,nullable?,enable_analyzer?,analyzer_params?}], functions:[{name,type,input,output}], indexes:[{field,index_name,index_type,metric_type?,params}]}`.

### create new version (write)

```bash
uv run -q "$M" col-create --db "$DB" --col "$COL" --like "$SRC"
```

Prints `{"created":"<db>/<col>","load":"Loaded"}`: indexed, loaded and empty. Fill it by re-ingesting through the app, or with [entities](./entities.md) `copy rows`. Read-back: `show` lists the same fields, functions and indexes as `$SRC`, with `rows: 0`.

### create from spec (write)

```bash
uv run -q "$M" col-create --db "$DB" --col "$COL" --spec "$FILE"
```

Change the spec with `jq` first, e.g. a new vector dimension: `jq '(.fields[] | select(.name=="vector") | .dim) = 1536' "$FILE"`. Field `type` names are pymilvus `DataType` names (`VARCHAR`, `INT64`, `FLOAT_VECTOR`, `SPARSE_FLOAT_VECTOR`, `JSON`). A BM25 function needs its input field to have `enable_analyzer: true` and its output to be `SPARSE_FLOAT_VECTOR` with a `BM25` index. Read-back: `show`.

### load (write)

```bash
uv run -q "$M" col-load --db "$DB" --col "$COL"
```

Prints `{"col","load":"Loaded"}`. Large collections take a while; the command waits.

### release (write)

```bash
uv run -q "$M" col-release --db "$DB" --col "$COL"
```

Prints `{"col","load":"NotLoad"}`. On a live database, the app's searches on it fail until it is loaded again; say so to the user first. Read-back: `cols` shows `load: "NotLoad"`.

### point alias (write)

```bash
uv run -q "$M" alias-set --db "$DB" --col "$COL" --alias "$ALIAS"
```

Prints `{"alias","before":<previous collection or null>,"now":"<col>"}`. Apps that address the alias switch at once. Read-back: `cols` shows `$ALIAS` under `aliases` of `$COL`. Undo: rerun with `--col` set to `before`.

### drop alias (destructive)

```bash
uv run -q "$M" alias-drop --db "$DB" --alias "$ALIAS"
```

Prints the preview (`points_at`) and exits 3. After the user's explicit yes, rerun with `--yes`. Read-back: `cols` no longer shows it.

### drop (destructive)

```bash
uv run -q "$M" col-drop --db "$DB" --col "$COL"
```

Refuses while the collection has aliases. Otherwise prints the preview (`stored_rows`, `load`) and exits 3. Show it to the user; after their explicit yes rerun with `--yes`. Read-back: `cols` no longer lists it.

## Gotchas

- Loaded collections share the server's memory: release old `_v<N>` versions nobody queries rather than loading more.
- `stored_rows` counts deleted rows until compaction and misses new rows until a flush: a fresh copy shows `stored_rows: 0` with `rows: 5`.
- Scalar indexes on VARCHAR fields show `type: "default"`: created without an explicit type, Milvus picks one.
- A collection with a single `_default` partition separates tenants by scalar fields (e.g. `app_id`, `scope`), not partitions; `show` lists the partitions.
