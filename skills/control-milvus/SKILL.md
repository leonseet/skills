---
name: control-milvus
description: "Operate a Milvus instance (the one MILVUS_URI names) through scripts/milvus.py on pymilvus: databases, collections (schema, indexes, load, aliases, new versions), entities (count, query, insert, patch, delete), and search (similar-to-stored, BM25, hybrid). Use whenever a task reads or changes anything in Milvus or a RAG vector store."
---

# Control Milvus

The Milvus instance is the one `MILVUS_URI` names (proven on Milvus 2.5.13). Every operation goes through our own CLI, `scripts/milvus.py`, which wraps pymilvus and prints compact JSON. `milvus_cli` lost because it is an interactive shell that prints tables, not JSON.

Set once per shell, from the repo root:

```bash
M=~/.agents/skills/control-milvus/scripts/milvus.py
```

Every recipe runs `uv run -q "$M" <command>`; `uv run -q "$M" <command> --help` lists its options.

## Setup

A new machine needs, in this order (`doctor` checks each and prints the fix for what is missing):

1. `uv`: `curl -LsSf https://astral.sh/uv/install.sh | sh`. `doctor` runs on it, so this one comes first. `uv run` installs pymilvus, typer and python-dotenv on first use from the script's inline dependencies.
2. `jq`: `sudo apt install jq` on Linux, `brew install jq` on macOS.
3. `MILVUS_URI`: the server's address (`http://<host>:19530`). The skill carries no default. The script reads it from the current repo's `.env` first, then the shell. When both lack it, ask the user; they put it in the repo's `.env` when it belongs to that project, or export it in their shell's startup file (`~/.bashrc`, `~/.zshrc`) for every repo.
4. `MILVUS_TOKEN`, read from the same two places, only when the server has authentication on (`user:password` or an API key). The user writes it in themselves.
5. A reachable host. `doctor` connects to the URI's host and port. An internal host answers only on the network or VPN that serves it. For an `https://` URI whose certificate comes from a private CA the machine lacks, `CONTROL_CA_FILE` names that CA's PEM file, read like the URI.

## Doctor

```bash
uv run -q "$M" doctor
```

One `ok`/`WARN`/`FAIL` line each: pymilvus, `MILVUS_URI` and the token with where each came from, `jq`, the host reachable; then the server version and listing databases. Every `FAIL` has a `fix:` line under it. Run it first, and again whenever a command fails strangely.

On a `FAIL`, stop the task and walk the user through the `fix:` lines one at a time, offering to run each fix yourself; then rerun `doctor` until it is clean. Install commands and other system changes run only after the user's yes; the user enters credentials themselves, never into the chat. A `FAIL reachable` is usually a VPN that is down: say so and let the user connect. A `FAIL` with no fix you can apply is reported to the user, never worked around. A version `WARN` means a recipe may have drifted: check the command's `--help` and re-prove it.

## Instances & conventions

- **One instance** per `MILVUS_URI`. `doctor` reports its version and whether a token is in use. With authentication off, every caller can create, change and drop anything, and the script's guards below are the only brake.
- **Instance notes**: `~/.config/control-milvus/instance.md`, this machine's notes on the instance `MILVUS_URI` names: which database belongs to which app, naming and schema conventions. Read it before the first recipe when it exists. For what it lacks, observe the instance, then ask the user, and offer to record their answer there (names and conventions, never secrets).
- **Live vs scratch**: every database holds live app data unless its name starts with `control_sandbox` or `MILVUS_SCRATCH_DBS` lists it (comma-separated, read like the URI; the user sets it, for databases they know are throwaway). `dbs` lists every database with a `scratch` flag. Write and destructive commands refuse a live database (exit 4) unless given `--live`; add it only when the user named that database for this change.
- **Variables** recipes use: `DB` database, `COL` collection, `ID`/`IDS` primary key(s), `F` filter expression, `TEXT` keyword query, `FILE` rows file, `ALIAS`, `SRC` `<db>/<col>`. Each feature's `Finding things` says how to get them.
- **Sandbox**: database `control_sandbox` (create it on demand with `db-create`, drop it when done). Prove new write recipes there.

## Safety

Every operation in `features/` is tagged:

- **read**: run freely.
- **write**: run when the user asked for that change, then run the recipe's read-back and report what it shows.
- **destructive** (drop, delete, drop alias): run the command **without** `--yes` first; it prints the preview (what goes, how many rows, sample ids) and exits 3. Show that preview to the user, and rerun with `--yes` only after their explicit yes in the conversation.

`col-release` and `alias-set` are writes, but on a live database they cut an app off from its data or switch it to another collection. Name the effect to the user before running them there.

## Operate

Read [`features/README.md`](features/README.md): the common-task chains, then one recipe file per resource area.

## Output shaping

- Commands print compact JSON. Pipe through `jq` to project fields or `jq -c '.[]'` for one hit per line.
- `query`, `get` and the searches leave vectors out and cut strings at `--max-chars` (300 for queries, 200 for searches). Name the fields you need with `--fields a,b`; `--max-chars 0` gives whole values, redirected into a file.
- Every listing has a limit: `--limit` defaults to 10. Raise it deliberately; count first with `count`.

## Gotchas

- A collection must be **loaded** to be counted, queried or searched; otherwise you get `collection not loaded`. `cols` shows `load`.
- Stats `stored_rows` is not the row count: it includes deleted rows until compaction and lags new inserts until a flush. `count` (or `rows` in `col-show`) is the live number.
- Vectors must come from the same embedding model as the collection. There is no embedding endpoint in this skill: search uses a stored entity's vector (`similar`) or keywords (`bm25`). Never insert made-up vectors into a live collection.
- Filter strings use double quotes inside: wrap the whole expression in single quotes in the shell, `--filter 'doc_id == "abc"'`.
