# Temporal control map

Read this index, then use the matching feature file as the recipe book. Setup, doctor, safety, conventions and output shaping live in [`../SKILL.md`](../SKILL.md).

## Baseline

- `uv run ~/.agents/skills/control-temporal/scripts/temporal.py doctor` all `ok`.
- Recipes target the server `TEMPORAL_UI_URL` names; put `--local` right after `temporal.py` for the local docker Temporal.
- Recipes are runnable as written once their shell variables are set. Each feature's `Finding things` says how to get them.
- Sandbox: task queue `control-temporal-sandbox`, ids `control-temporal-sandbox-*`, in the namespace SKILL.md's Sandbox rule settles. Write recipes in proof run only there.

## Common tasks

- **Why is my run stuck?** [workflows](./workflows.md) `diagnose` with `W` = its workflow id. Its `hints` name the cause; then [task-queues](./task-queues.md) `task-queue` if no worker polls, or `history --only failures` for the error text.
- **Why did my run fail?** [workflows](./workflows.md) `result`, then `history --only failures` for the failing activity and its retries.
- **Will my dev worker pick up my runs?** [task-queues](./task-queues.md) `task-queue` with `TQ` from the repo's `TEMPORAL_TASK_QUEUE`: `workflow.pollers` lists a poller on your machine.
- **Which Runs are running or failed lately?** [workflows](./workflows.md) `count --by-status`, then `list --status <s>`.
- **Stop a run**: [workflows](./workflows.md) `cancel`; `terminate` only when cancel cannot finish (read its gotcha first).
- **Clean up stale local Runs**: `--local list --status running`, then `diagnose` each; they usually fail on nondeterminism after a code change and need the user's call on cancel or terminate.
- **What did the agent see or return in one step?** [workflows](./workflows.md) `history --only activities --payloads` with a wider `--width`, into a file for big ones.

## Feature entry contract

Each feature file has an H1, one paragraph saying what the resource is here, and a `Commands:` line naming the script commands and API paths it covers, then exactly four H2s in this order:

1. `Operations`: one line each, tagged `read` / `write` / `destructive`.
2. `Finding things`: how to set the shell variables the recipes use.
3. `Recipes with temporal.py`: one H3 per operation, `### <operation> (<tag>)`: the command, the output shape, and for writes, the read-back.
4. `Gotchas`.

A feature is one resource area. To find the recipes a Temporal UI or server upgrade touches, grep the `Commands:` lines.

## Features

Proven 2026-11-16: reads on a shared server (1.32.0, UI 2.54.1) and on stale runs in a local docker Temporal; writes in the shared server's sandbox (`start`, `signal`, `cancel` request, `terminate`, every schedule write including `delete`; the user approved the destructive ones for sandbox targets). That sandbox has no worker, so `query`, `reset` (it needs a completed workflow task), a cancel that closes the run, and `result` of a completed run were proven against a throwaway worker on the local Temporal's `control-temporal-sandbox` queue. A recipe that fails is possible drift: check the command's `--help`, fix the recipe, and re-prove it.

| File | Covers | Proven | Script | Service | Unproven |
| --- | --- | --- | --- | --- | --- |
| [workflows](./workflows.md) | list, count, describe, history, result, diagnose, start, signal, query, cancel, terminate, reset | 2026-11-16 | httpx 0.28.1 | UI 2.54.1, server 1.32.0 | none (`reset` proven on local, UI 2.49.1, server 1.31.0) |
| [task-queues](./task-queues.md) | task-queue, workers | 2026-11-16 | httpx 0.28.1 | UI 2.54.1, server 1.32.0 | none |
| [schedules](./schedules.md) | list, show, create, pause, unpause, trigger, delete | 2026-11-16 | httpx 0.28.1 | UI 2.54.1, server 1.32.0 | none |
| [namespace](./namespace.md) | info, search attributes | 2026-11-16 | httpx 0.28.1 | UI 2.54.1, server 1.32.0 | none |
