# Milvus control map

Read this index, then use the matching feature file as the recipe book. Setup, doctor, safety, `M` and output shaping live in [`../SKILL.md`](../SKILL.md).

## Baseline

- `uv run -q "$M" doctor` all `ok`.
- `M=~/.agents/skills/control-milvus/scripts/milvus.py` set, from the repo root.
- Recipes are runnable as written once their shell variables are set. Each feature's `Finding things` says how to get them: `DB`, `COL`, `ID`/`IDS`, `F`, `TEXT`, `FILE`, `ALIAS`, `SRC`/`DST`, `VALUE`.

## Common tasks

- **What does app X store?** [databases](./databases.md) `list` → [collections](./collections.md) `list` → `show` on the highest `_v<N>`.
- **Did my document get ingested?** [entities](./entities.md) `query` by `doc_title like` for its `doc_id` → `count` on that `doc_id`, split by `chunk_type` if needed.
- **Why doesn't retrieval return chunk X?** [collections](./collections.md) `show` (loaded? `pending` index rows?) → [search](./search.md) `bm25` with the user's words, and `similar` from a chunk that does come back → `hybrid` to see which half drops it.
- **Cut a new collection version**: [collections](./collections.md) `create new version` (or `spec` → edit → `create from spec`) → re-ingest through the app, or [entities](./entities.md) `copy rows` when the schema is unchanged → `count` on both → `point alias` if the app reads through one.
- **Fix a chunk's metadata**: [entities](./entities.md) `get` → `patch` → its read-back.
- **Remove a document**: [entities](./entities.md) `delete` with `--filter 'doc_id == "…"'` (preview, user's yes, `--yes`).
- **Free memory**: [collections](./collections.md) `list` → `release` old versions the user confirms no app reads.

## Feature entry contract

Each feature file has an H1, one paragraph saying what the resource is here, and a `Commands:` line naming the `milvus.py` commands it covers, then exactly four H2s in this order:

1. `Operations`: one line each, tagged `read` / `write` / `destructive`.
2. `Finding things`: how to set the shell variables the recipes use.
3. `Recipes with milvus.py`: one H3 per operation, `### <operation> (<tag>)`: the command, the output shape, and for writes, the read-back.
4. `Gotchas`.

A feature is one resource area. An operation shared between areas has one owner and the others link to it. To find the recipes a pymilvus or server upgrade touches, grep the `Commands:` lines.

## Features

Proven live on one Milvus 2.5 instance: reads against a scratch and two live databases; writes and destructive `--yes` runs (delete, drop alias, drop collection, drop database) only in the sandbox databases `control_sandbox` and `control_sandbox_dbproof`, both dropped at the end. A recipe that fails is possible drift: check `uv run -q "$M" <command> --help`, fix the script or recipe, and re-prove it.

| File | Covers | Proven | pymilvus | Milvus | Unproven |
| --- | --- | --- | --- | --- | --- |
| [databases](./databases.md) | list, create, drop | 2026-11-05 | 3.0.2 | 2.5.13 | none |
| [collections](./collections.md) | list, show, spec, create new version, create from spec, load, release, point alias, drop alias, drop | 2026-11-05 | 3.0.2 | 2.5.13 | none |
| [entities](./entities.md) | count, query, get, export, insert, upsert, patch, copy rows, delete | 2026-11-05 | 3.0.2 | 2.5.13 | none |
| [search](./search.md) | similar, bm25, hybrid | 2026-11-05 | 3.0.2 | 2.5.13 | none |
