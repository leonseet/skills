# Notion control map

Read this index, then use the matching feature file as the recipe book. Setup, doctor, safety, the workspace layout, the recipe variables and output shaping live in [`../SKILL.md`](../SKILL.md).

## Baseline

- `uv run ~/.agents/skills/control-notion/scripts/notion.py doctor` all `ok`.
- `NJQ="-L $HOME/.agents/skills/control-notion/scripts"` set in the shell; recipes use it unquoted, as `jq $NJQ 'include "notion"; …'`.
- Recipes run as written once their shell variables are set. Each feature's `Finding things` says how to get them.
- Sandbox: the page the workspace map names (SKILL.md). Prove write recipes there only.

## Common tasks

- **Read a page the user linked**: `P` from the URL ([pages](./pages.md) `Finding things`) → [pages](./pages.md) `read`.
- **Fix or update a passage**: [pages](./pages.md) `read` → `edit text` with the exact old text → `read` as the read-back.
- **Add notes or a section to a page**: [pages](./pages.md) `append`. Put a new page where SKILL.md's "Where a new page goes" says → [pages](./pages.md) `create`.
- **Put a chart, plot or image on a page**: slim plotly HTML first ([files](./files.md) gotchas) → [files](./files.md) `attach`, with `--after` the block it belongs below.
- **Fill a Datasets page**: [blocks](./blocks.md) `list all` to find the Task's toggle → [blocks](./blocks.md) `insert` the text into it, using the toggle id as `PARENT` → [files](./files.md) `attach` each crop with the same `PARENT`.
- **Restructure a page (move entries, archive old ones)**: [blocks](./blocks.md) `copy` to the new place → `list all` to check the copy → `delete` the originals, after the user's yes. For whole pages, [pages](./pages.md) `move`.
- **Find rows (stand-ups for a week, projects in progress)**: [databases](./databases.md) `find` → `schema` → `query` with a filter.
- **Track something in a table**: [databases](./databases.md) `create database` on the page → `add row` for each item → `update row` as items change.
- **Answer review comments on a page**: the skill `notion-review-comments` owns this. By hand: `notion-get-comments` (SKILL.md "Beyond ntn") → [comments](./comments.md) `as Claude Agent` in each discussion.

## Feature entry contract

Each feature file has an H1, one paragraph saying what the resource is here, and a `Commands:` line naming the ntn commands and script commands it covers. Then come exactly four H2s, in this order:

1. `Operations`: one line each, tagged `read` / `write` / `destructive`.
2. `Finding things`: how to set the shell variables the recipes use.
3. `Recipes with ntn`: one H3 per operation, `### <operation> (<tag>)`: the command, the output shape, and for writes, the read-back.
4. `Gotchas`.

A feature is one resource area. An operation shared between areas has one owner, and the others link to it. To find the recipes an ntn upgrade or a new API version touches, grep the `Commands:` lines.

## Features

Proven live on one workspace: reads against its live pages. Writes and destructive recipes ran only in the sandbox, each after its preview. A recipe that fails may have drifted: check `ntn <command> --help` or `ntn api <path> --spec` for the installed version, fix the recipe, and re-prove it.

| File | Covers | Proven | ntn | API | Unproven |
| --- | --- | --- | --- | --- | --- |
| [pages](./pages.md) | find by title, read, info, create, append, edit text, rename, move, restore, replace content, trash | 2026-11-11 | 0.23.28 | 2026-03-11 | none |
| [blocks](./blocks.md) | list children, list all, get, insert, update, copy, move, delete | 2026-11-11 | 0.23.28 | 2026-03-11 | none |
| [files](./files.md) | attach, upload, import from URL, use an upload, replace image, status, list | 2026-11-11 | 0.23.28 | 2026-03-11 | none |
| [databases](./databases.md) | find, schema, query, add row, update row, add property, create database, trash row, drop property | 2026-11-11 | 0.23.28 | 2026-03-11 | none |
| [comments](./comments.md) | list, add, reply, edit, delete | 2026-11-11 | 0.23.28 | 2026-03-11 | none |
| [suggested edits](./suggested-edits.md) | list, diff, suggest, resolve | 2026-11-19 | connector | connector | the inline-comment wrapper gotcha |
