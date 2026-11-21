---
name: control-temporal
description: "Operate a Temporal server (the one whose Web UI TEMPORAL_UI_URL names, or a local docker one) through scripts/temporal.py on the Temporal UI's HTTP API: workflows (find, describe, history, failures, why a run is stuck, result, signal, query, cancel, terminate, reset), task queues and workers (pollers, backlog), schedules, and namespace facts. Use whenever a task reads or changes anything in Temporal."
---

# Control Temporal

The Temporal server is the one whose Web UI `TEMPORAL_UI_URL` names. Every operation goes through `scripts/temporal.py`, which calls the UI's HTTP API (`/api/v1/...`).

The `temporal` CLI lost because it speaks only gRPC (port 7233), which a VPN or ingress in front of a shared server often does not route; the UI's HTTP API answers wherever the UI loads in a browser, and does reads and writes. The Python SDK is gRPC too.

## Setup

A new machine needs, in this order (`doctor` checks each and prints the fix for what is missing):

1. `uv`: `curl -LsSf https://astral.sh/uv/install.sh | sh`. The script runs on it.
2. `jq`: `sudo apt install jq` on Linux, `brew install jq` on macOS.
3. Settings, read from the current repo's `.env` first, then the shell. The skill carries no default for any of them. When one a task needs is in neither place, ask the user; they put it in the repo's `.env` when it belongs to that project, or export it in their shell's startup file (`~/.bashrc`, `~/.zshrc`) for every repo.
   - `TEMPORAL_UI_URL`: the Web UI's base URL (`https://<host>`), required. `--url` overrides it per command; `--local` is `http://localhost:8080`, a docker Temporal on this machine.
   - `TEMPORAL_NAMESPACE`: the namespace; unset means `default`. `-n` overrides it.
   - `TEMPORAL_TASK_QUEUE`: the task queue this repo's worker polls. It is the default `TQ` of the recipes; `--tq` on a command overrides it.
4. A reachable, trusted host. `doctor` calls the UI. An internal host answers only on the network or VPN that serves it. The script trusts the OS trust store (Keychain on macOS, the system bundle on Linux); for a UI whose certificate comes from a private CA the machine lacks, `CONTROL_CA_FILE` names that CA's PEM file, read like the other settings.

No credentials: the script supports a UI with auth disabled, and `doctor` fails on one that requires login. Writes need the UI's `_csrf` cookie echoed in an `X-CSRF-Token` header, which the script fetches by itself.

## Doctor

```bash
uv run ~/.agents/skills/control-temporal/scripts/temporal.py doctor
```

One `ok`/`WARN`/`FAIL` line each: uv, jq, the UI URL and where it came from, reachability and TLS, UI auth, UI version, write actions, the CSRF cookie, server version, and the namespace with its retention. UI and server versions are reported beside the ones this map was proven on. Every `FAIL` has a `fix:` line under it. Run it first, and again whenever a command fails strangely.

On a `FAIL`, stop the task and walk the user through the `fix:` lines one at a time, offering to run each fix yourself; then rerun `doctor` until it is clean. Install commands and other system changes run only after the user's yes. A `FAIL reach + tls` that says unreachable is usually a VPN that is down: say so and let the user connect. A `FAIL` with no fix you can apply is reported to the user, never worked around. A version `WARN` means a recipe may have drifted: check the command's `--help`.

## Instances & conventions

- **One server** per `TEMPORAL_UI_URL`; `info` gives its versions, namespaces and how long closed workflows are kept. A shared server carries other teams' workflows: touch only the workflows and queues the task is about.
- **Local**: `--local` targets a docker Temporal on this machine (UI `http://localhost:8080`). A run whose worker went away stays `RUNNING` there for good, so it collects stale runs.
- **Instance notes**: `~/.config/control-temporal/instance.md`, this machine's notes on the server and the apps on it: workflow types and what their ids mean, activity names, how task queues are named, where large payloads go. Read it before the first recipe when it exists. For what it lacks, read the current repo's `AGENTS.md` and worker code, then ask the user, and offer to record their answer there.
- **Task queues say who runs it**: this repo's queue is `TEMPORAL_TASK_QUEUE`; a run's own queue is `taskQueue` in `describe`.
- **Large payloads** may sit outside Temporal: with the SDK's external payload storage on, the script shows a payload as `{"$s3": {bucket, key, bytes}}`. Fetch one with `control-s3` into a file.
- **Recipe variables**: `W` workflow id, `R` run id, `TYPE` workflow type, `TQ` task queue, `SID` schedule id. Each feature's `Finding things` says how to get them.
- **Sandbox**: task queue `control-temporal-sandbox`, workflow and schedule ids `control-temporal-sandbox-*`, in a namespace the user agreed to: tell them which server and namespace the settings point at before the first proof write. No worker polls that queue, so a sandbox workflow sits until its run timeout (600 s by default) and then times out by itself.

## Safety

Every operation in `features/` is tagged:

- **read**: run freely.
- **write** (`start`, `signal`, `cancel`, schedule `create`, `pause`, `unpause`, `trigger`): run when the user asked for that change, then run the recipe's read-back.
- **destructive** (`terminate`, `reset`, schedule `delete`): the command first prints a preview and a `confirm` token and changes nothing. Show the preview to the user, and rerun with `--confirm <token>` only after their explicit yes in the conversation. The token is void once the target changes.

Runs are other people's work in progress: outside the sandbox, act only on the workflow or schedule the user named. Decoded payloads hold the apps' data and prompts; quote only the fields the task needs.

## Operate

Read [`features/README.md`](features/README.md): the common-task chains, then one recipe file per resource area.

## Output shaping

- Every command prints one compact JSON value; pipe it through the recipe's `jq` projection.
- `list` takes `--limit` (default 20) and filters (`--status`, `--type`, `--tq`, `--since`, `--query`) so the server does the narrowing.
- `history` hides workflow-task bookkeeping, keeps the last 40 events (`--last`), and decodes payloads only with `--payloads`, each cut to `--width` characters (default 300). Narrow with `--only failures|activities|signals` before raising `--last`. A whole history goes into a file: `… history "$W" --all --payloads --width 100000 --last 100000 > /tmp/history.json`.

## Gotchas

- A write that gets no answer (`got no answer`) may still have been accepted: read it back with `describe` before sending it again.
- Closed workflows vanish once the namespace's retention passes (`info` gives it), and externally stored payloads on their bucket's own expiry. An older run's story is wherever the app keeps it.
- Retried activity attempts do not add history events: a retrying activity shows in `describe` as `pendingActivities[].attempt` and `lastFailure`, not in `history`.
- Some events reference others: `ACTIVITY_TASK_*` events carry `sched`, the id of their `ACTIVITY_TASK_SCHEDULED` event, and can appear out of time order.
