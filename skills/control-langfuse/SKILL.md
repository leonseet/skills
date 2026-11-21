---
name: control-langfuse
description: "Operate a Langfuse v4 instance (the one LANGFUSE_BASE_URL names) through the langfuse CLI (@langfuse/cli) and scripts/langfuse.py on the Python SDK v5: observations and traces (debug a trace, find errors, cost and latency metrics), prompts (versions, labels, promote), datasets and experiments, scores, score configs and comments. Use whenever a task reads or changes anything in Langfuse."
---

# Control Langfuse

The Langfuse instance is the one `LANGFUSE_BASE_URL` names. This map is proven on a self-hosted Langfuse **v4** (4.75.0) in **events_only** mode. Traces arrive over OpenTelemetry, and the legacy v1 read endpoints (`/traces`, `/sessions`, `/scores`, `/observations`) answer 404. The main interface is the official CLI, `langfuse` (`@langfuse/cli`), which targets the v2/v3 endpoints v4 serves. `scripts/langfuse.py` holds `doctor` and the few chains plain commands make clumsy: the trace tree, sending a test trace (Python SDK v5, the CLI cannot emit OpenTelemetry), and pushing a prompt version from a file.

Set both variables at the start of every shell, from the repo root:

```bash
LFPY=~/.agents/skills/control-langfuse/scripts/langfuse.py
LF=$(uv run -q "$LFPY" lf)
```

`lf` prints the CLI prefix for this repo and machine: `env LANGFUSE_BASE_URL=… <CA setting for Node> langfuse [--env <repo>/.env]`.

Every recipe runs `$LF api <resource> <action>` (unquoted, so it splits into words) or `uv run -q "$LFPY" <command>`. `$LF api help <resource> <action>` lists an action's options; `uv run -q "$LFPY" <command> --help` the script's.

## Setup

A new machine needs, in this order (`doctor` checks each and prints the fix for what is missing):

1. `uv`: `curl -LsSf https://astral.sh/uv/install.sh | sh`. `doctor` itself runs on it, so this one comes first. `uv run` then installs the Python SDK `langfuse` 5.x, `truststore`, typer and python-dotenv from the script's inline dependencies, on Python ≥ 3.11 (uv fetches one if needed).
2. Node ≥ 20 and the CLI: `npm install -g @langfuse/cli@1.3.1`. The older `langfuse-cli` package (0.x) lacks the v4 endpoints: `npm uninstall -g langfuse-cli` first.
3. `LANGFUSE_BASE_URL`: the instance's URL (`https://<host>`); `LANGFUSE_HOST`, the older SDKs' name for it, is read when that one is missing. The skill carries no default. The script reads it from the current repo's `.env` (gitignored) first, then the shell. When both lack it, ask the user; they put it in the repo's `.env` when it belongs to that project, or export it in their shell's startup file (`~/.bashrc`, `~/.zshrc`) for every repo.
4. Credentials: `LANGFUSE_PUBLIC_KEY` and `LANGFUSE_SECRET_KEY`, read from the same two places. The user creates the pair in the Langfuse UI under Project settings → API Keys and writes them in themselves. `$LF` passes `--env <repo>/.env` when the file exists, and that file then wins over the shell.
5. A reachable, trusted host. `doctor` connects to the URL's host. An internal host answers only on the network or VPN that serves it. For a certificate from a private CA, two runtimes must trust it. The script (Python) trusts the OS trust store, plus the PEM file `CONTROL_CA_FILE` names. Node ignores the OS store, so `$LF` hands it one: `CONTROL_CA_FILE` when set, else the Linux system bundle, else on macOS `--use-system-ca` (Node 22.15 or newer). Without that, every CLI call fails with `fetch failed`.
6. `jq`: `sudo apt install jq` on Linux, `brew install jq` on macOS.

## Doctor

```bash
uv run -q "$LFPY" doctor
```

One `ok`/`WARN`/`FAIL` line each: Node, CLI and its version, `LANGFUSE_BASE_URL` and each credential with where it came from, the host (reachable, certificate trusted), `jq`; then host health and server version through the CLI, CLI auth (prints the project), Python SDK version and auth. Every `FAIL` has a `fix:` line under it. Run it first, and again whenever a command fails strangely.

On a `FAIL`, stop the task and walk the user through the `fix:` lines one at a time, offering to run each fix yourself; then rerun `doctor` until it is clean. Install commands and other system changes run only after the user's yes; the user enters credentials themselves, never into the chat. A `FAIL host` that says unreachable is usually a VPN that is down: say so and let the user connect. A `FAIL` with no fix you can apply is reported to the user, never worked around. A version `WARN` means a recipe may have drifted: check `$LF api help <resource> <action>` and re-prove it.

## Instances & conventions

- **One instance** per `LANGFUSE_BASE_URL`, one project per key pair: a pair sees only its own project, and `doctor` names it. Where a recipe needs the id: `PROJECT=$($LF api projects list | jq -r '.data[0].id')`.
- **Instance notes**: `~/.config/control-langfuse/instance.md`, this machine's notes on the instance `LANGFUSE_BASE_URL` names: its projects and the sandbox objects already there. Read it before the first recipe when it exists. For what it lacks, observe the instance, then ask the user, and offer to record their answer there (names and conventions, never secrets).
- **Langfuse defaults** for naming: prompt labels `production` (what apps fetch by default) and `latest` (set automatically on the newest version); environments `default` unless an app sets one.
- **Sandbox**: objects named `control-sandbox*` (prompts, datasets, score configs) and traces in environment `control-sandbox` (sent by `send-trace`), in a project the user agreed may hold test data. Tell the user which project the key pair points at before the first proof write, and prove new write recipes only on those names.
- **UI links**: `$LANGFUSE_BASE_URL/project/$PROJECT/traces/$T`; `trace` prints it.

## Safety

Every operation in `features/` is tagged:

- **read**: run freely.
- **write**: run when the user asked for that change, then run the recipe's read-back and report what it shows.
- **destructive** (delete a trace, prompt version, dataset item or score): first run the recipe's preview and show the user exactly what goes; run the delete only after their explicit yes in the conversation. Langfuse has no undo, and v4 deletes are asynchronous: the read-back can lag.

Promoting a prompt label (`update-version` with `production`) is a write, but it changes what every app fetching that prompt serves within its cache TTL. Name the effect before running it.

## Operate

Read [`features/README.md`](features/README.md): the common-task chains, then one recipe file per resource area.

## Output shaping

- `$LF api ...` prints the response body as pretty JSON; pipe it through a `jq` projection of the fields you need. `--json` wraps it in `{status, headers, body}`: use it only when you need the HTTP status.
- Observations return field groups, not whole rows: ask for only the groups you need with `--fields` (`core,basic` by default; `io` and `metadata` are the heavy ones). Input/output come back as raw strings, often JSON-encoded.
- Every listing gets an explicit `--limit`. Cursor endpoints (observations, scores, experiments) put the next page's cursor in `.meta.cursor`; `--all --max-items N` fetches pages up to a cap. Page endpoints (prompts, datasets, items, configs, comments) use `--page`, with `.meta.totalItems` telling you how many there are.
- Full input/output, prompt bodies and dataset items go into a file (`> "$FILE"`), then read the part you need.
- Exit codes: 2 usage, 3 configuration (missing keys, unreadable `--env`), 4 network, 5 HTTP error (body on stdout), 7 invalid response.

## Gotchas

- **Freshness**: observations and metrics are real-time. Every other endpoint (scores list, datasets, experiments) can lag up to ~10 minutes; a score created by the API typically shows up in `scores list` within a minute. An empty result right after a write is not proof it failed: retry the read-back before concluding.
- **Traces are observations.** There is no trace object to fetch: a trace is the set of observations sharing a `traceId`. Trace name, tags, user and session are copied onto every observation (`trace_context` and `basic` field groups).
- Writing traces via the CLI or `/api/public/ingestion` is unavailable in events_only mode. Apps must use an OpenTelemetry-based SDK: Python SDK v4+ (latest 5.x), JS/TS v5+.
- Re-ingesting the same observation id creates duplicates in v4 instead of updating.
- For SDK and integration questions outside this skill, read the docs: `https://langfuse.com/llms.txt` indexes every page, and any page is available as markdown by appending `.md` to its URL.
