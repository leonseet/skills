# Pipelines

A pipeline is one CI run of `.gitlab-ci.yml` on a ref; it holds jobs grouped in stages. Pushes, tags and MRs start pipelines. Which runners serve a project and where job images come from is the instance's own setup: read the project's `.gitlab-ci.yml`.

Commands: `glab ci`, `glab api projects/:id/pipelines`, `glab api projects/:id/jobs`, `scripts/gitlab.py failed-job-log`.

## Operations

- `list` (read): recent pipelines by ref or status.
- `view` (read): one pipeline's status and its jobs.
- `failed log` (read): each failed job with the cleaned tail of its log.
- `job log` (read): the tail of one job's log.
- `lint` (read): validate a `.gitlab-ci.yml`.
- `run` (write): start a pipeline on a ref, with variables.
- `retry job` (write).
- `cancel` (write): cancel a running pipeline.
- `play manual job` (write).
- `delete` (destructive).

## Finding things

- `PL`: the newest on a ref, `glab ci list -R "$P" -r "$REF" -P 1 -F json --jq '.[0].id'`; an MR's, from [merge-requests](./merge-requests.md) `view` (`.head_pipeline.id`); from a URL, the segment after `/-/pipelines/`.
- `J`: from `view`, by job name.

## Recipes with glab

### list (read)

```bash
glab ci list -R "$P" -P 10 -F json --jq '[.[] | {id,status,ref,source,created_at}]'
```

Filters: `-r <ref>`, `-s failed|running|success|…`, `-o desc`.

### view (read)

```bash
glab ci get -R "$P" -p "$PL" -F json --jq '{id,status,ref,sha:.sha[:8],duration,web_url,jobs:[.jobs[] | {id,name,stage,status}]}'
```

`jobs` lists only the latest try of each job; a retried job has a new id.

### failed log (read)

```bash
uv run ~/.agents/skills/control-gitlab/scripts/gitlab.py failed-job-log -p "$P" --pipeline "$PL" --lines 60
```

Without `--pipeline` it takes the newest pipeline on `--ref` (default: the default branch). Returns `{pipeline,status,ref,web_url,failed:[{id,name,stage,failure_reason,allow_failure,log_tail}]}`; `failed` is empty when nothing failed. Log lines are stripped of colours, timestamps and section markers.

### job log (read)

```bash
glab api --hostname "$H" "projects/$ID/jobs/$J/trace" | sed -E 's/\x1b\[[0-9;]*[A-Za-z]//g; s/^[0-9T:.-]+Z [0-9]+[OE]\+? ?//' | grep -v '^section_' | tail -n 60
```

For a long log, save it to a file and `grep` it for `error|fail|Traceback` before reading.

### lint (read)

```bash
glab ci lint -R "$P" .gitlab-ci.yml
```

Run inside a clone; it validates the local file against the project's CI config, includes resolved. Prints `CI/CD YAML is valid!` or the errors.

### run (write)

```bash
glab ci run -R "$P" -b "$REF" --variables KEY1:value1 --variables KEY2:value2
```

Prints `Created pipeline (id: <PL>) …`. Read-back: `view` with that id shows `created`/`pending`/`running`. Poll every 10 s until `success`, `failed` or `canceled`.

### retry job (write)

```bash
glab ci retry "$J" -R "$P"
```

Prints `Retried job (ID: <new J>) …`. Read-back: `view` shows the new job id `pending` or `running`.

### cancel (write)

```bash
glab ci cancel pipeline "$PL" -R "$P"
```

Prints `✓ Pipeline #<PL> is canceled successfully.` Read-back: `glab ci get -R "$P" -p "$PL" -F json --jq .status` is `canceled`.

### play manual job (write)

```bash
glab api -X POST --hostname "$H" "projects/$ID/jobs/$J/play" | jq '{id,name,status}'
```

Only for a job in `manual` status. Read-back: `view` shows it `pending` or `running`.

### delete (destructive)

Preview with `view` and show it to the user. After their explicit yes:

```bash
glab api -X DELETE --hostname "$H" "projects/$ID/pipelines/$PL"
```

Needs Owner. Deletes the pipeline's jobs, logs and artifacts. Read-back: `view` fails with `404`.

## Gotchas

- `glab ci view` is an interactive TUI; use `glab ci get` for JSON.
- A raw job log has a timestamp and stream id on every line and ANSI colours; `failed log` and the `job log` recipe strip them. Reading it raw wastes most of the tokens.
- Pushing a tag starts a pipeline in any project whose CI runs on tags, which may mean a deploy.
- Masked variables show as `[MASKED]` in logs; that is expected, not missing configuration.
