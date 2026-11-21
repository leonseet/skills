# Datasets

A dataset is a named set of test cases (**items**: `input`, optional `expectedOutput` and `metadata`) used to evaluate an app. An item can point back at the trace it came from (`sourceTraceId`). An **experiment** is one run of an app over a dataset: each item's run is an **experiment item** with its own trace, output and evaluator scores. Experiments are produced by app code through the Python SDK (`dataset.run_experiment(...)` or `langfuse.run_experiment(...)`); this skill reads them. In the API an experiment's `name` is the SDK's `run_name`.

Commands: `langfuse api datasets list|get|create`, `langfuse api dataset-items list|get|create|delete`, `langfuse api experiments list`, `langfuse api experiment-items list`.

## Operations

- `list datasets` (read): every dataset with its id.
- `show dataset` (read): one dataset's description, metadata and schemas.
- `list items` (read): a dataset's items, input and expected output cut short.
- `export items` (read): every item of a dataset into a JSON file.
- `create dataset` (write): a new, empty dataset.
- `add item` (write): one item, optionally linked to its source trace.
- `archive item` (write): set an item `ARCHIVED` (skipped by experiments) or back to `ACTIVE`.
- `delete item` (destructive): remove an item and its experiment items.
- `list experiments` (read): runs over datasets, newest activity first.
- `experiment results` (read): one run's items with output, expected output and scores.

## Finding things

- `D`: dataset name, from `list datasets` (`control-sandbox`).
- `DID`: dataset id (`cmw...`), from `list datasets`; experiments filter by id, not name.
- `I`: item id (UUID), from `list items` (active items only) or the `id` an `add item` returned.
- `E`: experiment id (16 hex), from `list experiments`.
- `FROM`: ISO 8601 UTC lower bound, required for experiment reads: `FROM=$(date -u -d '-7 days' +%FT%TZ)` (on macOS, `date -u -v-7d +%FT%TZ`).
- `FILE`: a local path for item JSON, e.g. `FILE=/tmp/item.json`.
- `T`: a trace id, when adding an item from a trace (see [observations](./observations.md)).

## Recipes with langfuse

### list datasets (read)

```bash
$LF api datasets list --limit 50 | jq '{total: .meta.totalItems, datasets: [.data[] | {name, id, description, updated: .updatedAt}]}'
```

Returns `{total, datasets: [{name, id, description, updated}]}`. Past 50, page with `--page 2`.

### show dataset (read)

```bash
$LF api datasets get "$D" | jq '{name, id, description, metadata, inputSchema, expectedOutputSchema, created: .createdAt}'
```

Returns the dataset's fields; schemas are `null` unless set, and when set, items that do not match are rejected.

### list items (read)

```bash
$LF api dataset-items list --dataset-name "$D" --limit 20 \
  | jq '{total: .meta.totalItems, items: [.data[] | {id, status, input: (.input | tojson | .[:200]), expected: (.expectedOutput | tojson | .[:200]), sourceTraceId}]}'
```

Returns `{total, items: [{id, status, input, expected, sourceTraceId}]}` with input and expected output as JSON text cut to 200 chars. `ARCHIVED` items are left out of the list (and of `total`); fetch one by id with `$LF api dataset-items get "$I"`. `--source-trace-id "$T"` finds the items made from one trace.

### export items (read)

```bash
$LF api dataset-items list --dataset-name "$D" --limit 100 --all --max-items 5000 > "/tmp/dataset-$D.json"
jq '.meta' "/tmp/dataset-$D.json"
```

Writes `{data: [...], meta}` to `/tmp/dataset-$D.json`; `meta` is `{pages, fetchedItems, totalItems, truncated}`. `truncated: true` means the cap cut it: raise `--max-items`. Archived items are not exported.

### create dataset (write)

```bash
$LF api datasets create --body-json "$(jq -nc --arg n "$D" '{name: $n, description: "what it tests", metadata: {}}')" | jq '{name, id}'
```

Returns `{name, id}`. Read-back: `show dataset`.

### add item (write)

Write the item to `$FILE` first (quoted heredoc, so text with backticks or `$` stays literal):

```bash
cat > "$FILE" <<'EOF'
{"input": {"question": "ping"}, "expectedOutput": "pong", "metadata": {"source": "manual"}}
EOF
jq --arg d "$D" '. + {datasetName: $d}' "$FILE" | $LF api dataset-items create --body-file - | jq '{id, status, datasetName}'
```

Returns `{id, status: "ACTIVE", datasetName}`. From a trace: add `sourceTraceId` (and `sourceObservationId`) to the JSON, and take `input` from the trace's root observation (`observation in full` in [observations](./observations.md)). Read-back: `$LF api dataset-items get "$I" | jq '{id, status, input, expectedOutput}'` with the returned id.

### archive item (write)

```bash
$LF api dataset-items create --body-json "$(jq -nc --arg d "$D" --arg i "$I" '{datasetName: $d, id: $i, status: "ARCHIVED"}')" | jq '{id, status}'
```

Returns `{id, status: "ARCHIVED"}`. Creating with an existing `id` updates only the fields you send, so this is also how to edit an item's `input`, `expectedOutput` or `metadata`. `"ACTIVE"` restores it. Read-back: `$LF api dataset-items get "$I" | jq '{id, status}'`.

### delete item (destructive)

Preview first and show it to the user: `$LF api dataset-items get "$I" | jq '{id, datasetName, status, input, expectedOutput}'`. Prefer `archive item` when the user wants it out of experiments but kept. Only after their explicit yes:

```bash
$LF api dataset-items delete "$I"
```

Read-back: `$LF api dataset-items get "$I"` exits 5 with a not-found body. Deleting a whole dataset is UI-only.

### list experiments (read)

```bash
$LF api experiments list --from-start-time "$FROM" --limit 20 --fields core,scores \
  | jq '[.data[] | {id, name, datasetId, items: .itemCount, start: .startTime, scores: [.scores[]? | {name, value}]}]'
```

Returns `[{id, name, datasetId, items, start, scores}]`; `scores` here are run-level (from run evaluators), often empty. Narrow with `--dataset-id "$DID"` or `--name <run name>`.

### experiment results (read)

```bash
$LF api experiment-items list --from-start-time "$FROM" --experiment-id "$E" --limit 50 --fields core,io,scores \
  | jq '[.data[] | {item: .experimentItemId, traceId, level, output: (.output // "" | .[:200]), expected: (.expectedOutput | tojson | .[:200]), scores: [.scores[]? | {name, value}]}]'
```

Returns one row per item: `[{item, traceId, level, output, expected, scores: [{name, value}]}]`. `traceId` opens the run's trace with `show trace`. Compare two runs by running it for each `E` and joining on `item`.

## Gotchas

- Experiment reads require `--from-start-time`; without it they fail with a usage error.
- SDK experiments trace into environment `sdk-experiment` whatever environment the client was given; filter observations on that, not your app's environment.
- Item and experiment lists can lag new writes by up to ~10 minutes (seconds, typically).
