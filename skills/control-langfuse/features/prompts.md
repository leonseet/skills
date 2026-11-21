# Prompts

A prompt is a named, versioned template that apps fetch at runtime instead of hard-coding it. Every change is a new immutable version (1, 2, 3…); **labels** point at versions, and apps fetch by label, `production` by default. `latest` moves to the newest version automatically. A prompt is `text` (one string) or `chat` (an array of `{role, content}` messages, plus `{type: "placeholder", name}` slots); `{{var}}` marks a variable either way. `config` holds JSON settings such as model and temperature, carried per version.

Commands: `langfuse api prompts list|get|create|update-version|delete`, `langfuse.py prompt-push`.

## Operations

- `list` (read): every prompt with its versions, labels and type.
- `show` (read): one version's body, labels and config.
- `pull to file` (read): a version's body into a file, for reading or editing.
- `diff versions` (read): body and config differences between two versions.
- `create` (write): a new prompt, version 1.
- `new version from file` (write): the edited body as the next version, same type, config and tags.
- `promote` (write): put a label (`production`, `staging`) on a version.
- `delete version` (destructive): remove one version, or the whole prompt.

## Finding things

- `P`: prompt name, exactly as `list` prints it (`control-sandbox`). Names may contain `/` for folders.
- `V`, `V1`, `V2`: version numbers, from `list` (`versions`) or `show` (`version`).
- `L`: a label, `production` unless the user names another.
- `FILE`: a local path for the body, e.g. `FILE=/tmp/prompt.txt` (text) or `/tmp/prompt.json` (chat).

## Recipes with langfuse

### list (read)

```bash
$LF api prompts list --limit 50 | jq '{total: .meta.totalItems, prompts: [.data[] | {name, type, versions, labels, tags, updated: .lastUpdatedAt}]}'
```

Returns `{total, prompts: [{name, type, versions: [1,2], labels, tags, updated}]}`; `labels` is the union across versions. Narrow with `--name "$P"`, `--label production` or `--tag <tag>`; past 50, page with `--page 2`.

### show (read)

```bash
$LF api prompts get "$P" --label "$L" | jq '{name, version, type, labels, config, tags, commitMessage, prompt}'
```

Returns `{name, version, type, labels, config, tags, commitMessage, prompt}`; `prompt` is a string or a message array. `--version "$V"` instead of `--label` picks a version; `--label latest` the newest. `--no-resolve` shows composed-prompt references (`@@@langfusePrompt:name=…@@@`) unexpanded.

### pull to file (read)

```bash
$LF api prompts get "$P" --label latest | jq -r '.prompt | if type == "string" then . else tojson end' > "$FILE"
```

A text prompt lands as plain text; a chat prompt as one-line JSON (`jq . "$FILE"` to view it). Edit the file with your editor tool, then `new version from file`.

### diff versions (read)

```bash
diff <($LF api prompts get "$P" --version "$V1" | jq -r '(.config | tojson), (.prompt | if type == "string" then . else .[] | tojson end)') \
     <($LF api prompts get "$P" --version "$V2" | jq -r '(.config | tojson), (.prompt | if type == "string" then . else .[] | tojson end)')
```

Standard `diff` output (exit 1 when they differ); the first line is `config`, chat messages one per line. No output and exit 0 means identical.

### create (write)

Write the body to `$FILE` first (a quoted heredoc keeps `{{var}}` and backticks literal):

```bash
cat > "$FILE" <<'EOF'
Answer {{question}} in one sentence.
EOF
jq -n --arg n "$P" --rawfile t "$FILE" '{name: $n, type: "text", prompt: ($t | rtrimstr("\n")), labels: [], config: {}, commitMessage: "first version"}' \
  | $LF api prompts create --body-file - | jq '{name, version, labels}'
```

Returns `{name, version: 1, labels: ["latest"]}`. For a chat prompt, `$FILE` holds a JSON message array and the filter is `jq -n --arg n "$P" --slurpfile m "$FILE" '{name: $n, type: "chat", prompt: $m[0], labels: []}'`. Leave `labels` empty until the user asks to promote: `production` makes apps serve it. Creating with an existing name adds a version instead. Read-back: `show` with `--label latest`; `version` and `prompt` match.

### new version from file (write)

```bash
uv run -q "$LFPY" prompt-push --name "$P" --file "$FILE" --message "what changed"
```

Returns `{name, version, previous, labels}`. It copies type, config and tags from the latest version, drops trailing newlines from a text body, and gives the new one no label beyond `latest`; add `--label staging` (repeatable) to label it in the same step. Read-back: `diff versions` with `V1=previous`, `V2=version` shows exactly the edit.

### promote (write)

```bash
$LF api prompts update-version "$P" "$V" --body-json "$(jq -nc --arg l "$L" '{newLabels: [$l]}')" | jq '{version, labels}'
```

Returns `{version, labels}`; `newLabels` is added to the version's existing labels, and a label moves off whichever version held it. Read-back: `$LF api prompts get "$P" --label "$L" | jq '{version, labels}'` shows `version` = `$V`. To undo, promote the previously labelled version again.

### delete version (destructive)

Preview first and show it to the user: `$LF api prompts get "$P" --version "$V" | jq '{name, version, labels, commitMessage}'`, naming any label on it (deleting the `production` version leaves apps with nothing to fetch). Only after their explicit yes:

```bash
$LF api prompts delete "$P" --version "$V"
```

Prints nothing on success. Read-back: `$LF api prompts list --name "$P" | jq '.data[0].versions'` no longer lists `$V`. Deleting the newest version moves `latest` back to the one before it. Without `--version` (or with `--label`) it deletes every version, or every version with that label.

## Gotchas

- `get` without `--label` or `--version` means `--label production` and fails with `LangfuseNotFoundError` (exit 5) for a prompt that was never promoted. Use `--label latest`.
- Apps' SDKs cache fetched prompts (Python default 60 s) and fall back to the cached copy on errors, so a promotion reaches running apps after the cache expires.
- A prompt's `type` is fixed by version 1: a version of the other type fails with 400 `Previous versions have different prompt type`. A new type needs a new name.
- `prompt-push` needs an existing prompt; start a new one with `create`.
