# Observations

An observation is one step an app recorded: a span, an LLM generation, a tool call, a retrieval. In Langfuse v4 there is no separate trace object: a **trace** is every observation sharing a `traceId`, and its name, tags, user and session are copied onto each observation. Reads go through Observations API v2 (row-level) and Metrics API v2 (aggregates); both are real-time. Traces are written only by apps over OpenTelemetry; this skill can send a test trace into the sandbox.

Commands: `langfuse api observations list`, `langfuse api metrics get`, `langfuse api traces delete`, `langfuse.py trace`, `langfuse.py send-trace`.

## Operations

- `recent traces` (read): root observations in a time window, one per trace.
- `find errors` (read): observations at level `ERROR` (or `WARNING`).
- `show trace` (read): one trace as an indented tree with timings, models, cost and scores.
- `observation in full` (read): one observation's input, output and metadata, into a file.
- `search with a filter` (read): observations matching tags, cost, latency, model, prompt, metadata.
- `metrics` (read): counts, cost, tokens, latency percentiles grouped by model, trace name, level, day.
- `send test trace` (write): a span + generation trace in environment `control-sandbox`.
- `delete trace` (destructive): remove a trace and its observations.

## Finding things

- `FROM` and `TO`: ISO 8601 UTC bounds, required for every listing and metric: `FROM=$(date -u -d '-1 day' +%FT%TZ); TO=$(date -u +%FT%TZ)` (on macOS, `FROM=$(date -u -v-1d +%FT%TZ)`). Results come newest first.
- `T`: a trace id (32 hex). From a UI link (`.../traces/<T>`), from `recent traces` or `find errors` (`traceId`), or from an app's log line.
- `O`: an observation id (16 hex), from `show trace` (`id`).
- `F`: a JSON array of filter conditions `{"type","column","operator","value"}` (plus `"key"` for `metadata`), the same columns and operators as the UI filter bar. Examples:
  - by tag: `F='[{"type":"arrayOptions","column":"tags","operator":"any of","value":["control-sandbox"]}]'`
  - slow generations: `F='[{"type":"stringOptions","column":"type","operator":"any of","value":["GENERATION"]},{"type":"number","column":"latency","operator":">","value":5}]'`
  - costly calls: `F='[{"type":"number","column":"totalCost","operator":">","value":0.01}]'`
  - by prompt: `F='[{"type":"stringOptions","column":"promptName","operator":"any of","value":["control-sandbox"]}]'`
  - by metadata key: `F='[{"type":"stringObject","column":"metadata","key":"tenant","operator":"=","value":"acme"}]'`
  - text in input/output: `operator` `matches` (full-text) or `=`; `contains` is rejected on those columns.
- Fixed flags cover the common cases without `F`: `--trace-id`, `--name`, `--type`, `--level`, `--user-id`, `--session-id`, `--environment` (repeatable), `--is-root-observation`.

## Recipes with langfuse

### recent traces (read)

```bash
$LF api observations list --is-root-observation --from-start-time "$FROM" --to-start-time "$TO" --limit 20 \
  --fields core,basic,trace_context \
  | jq '[.data[] | {traceId, name, start: .startTime, env: .environment, level, user: .userId, session: .sessionId, tags}]'
```

Returns `[{traceId, name, start, env, level, user, session, tags}]`, newest first. Add `--environment production` (or any env) to narrow. A trace whose root span lives in another project or service has no root here; group `--fields core,basic` rows by `traceId` instead.

### find errors (read)

```bash
$LF api observations list --level ERROR --from-start-time "$FROM" --to-start-time "$TO" --limit 20 \
  --fields core,basic,trace_context \
  | jq '[.data[] | {traceId, id, type, name, traceName, start: .startTime, status: (.statusMessage // "" | .[:200])}]'
```

Returns `[{traceId, id, type, name, traceName, start, status}]`. `status` is the recorded error message, cut to 200 chars. Follow up with `show trace` on a `traceId`.

### show trace (read)

```bash
uv run -q "$LFPY" trace "$T"
```

Returns `{trace_id, name, environment, user, session, tags, url, observations: [{depth, id, type, name, level, start, ms, status?, model?, tokens?, cost?}], scores: [{name, value, source}]}`, observations in tree order (`depth` 0 is the root). `--io 300` adds `input`/`output` cut to 300 chars each. An empty `observations` with a `note` means the id is wrong, belongs to another project, or never arrived.

### observation in full (read)

```bash
$LF api observations list --fields core,basic,io,metadata,model,usage --limit 1 \
  --filter "$(jq -nc --arg id "$O" '[{type:"string",column:"id",operator:"=",value:$id}]')" \
  | jq '.data[0]' > "/tmp/obs-$O.json"
jq '{name, type, model, input: (.input // "" | .[:500]), output: (.output // "" | .[:500]), metadata}' "/tmp/obs-$O.json"
```

The first command writes the whole observation to `/tmp/obs-$O.json`; the second shows it cut to 500 chars per side. `input`/`output` are strings; when they hold JSON, `jq -r .input "/tmp/obs-$O.json" | jq .` parses one. There is no get-by-id route in v2: the `id` filter is the lookup. Metadata values are cut at 200 chars unless named in `--expand-metadata key1,key2`.

### search with a filter (read)

```bash
$LF api observations list --filter "$F" --from-start-time "$FROM" --to-start-time "$TO" --limit 20 \
  --fields core,basic,model,usage,metrics,trace_context \
  | jq '[.data[] | {traceId, id, type, name, model, latency, totalCost, totalUsage, start: .startTime}]'
```

Returns `[{traceId, id, type, name, model, latency, totalCost, totalUsage, start}]`. `latency` is in seconds and `null` until the observation has ended. More than 20 matches: thread `.meta.cursor` into `--cursor`, or count them with `metrics` instead.

### metrics (read)

```bash
Q=$(jq -nc --arg from "$FROM" --arg to "$TO" '{view:"observations",
  metrics:[{measure:"count",aggregation:"count"},{measure:"totalCost",aggregation:"sum"},{measure:"totalTokens",aggregation:"sum"},{measure:"latency",aggregation:"p95"}],
  dimensions:[{field:"providedModelName"}], fromTimestamp:$from, toTimestamp:$to}')
$LF api metrics get --query "$Q" | jq '.data'
```

Returns one row per dimension value: `[{providedModelName, count_count, sum_totalCost, sum_totalTokens, p95_latency}]` (keys are `<aggregation>_<measure>`). Swap the dimension for `traceName`, `environment`, `level`, `name` or `promptName`; add `timeDimension:{granularity:"day"}` for a time series (`time_dimension` per row); add `filters` (same condition shape as `F`). Views: `observations`, `scores-numeric`, `scores-categorical`; score aggregates live in [scores](./scores.md).

### send test trace (write)

```bash
uv run -q "$LFPY" send-trace
```

Returns `{trace_id, environment, url}`; the trace lands in environment `control-sandbox` with tag `control-sandbox`. `--name` and `--environment` change where it lands; keep the environment `control-sandbox` unless the user asked otherwise. `--error` marks the generation `ERROR` with a status message, for testing `find errors` or alerting. Use it to confirm ingestion works end to end. Read-back: `uv run -q "$LFPY" trace <trace_id>` shows a `SPAN` at depth 0 and a `GENERATION` `fake-llm` at depth 1 with `model: gpt-4o-mini`.

### delete trace (destructive)

Preview first and show it to the user: `uv run -q "$LFPY" trace "$T" | jq '{name, environment, url, observations: (.observations | length), scores: (.scores | length)}'`. Only after their explicit yes:

```bash
$LF api traces delete "$T"
```

Returns `{"message":"Trace deleted successfully"}` whether or not the trace existed. Deletion is asynchronous (seconds in the proof run). Read-back: `$LF api observations list --trace-id "$T" --limit 1 | jq '.data | length'` reaches `0`; retry for a few minutes before calling it failed. Several at once: `$LF api traces delete-many --body-json "$(jq -nc --args '{traceIds:$ARGS.positional}' "$T1" "$T2")"`.

## Gotchas

- `--filter` combines with the fixed flags (`--from-start-time`, `--level`, …) on this server: rows must satisfy all of them, despite the API docs saying `filter` takes precedence.
- `isRootObservation` assumes one exported root per trace; traces whose root span lives in another service do not show up in `recent traces`.
- Field groups you leave out are absent, not `null`. `inputPrice`/`outputPrice`/`totalPrice` come back as strings.
- Re-sending an observation id duplicates it rather than updating it; duplicated rows inflate `metrics` counts.
