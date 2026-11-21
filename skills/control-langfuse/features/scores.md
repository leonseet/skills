# Scores

A score is one evaluation attached to exactly one subject: a trace, an observation, a session or an experiment run. Scores come from evaluators (`source: EVAL`), human annotation in the UI (`ANNOTATION`) or API and SDK calls (`API`). Each has a `dataType` (`NUMERIC`, `BOOLEAN`, `CATEGORICAL`, `TEXT`, `CORRECTION`) that fixes the type of `value`. A **score config** defines a score name's type and range, so annotators and evaluators produce consistent values. **Comments** are free-text notes on a trace, observation, session or prompt. Scores are read through Scores API v3; the legacy v1/v2 score lists answer 404 here.

Commands: `langfuse api scores list|create|delete`, `langfuse api score-configs list|create|update`, `langfuse api comments list|create`, `langfuse api metrics get` (score views).

## Operations

- `list scores` (read): scores by trace, name, source or time window.
- `score aggregates` (read): average, count per score name, over time.
- `add score` (write): a score on a trace or observation.
- `delete score` (destructive): remove one score.
- `list configs` (read): score configs with type and range.
- `create config` (write): a new score config.
- `archive config` (write): hide a config from new annotations, or restore it.
- `list comments` (read): comments on one object.
- `add comment` (write): a comment on a trace, observation, session or prompt.

## Finding things

- `T`: trace id; `O`: observation id (see [observations](./observations.md)).
- `NAME`: score name, exactly as `list scores` or `list configs` prints it (`control-sandbox-quality`).
- `S`: score id (UUID), from `list scores`.
- `C`: score config id (UUID), from `list configs`.
- `FROM`, `TO`: ISO 8601 UTC bounds: `FROM=$(date -u -d '-7 days' +%FT%TZ); TO=$(date -u +%FT%TZ)` (on macOS, `FROM=$(date -u -v-7d +%FT%TZ)`).
- `PROJECT`: `$LF api projects list | jq -r '.data[0].id'`; comments need it.
- `OT`: comment object type, one of `TRACE`, `OBSERVATION`, `SESSION`, `PROMPT`; `OID`: that object's id.

## Recipes with langfuse

### list scores (read)

```bash
$LF api scores list --trace-id "$T" --limit 50 --fields details,subject \
  | jq '[.data[] | {id, name, value, dataType, source, comment, subject, at: .timestamp}]'
```

Returns `[{id, name, value, dataType, source, comment, subject: {kind, id, traceId?}, at}]`. Instead of `--trace-id`, filter with `--name "$NAME"`, `--source EVAL`, `--from-timestamp "$FROM" --to-timestamp "$TO"`, or `--data-type NUMERIC --value-max 0.5` for low scores; most filters take comma-separated lists. `--trace-id`, `--session-id` and `--experiment-id` are mutually exclusive; `--observation-id` needs `--trace-id`. Past 50, thread `.meta.cursor` into `--cursor` (max 100 per page).

### score aggregates (read)

```bash
Q=$(jq -nc --arg from "$FROM" --arg to "$TO" '{view:"scores-numeric",
  metrics:[{measure:"value",aggregation:"avg"},{measure:"count",aggregation:"count"}],
  dimensions:[{field:"name"}], fromTimestamp:$from, toTimestamp:$to}')
$LF api metrics get --query "$Q" | jq '.data'
```

Returns `[{name, avg_value, count_count}]`. Real-time, unlike `list scores`. Add `timeDimension:{granularity:"day"}` for a trend; use view `scores-categorical` (measure `count`, dimension `stringValue`) for categorical scores.

### add score (write)

```bash
$LF api scores create --body-json "$(jq -nc --arg t "$T" --arg n "$NAME" '{traceId: $t, name: $n, value: 0.9, dataType: "NUMERIC", comment: "why"}')" | jq '{id}'
```

Returns `{id}`. On an observation add `observationId`; on a session send `sessionId` instead of `traceId`; with a config send `configId` and a value in its range. Sending an existing `id` updates that score. Read-back (scores list lags, typically under a minute): `$LF api scores list --trace-id "$T" --name "$NAME" --limit 5 | jq '[.data[] | {id, value}]'` lists the returned `id`.

### delete score (destructive)

Preview first and show it to the user: `$LF api scores list --id "$S" --fields details,subject | jq '.data[0] | {id, name, value, source, subject}'`. Only after their explicit yes:

```bash
$LF api scores delete "$S"
```

Returns `{"message":"Score deletion queued successfully"}`. Read-back: `$LF api scores list --id "$S" | jq '.data | length'` reaches `0`.

### list configs (read)

```bash
$LF api score-configs list --limit 50 | jq '[.data[] | {id, name, dataType, min: .minValue, max: .maxValue, categories, archived: .isArchived}]'
```

Returns `[{id, name, dataType, min, max, categories, archived}]`.

### create config (write)

```bash
$LF api score-configs create --body-json "$(jq -nc --arg n "$NAME" '{name: $n, dataType: "NUMERIC", minValue: 0, maxValue: 1, description: "what it measures"}')" | jq '{id, name, dataType}'
```

Returns `{id, name, dataType}`. A categorical config takes `categories: [{label: "good", value: 1}, {label: "bad", value: 0}]` instead of min/max. Read-back: `$LF api score-configs get "$C" | jq '{name, dataType, minValue, maxValue, isArchived}'` with the returned id.

### archive config (write)

```bash
$LF api score-configs update "$C" --body-json '{"isArchived": true}' | jq '{id, name, isArchived}'
```

Returns `{id, name, isArchived: true}`. `false` restores it. Configs cannot be deleted; archiving is the way to retire one. Read-back: `$LF api score-configs get "$C" | jq .isArchived`.

### list comments (read)

```bash
$LF api comments list --object-type "$OT" --object-id "$OID" --limit 20 | jq '[.data[] | {id, content, author: .authorUserId, at: .createdAt}]'
```

Returns `[{id, content, author, at}]`.

### add comment (write)

```bash
$LF api comments create --body-json "$(jq -nc --arg p "$PROJECT" --arg ot "$OT" --arg oid "$OID" --arg c "$(cat <<'EOF'
Checked this trace: retrieval returned the wrong document.
EOF
)" '{projectId: $p, objectType: $ot, objectId: $oid, content: $c}')" | jq '{id}'
```

Returns `{id}`. Content is markdown, up to 5000 chars. There is no API to edit or delete a comment. Read-back: `list comments` on the same object shows the content.

## Gotchas

- `list scores` can trail new scores by up to ~10 minutes (under a minute typically); `score aggregates` is real-time.
- `scores create` is asynchronous: a `{id}` back means accepted, not stored. A value that breaks its config (out of range, unknown category) is dropped after acceptance; check the read-back.
- Scores from SDK experiments attach to the experiment item's observation (`subject.kind: "observation"`), not the trace: filter by `--trace-id` and read `subject`.
