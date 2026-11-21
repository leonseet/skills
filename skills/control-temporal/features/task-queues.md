# Task queues and workers

A task queue is the named mailbox the server puts workflow and activity tasks in; a worker process polls one queue and runs whatever it finds. Nothing registers a queue: it exists while someone polls it or tasks wait in it. When each deployment and each developer has its own queue, "is my run going to be picked up" is "does a worker poll the Run's queue".

Commands: `temporal.py task-queue`, `workers`; API `/api/v1/namespaces/:ns/task-queues/:tq?taskQueueType=1|2&reportStats=true`, `/api/v1/namespaces/:ns/workers`.

## Operations

- `task-queue` (read): the workflow and activity pollers of one queue, and its backlog.
- `workers` (read): running worker processes, from the heartbeats the SDK sends.

## Finding things

- `TQ`: a run's queue is `taskQueue` from [workflows](./workflows.md) `describe`. This repo's own queue is the `TEMPORAL_TASK_QUEUE` setting (repo `.env` first, then the shell): `TQ=$(uv run ~/.agents/skills/control-temporal/scripts/temporal.py info | jq -r '.taskQueue // empty')`. Empty means it is set nowhere: ask the user which queue. The instance notes (SKILL.md) hold how other queues are named.
- Queues with a live worker right now: `uv run ~/.agents/skills/control-temporal/scripts/temporal.py workers | jq -r '.[].taskQueue' | sort -u`.

## Recipes with temporal.py

### task-queue (read)

```bash
uv run ~/.agents/skills/control-temporal/scripts/temporal.py task-queue "$TQ" \
  | jq -c '{taskQueue, wf: (.workflow.pollers | if type == "array" then map(.identity + " " + .seen) else . end), act: (.activity.pollers | if type == "array" then map(.identity) else . end), backlog: .workflow.backlog, backlogAge: .workflow.backlogAge}'
```

Returns `{taskQueue, workflow: {pollers, backlog, backlogAge}, activity: {…}}`. `pollers` is `[{identity, seen, buildId?}]`, or `"none"` when no worker polled in the last few minutes. `seen` is how long ago the poller last asked (`45s`). `identity` is `<pid>@<host>`: a container id as host means a deployed stack, a machine name a developer's worker. A `backlog` above 0 with `pollers: "none"` is work waiting for a worker that is not there.

### workers (read)

```bash
uv run ~/.agents/skills/control-temporal/scripts/temporal.py workers --limit 50 \
  | jq -c '.[] | {taskQueue, identity, sdk, status, started, seen}'
```

Returns `[{taskQueue, identity, host, sdk, buildId?, status, started, seen}]`, sorted by queue. `--tq "$TQ"` keeps one queue. `started` is when the worker process came up, which dates the last deploy or restart.

## Gotchas

- `workers` lists only workers whose SDK sends heartbeats, and hides the server's own `temporal-sys-*` queues; `task-queue` pollers see every worker. When the two disagree, trust `task-queue`.
- Backlog counts are approximate and omitted when zero; the script reports `0`.
- One task queue serves both workflow and activity tasks. A worker can poll one kind without the other (an activity-only worker); check both lists.
