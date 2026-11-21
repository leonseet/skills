# Schedules

A schedule is a server-side timer that starts a workflow on a cron or interval spec, with its own id, pause state and notes. Schedules are how a recurring job (a nightly eval, a cleanup) would run without a cron host.

Commands: `temporal.py schedule list`, `schedule show`, `schedule create`, `schedule pause`, `schedule unpause`, `schedule trigger`, `schedule delete`; API `/api/v1/namespaces/:ns/schedules`, `/schedules/:id`, `/schedules/:id/patch`.

## Operations

- `list` (read): the schedules in the namespace.
- `show` (read): one schedule's spec, action, state, recent and next actions.
- `create` (write): a new schedule, paused unless `--active`.
- `pause` (write): stop it starting workflows.
- `unpause` (write): resume it.
- `trigger` (write): start its workflow once, now.
- `delete` (destructive): remove the schedule.

## Finding things

- `SID`: the schedule id, from `list` (`.[].id`). Sandbox schedules are named `control-temporal-sandbox-*`.
- The workflow type and queue a schedule starts are in `show` (`.workflow`).

## Recipes with temporal.py

### list (read)

```bash
uv run ~/.agents/skills/control-temporal/scripts/temporal.py schedule list --limit 50 \
  | jq -c '.[] | {id, paused, workflowType, next}'
```

Returns `[{id, paused, workflowType, notes?, recent?, next?}]`; `[]` when there are none.

### show (read)

```bash
uv run ~/.agents/skills/control-temporal/scripts/temporal.py schedule show "$SID"
```

Returns `{id, paused, notes?, cron, intervals?, workflow: {type, id, taskQueue, input?}, actions, running?, recent?, next?, updated?}`. `cron` is a list of 5-field strings, rebuilt from the calendar spec the server stores a cron string as. `actions` counts the workflows it has started; `recent` lists the last five with their status.

### create (write)

```bash
uv run ~/.agents/skills/control-temporal/scripts/temporal.py schedule create "$SID" --cron '0 2 * * *' \
  --type SandboxProbe --tq control-temporal-sandbox --input '{"hello": 1}' --run-timeout 600s --notes "$(cat <<'EOF'
sandbox schedule from control-temporal
EOF
)"
```

Returns `{"created": …, "paused": true}`. Cron runs in UTC. `--run-timeout` bounds each started run (default 600 s); raise it for a real job. The started workflow's id is `--workflow-id` (default `<SID>-wf`) plus a timestamp the server appends. Read-back: `schedule show "$SID" | jq -c '{paused, cron, workflow, next}'` returns the spec, `paused: true` and the next fire times.

### pause (write)

```bash
uv run ~/.agents/skills/control-temporal/scripts/temporal.py schedule pause "$SID" --note "$(cat <<'EOF'
paused from control-temporal at the user's request
EOF
)"
```

Returns `{"paused": …}`. Read-back: `schedule show "$SID" | jq -c '{paused, notes}'` returns `paused: true` and the note.

### unpause (write)

```bash
uv run ~/.agents/skills/control-temporal/scripts/temporal.py schedule unpause "$SID"
```

Returns `{"unpaused": …}`. Read-back: `schedule show "$SID" | jq -c '{paused, next}'` returns `paused: false` and the `next` fire times.

### trigger (write)

```bash
uv run ~/.agents/skills/control-temporal/scripts/temporal.py schedule trigger "$SID"
```

Returns `{"triggered": …}`; it fires even while paused. Read-back: a few seconds later, `schedule show "$SID" | jq -c '{actions, recent}'` shows `actions` up by one and the new workflow id in `recent`; that workflow is in [workflows](./workflows.md) `describe`.

### delete (destructive)

Preview first (prints the schedule and a `confirm` token, changes nothing):

```bash
uv run ~/.agents/skills/control-temporal/scripts/temporal.py schedule delete "$SID"
```

Show the preview to the user. Only after their explicit yes, rerun with `--confirm <token>`. Returns `{"deleted": …}`. Read-back: `schedule show "$SID"` fails with `HTTP 404`. Workflows the schedule already started keep running.

## Gotchas

- A schedule's workflows run only if a worker polls its `taskQueue`; a schedule pointed at a queue nobody serves piles up runs that time out.
- `trigger` and `recent` lag by a second or two: read back after a short wait.
- `create` fails with `HTTP 409: schedule "<id>" is already registered` when the id exists; pick another id or delete the old schedule first.
