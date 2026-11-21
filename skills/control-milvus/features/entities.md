# Entities

An entity is one row of a collection: a RAG chunk (`id`, `doc_id`, `text`, `vector`, …) or a ReID tracklet (`tracklet_id`, `camera_id`, `embedding`, …). Apps write them during ingestion; this feature is for inspecting them, fixing a few, moving them between versions, and removing a document's chunks.

Commands: `milvus.py count`, `query`, `get`, `insert`, `upsert`, `patch`, `copy-rows`, `delete`.

## Operations

- `count` (read): live rows matching a filter.
- `query` (read): rows matching a filter, vectors left out, long strings cut.
- `get` (read): rows by primary key.
- `export` (read): whole rows with vectors into a file, ready for `insert`/`upsert`.
- `insert` (write): add rows from a file.
- `upsert` (write): add rows, replacing whole rows whose key exists.
- `patch` (write): change some scalar fields of existing rows, keeping everything else.
- `copy rows` (write): copy rows between collections with the same schema.
- `delete` (destructive): rows by key or filter.

## Finding things

- `F`: a Milvus boolean expression over scalar fields, in single quotes with double-quoted strings: `'doc_id == "9c3e7268-b7f1-480d-a910-e4e1acd6f71d"'`, `'app_id == "dataprep_testing" and chunk_type == "table"'`, `'doc_title like "FAQ%"'`, `'camera_id in ["onyx_pantry","30a_front_entrance"]'`, `'metadata["meta_source_title"] like "%Handbook%"'`. Empty means all rows.
- `ID`/`IDS`: primary keys, comma-separated for `IDS`. From `query --fields <pk>`; the primary key is `id` for RAG chunks and `tracklet_id` for ReID ([collections](./collections.md) `show` marks it `*`).
- A document's chunks: `doc_id` (or `file_id` in docres v3+). Find it from a title: `query --filter 'doc_title like "Compensation%"' --fields doc_id,doc_title --limit 5`.
- `FILE`: rows as a JSON array or JSONL, each with every field except function outputs (`bm25_vector`); `export` writes exactly that.
- `SRC`, `DST`: `<db>/<col>`.

## Recipes with milvus.py

### count (read)

```bash
uv run -q "$M" count --db "$DB" --col "$COL" --filter "$F"
```

`{"count": N}`. Needs the collection loaded.

### query (read)

```bash
uv run -q "$M" query --db "$DB" --col "$COL" --filter "$F" --fields id,doc_id,doc_title,chunk_type,text --limit 10 --max-chars 200 | jq -c '.[]'
```

One row per line with the named fields; strings over `--max-chars` end in `…(+<n>)`. Without `--fields` every scalar field comes back.

### get (read)

```bash
uv run -q "$M" get --db "$DB" --col "$COL" --ids "$IDS" --fields id,doc_title,text --max-chars 500
```

`[{...}]` in no particular order; missing keys are silently absent.

### export (read)

```bash
uv run -q "$M" query --db "$DB" --col "$COL" --filter "$F" --limit 100 --with-vectors > "$FILE"
```

A JSON array of whole rows, vectors included, function outputs left out. Keep it in a file; a 1024-dim row is ~20 KB of JSON.

### insert (write)

```bash
uv run -q "$M" insert --db "$DB" --col "$COL" --file "$FILE"
```

`{"insert": N, "first_ids": [...]}`. Batches of 500. Milvus computes `bm25_vector` itself. A duplicate primary key is not rejected: you get two rows with the same key, so use `upsert` when rows may exist. Read-back: `count` with a filter on the inserted keys equals N.

### upsert (write)

```bash
uv run -q "$M" upsert --db "$DB" --col "$COL" --file "$FILE"
```

`{"upsert": N, "first_ids": [...]}`. Each row replaces the whole stored row: a field missing from the file becomes null or fails. Read-back: `get` on the keys.

### patch (write)

```bash
uv run -q "$M" patch --db "$DB" --col "$COL" --ids "$IDS" --set "$(jq -nc --arg v "$VALUE" '{doc_title: $v}')"
```

`{"patched": [ids], "fields": [...]}`. Reads each whole row, merges the `--set` fields, upserts; vectors and the BM25 field are kept. Build `--set` with `jq -n --arg` so quotes and markdown in the value survive. Refuses primary keys, function outputs and `auto_id` collections. Read-back: `get --ids "$IDS" --fields <the patched fields>`.

### copy rows (write)

```bash
uv run -q "$M" copy-rows --from "$SRC" --to "$DST" --filter "$F"
```

`{"copied": N, "from", "to"}`. Streams in batches of 500 with vectors; `$DST` must have the same schema (create it with [collections](./collections.md) `create new version`). Read-back: `count` on `$DST` with the same filter equals N.

### delete (destructive)

```bash
uv run -q "$M" delete --db "$DB" --col "$COL" --filter "$F"
```

Or `--ids "$IDS"` in place of `--filter`. Prints the preview (`filter`, `matching` count, `sample_ids`) and exits 3. Show it to the user; after their explicit yes rerun with `--yes` (plus `--live` on a live database). Read-back: `count` with the same filter is 0.

## Gotchas

- Upsert deletes every row with the key, then inserts one: it is also how to collapse duplicate keys left by a double `insert`. The deleted rows still count in `stored_rows` until compaction.
- `query` ordering is arbitrary; for "the first chunks of a doc" filter by `doc_id` and sort with `jq 'sort_by(.position)'`.
- JSON fields filter with `metadata["key"]`; a missing key is false, not an error.
