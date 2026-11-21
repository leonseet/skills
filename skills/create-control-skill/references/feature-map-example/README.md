# Ticketd control map

An example of a control skill's `features/README.md`, for a made-up ticket service `ticketd` driven by its CLI `tix`. Copy the shape, not the content.

Read this index, then use the matching feature file as the recipe book. Setup, doctor, safety and output shaping live in [`../SKILL.md`](../SKILL.md).

## Baseline

- `uv run scripts/ticketd.py doctor` all `ok`.
- Default instance `tickets.internal`; queues are named `<team>-<area>` (`res-reid`, `ops-infra`).
- Sandbox: queue `sandbox-control`. Write recipes in proof run only there.

## Common tasks

Chains across features. Each step names the recipe that does it.

- **Check a reported bug is tracked**: [tickets](./tickets.md) `find by title` → `show`.
- **Close out a fixed bug**: [tickets](./tickets.md) `find by title` → `close` → its read-back.
- **Who is overloaded**: `uv run scripts/ticketd.py open-by-assignee --queue res-reid` (chain: list open → group → count).

## Feature entry contract

Each feature file has an H1, one paragraph saying what the resource is in this company, and a `Commands:` line naming the CLI groups it covers, then exactly four H2s in this order:

1. `Operations`: one line each, tagged `read` / `write` / `destructive`.
2. `Finding things`: how to resolve the identifiers the recipes need.
3. `Recipes with <cli>`: one H3 per operation: the command with its `jq` projection, the output shape, and for writes, the read-back.
4. `Gotchas`.

A feature is one resource area. An operation shared between areas has one owner and the others link to it. To find the recipes a CLI upgrade touches, grep the `Commands:` lines.

## Features

Treat a recipe that fails as possible drift: check `--help` for the installed version, fix the recipe, and re-prove it.

| File | Covers | Proven | CLI | Service | Unproven |
| --- | --- | --- | --- | --- | --- |
| [tickets](./tickets.md) | find, show, create, close, delete | 2026-11-04 | tix 2.3.1 | ticketd 5.2 | `delete` (destructive) |
