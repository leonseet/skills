# Langfuse control map

Read this index, then use the matching feature file as the recipe book. Setup, doctor, safety, `LF`/`LFPY` and output shaping live in [`../SKILL.md`](../SKILL.md).

## Baseline

- `uv run -q "$LFPY" doctor` all `ok`.
- `LF` and `LFPY` set as in SKILL.md, from the repo root.
- Recipes are runnable as written once their shell variables are set. Each feature's `Finding things` says how to get them: `FROM`/`TO`, `T`, `O`, `F`, `P`, `V`, `L`, `D`, `DID`, `I`, `E`, `NAME`, `S`, `C`, `OT`/`OID`, `FILE`.
- Sandbox: `control-sandbox*` objects and environment `control-sandbox`, in the project SKILL.md's Sandbox rule settles. Write recipes in proof run only there.

## Common tasks

Chains across features. Each step names the recipe that does it.

- **Why did this request go wrong?** [observations](./observations.md) `find errors` or `recent traces` (narrow with `--user-id`/`--session-id`) → `show trace` → `observation in full` on the failing step → [scores](./scores.md) `list scores` for the trace.
- **What does this app cost?** [observations](./observations.md) `metrics` by `providedModelName`, then by `traceName`, with a daily `timeDimension` for the trend → `search with a filter` (`totalCost >`) for the outliers.
- **Ship a prompt change**: [prompts](./prompts.md) `pull to file` → edit → `new version from file` with `--label staging` → `diff versions` → after the user approves, `promote` to `production`.
- **Roll back a prompt**: [prompts](./prompts.md) `list` → `diff versions` (current vs previous) → `promote` the previous version.
- **Turn a bad trace into a test case**: [observations](./observations.md) `observation in full` on the root → [datasets](./datasets.md) `add item` with `sourceTraceId`.
- **How did the last experiment do?** [datasets](./datasets.md) `list experiments` → `experiment results` → `show trace` on a failing item's `traceId`.
- **Is ingestion working?** `doctor` → [observations](./observations.md) `send test trace` → `show trace` on its id.

## Feature entry contract

Each feature file has an H1, one paragraph saying what the resource is here, and a `Commands:` line naming the CLI and script commands it covers, then exactly four H2s in this order:

1. `Operations`: one line each, tagged `read` / `write` / `destructive`.
2. `Finding things`: how to set the shell variables the recipes use.
3. `Recipes with langfuse`: one H3 per operation, `### <operation> (<tag>)`: the command with its `jq` projection, the output shape, and for writes, the read-back.
4. `Gotchas`.

A feature is one resource area. An operation shared between areas has one owner and the others link to it. To find the recipes a CLI or server upgrade touches, grep the `Commands:` lines.

## Features

Proven live on one self-hosted Langfuse v4, in a test project: reads against the sandbox data; writes only on `control-sandbox*` objects and environment `control-sandbox`; destructive recipes only on sandbox objects created for that purpose in the same run, at the user's request. A recipe that fails is possible drift: check `$LF api help <resource> <action>`, fix the recipe or script, and re-prove it.

| File | Covers | Proven | CLI | Service | Unproven |
| --- | --- | --- | --- | --- | --- |
| [observations](./observations.md) | recent traces, find errors, show trace, observation in full, search with a filter, metrics, send test trace, delete trace | 2026-11-05 | @langfuse/cli 1.3.1, SDK 5.1.0 | Langfuse 4.75.0 | none |
| [prompts](./prompts.md) | list, show, pull to file, diff versions, create, new version from file, promote, delete version | 2026-11-05 | @langfuse/cli 1.3.1, SDK 5.1.0 | Langfuse 4.75.0 | none |
| [datasets](./datasets.md) | list datasets, show dataset, list items, export items, create dataset, add item, archive item, delete item, list experiments, experiment results | 2026-11-05 | @langfuse/cli 1.3.1, SDK 5.1.0 | Langfuse 4.75.0 | none |
| [scores](./scores.md) | list scores, score aggregates, add score, delete score, list configs, create config, archive config, list comments, add comment | 2026-11-05 | @langfuse/cli 1.3.1, SDK 5.1.0 | Langfuse 4.75.0 | none |
