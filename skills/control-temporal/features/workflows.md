# Workflows

A workflow execution is one durable run of workflow code, addressed by its workflow id; each attempt or reset under that id is a run with its own run id. Its history is the event log a worker replays: activities scheduled, started, completed or failed, signals, cancellation, the close.

Commands: `temporal.py list`, `count`, `describe`, `history`, `result`, `diagnose`, `start`, `signal`, `query`, `cancel`, `terminate`, `reset`; API `/api/v1/namespaces/:ns/workflows`, `/workflow-count`, `/workflows/:id`, `/workflows/:id/{history,history-reverse,signal/:name,query/:name,cancel,terminate,reset}`.

## Operations

- `list` (read): executions matching filters, newest first.
- `count` (read): how many match, optionally by status.
- `describe` (read): one execution's status, age, size, pending workflow task and pending activities.
- `history` (read): the compacted event log.
- `result` (read): how a closed execution ended.
- `diagnose` (read): why a running execution is stuck, slow or failing.
- `start` (write): start a workflow by type, queue and id.
- `signal` (write): send a signal to a running execution.
- `query` (read): ask the execution's live worker a question.
- `cancel` (write): request cancellation; the workflow's own cleanup runs.
- `terminate` (destructive): kill a run at once; no workflow code runs.
- `reset` (destructive): close the run and start a new one from an earlier workflow task.

## Finding things

- `W`: the workflow id, from `list` (`.[].id`). Apps often use their own record's id: the instance notes (SKILL.md) say which.
- `TYPE`: the workflow type, from `list` (`.[].type`) or the worker's code.
- `R`: a run id, needed only to address an earlier run of the same `W`; every command defaults to the latest. From `list` or `describe` (`.run`).
- Recent runs of one queue: `uv run ~/.agents/skills/control-temporal/scripts/temporal.py list --type "$TYPE" --tq "$TQ" --since 6h --limit 10 | jq -c '.[] | {id, status, start}'`. `TQ` is in [task-queues](./task-queues.md).
- A visibility `--query` takes Temporal's SQL-like filter over search attributes (`ExecutionStatus`, `WorkflowType`, `TaskQueue`, `StartTime`, `CloseTime`, `WorkflowId`, `ExecutionDuration`, …): `"WorkflowId STARTS_WITH 'control-temporal-sandbox' AND CloseTime > '2026-11-15T00:00:00Z'"`. [namespace](./namespace.md) `search attributes` lists them.

## Recipes with temporal.py

### list (read)

```bash
uv run ~/.agents/skills/control-temporal/scripts/temporal.py list --type "$TYPE" --status running --limit 10 \
  | jq -c '.[] | {id, status, taskQueue, start}'
```

Returns `[{id, run, type, status, taskQueue, start, close?, events?}]`, newest first. `--status` takes `running`, `completed`, `failed`, `canceled`, `terminated`, `timed_out`, `continued_as_new`; `--since` takes `30m`, `6h`, `2d`; `--query` adds a raw filter, ANDed with the others. An empty array means no match.

### count (read)

```bash
uv run ~/.agents/skills/control-temporal/scripts/temporal.py count --type "$TYPE" --since 2d --by-status
```

Returns `{"count": n, "byStatus": {"Running": n, "Completed": n, …}}`; without `--by-status`, `{"count": n}`. Takes the same filters as `list`.

### describe (read)

```bash
uv run ~/.agents/skills/control-temporal/scripts/temporal.py describe "$W" \
  | jq -c '{status, age, taskQueue, events, pendingWorkflowTask, pendingActivities: [.pendingActivities[]? | {activity, state, attempt, lastFailure: .lastFailure.message}]}'
```

Returns `{id, run, type, status, taskQueue, start, age, close?, events, historyBytes, pendingWorkflowTask?, pendingActivities?, pendingChildren?}`. A `pendingWorkflowTask.attempt` above 1, or a pending activity with `attempt` above 1 and a `lastFailure`, is a run that keeps failing in place.

### history (read)

```bash
uv run ~/.agents/skills/control-temporal/scripts/temporal.py history "$W" --last 20 \
  | jq -c '.[] | {id, e, activity, failure: .failure.message}'
```

Returns `[{id, t, e, activity?, sched?, type?, taskQueue?, signal?, cause?, retryState?, failure?, identity?, input?, result?}]`, oldest first. `e` is the event type without `EVENT_TYPE_`. `--only failures` keeps the failed and timed-out events, `--only activities` the activity events, `--only signals` the signals. `--payloads` adds the decoded `input`, `result` and `details`, each cut to `--width` characters; an S3-offloaded payload decodes to `{"$s3": {bucket, key, bytes}}`. `--all` adds the workflow-task bookkeeping events.

### result (read)

```bash
uv run ~/.agents/skills/control-temporal/scripts/temporal.py result "$W"
```

Returns `{status, close, event, result? | failure? | reason?, identity?, newRun?}` for a closed execution, or `{"status": "RUNNING", "note": …}`. A `FAILED` run's error text is in `failure.message`.

### diagnose (read)

```bash
uv run ~/.agents/skills/control-temporal/scripts/temporal.py diagnose "$W" \
  | jq -c '{status: .run.status, age: .run.age, hints, failures: [.recentFailures[]? | {e, activity, cause, failure: .failure.message}], pollers: .queue.workflow.pollers}'
```

A chain: `describe`, the last 5 failure events, and, while the run is running, its task queue's pollers. Returns `{run, recentFailures?, queue?, hints?}`; an empty key is left out. `hints` names the usual causes it detects: no worker on the queue, a nondeterminism error, an activity retrying, a workflow task failing over and over. No `hints` (`null` in the projection) on a running run means it is waiting on something it is allowed to wait on, usually a long model call or tool call: check `run.pendingActivities`.

### start (write)

```bash
uv run ~/.agents/skills/control-temporal/scripts/temporal.py start --type SandboxProbe --tq control-temporal-sandbox \
  --id "$W" --input '{"hello": 1}' --run-timeout 600s
```

Returns `{id, run, started: true}`. Each `--input` is one JSON argument. An app's own runs start through the app, which usually writes its own records too; `start` is for sandbox and one-off workflows. Read-back: `describe "$W"` shows `status: "RUNNING"` and the `taskQueue`.

### signal (write)

```bash
uv run ~/.agents/skills/control-temporal/scripts/temporal.py signal "$W" poke --input '{"hello": 2}'
```

Returns `{"signaled": "poke", "id": …}`. Read-back: `history "$W" --only signals --payloads | jq -c '.[-1] | {signal, input, identity}'` shows the signal with `identity` `control-temporal:<user>`.

### query (read)

```bash
uv run ~/.agents/skills/control-temporal/scripts/temporal.py query "$W" __stack_trace | jq -r '.result' | head -40
```

Returns `{result}` (or `{rejected}`). The worker answers, so a run whose queue has no worker hangs until the server gives up after 30 s with `HTTP 504: query timed out before a worker could process it`. `__stack_trace` is built into every SDK and shows where the workflow code is blocked: in the Python SDK, the first `Stack for <Task pending name='run …` block is the workflow's own `await`, and the threading frames below are the SDK's. Other query names are the ones the workflow's code defines.

### cancel (write)

```bash
uv run ~/.agents/skills/control-temporal/scripts/temporal.py cancel "$W" --reason "$(cat <<'EOF'
cancelled from control-temporal at the user's request
EOF
)"
```

Returns `{"cancelRequested": …}`. The workflow code decides what a cancel does: a well-behaved one cleans up and closes `CANCELED`. Read-back: `history "$W" --last 3 | jq -c '.[] | {e}'` shows `WORKFLOW_EXECUTION_CANCEL_REQUESTED`; once a worker has handled it, `result "$W"` returns `status: "CANCELED"`.

### terminate (destructive)

Preview first (prints the run, its pending activities and a `confirm` token, changes nothing):

```bash
uv run ~/.agents/skills/control-temporal/scripts/temporal.py terminate "$W" --reason "$(cat <<'EOF'
terminated from control-temporal: <why>
EOF
)"
```

Show the preview to the user. Only after their explicit yes, rerun the same command with `--confirm <token>`. Returns `{"terminated": …, "run": …}`. Read-back: `result "$W"` returns `status: "TERMINATED"` with the `reason`.

### reset (destructive)

Preview first:

```bash
uv run ~/.agents/skills/control-temporal/scripts/temporal.py reset "$W" --to last --reason "$(cat <<'EOF'
reset from control-temporal: <why>
EOF
)"
```

`--to` is `first` (replay from the start), `last` (the last completed workflow task) or an event id of a `WORKFLOW_TASK_COMPLETED`. The preview shows `toEvent` and the events it discards. Only after the user's explicit yes, rerun with `--confirm <token>`. Returns `{reset, oldRun, newRun}`. Read-back: `describe "$W"` shows the `newRun` as `run`, `RUNNING`; `result "$W" --run <oldRun>` shows the old run `TERMINATED` by identity `history-resetter`. The new run's history opens with the kept events, then a `WORKFLOW_TASK_FAILED` with cause `RESET_WORKFLOW` carrying the reason (the reset's marker, not an error), then the old run's signals sent again.

## Gotchas

- **Terminate skips the app's bookkeeping.** No workflow code runs, so whatever the workflow does on the way out (marking its record finished, releasing resources) never happens, and the app may keep showing the run as running. Prefer `cancel`; terminate only a run whose worker cannot run the cancellation (nondeterminism, no worker will ever return), and tell the user the app's own record is left as it was.
- **Cancel needs a worker.** With no worker on the queue the cancel request just waits in the history; the run closes only once a worker picks it up.
- **A nondeterminism error retries forever.** `WORKFLOW_TASK_FAILED` with cause `NON_DETERMINISTIC_ERROR` means the worker's code no longer matches the history (an activity added, removed or reordered since the Run started). The run stays `RUNNING` with a climbing `pendingWorkflowTask.attempt`. Running the old code finishes it; otherwise it is a cancel-or-terminate decision for the user, and a reset only helps if it lands before the first diverging step.
- **Reset re-sends signals.** Every signal the old run received after the reset point is delivered again to the new run, so a workflow that acts on signals acts on them again.
- A worker that shut down mid-run leaves `ACTIVITY_TASK_FAILED` events with type `WorkerShutdown`; they are the symptom of the restart, not the cause of a later failure.
