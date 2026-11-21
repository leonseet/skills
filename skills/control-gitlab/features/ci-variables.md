# CI/CD variables

CI/CD variables give pipelines their configuration and secrets: Portainer keys, S3 keys and the like, set per project or per group. Their values are secrets. They never appear in your output, files, commits or messages, and every recipe here is written so they don't: listings drop `.value`, checks compare without printing, and new values go in on stdin.

Commands: `glab variable`.

## Operations

- `list` (read): keys and flags, never values.
- `check a value` (read): does a variable hold the value the user expects?
- `set` (write): create a variable.
- `update` (write): change a variable's value or flags.
- `group list` (read): a group's keys.
- `delete` (destructive).

## Finding things

- `KEY`: from `list`.
- A value the user provides goes into a file or stdin, never into the command line, where shell history and process listings keep it.

## Recipes with glab

### list (read)

```bash
glab variable list -R "$P" -F json --jq '[.[] | {key,masked,protected,hidden,environment_scope,variable_type}]'
```

The raw JSON includes every `value`. Keep the projection.

### check a value (read)

```bash
[ "$(glab variable get "$KEY" -R "$P" -F json --jq .value | shasum -a 256)" = "$(printf '%s\n' "$(cat "$VALUE_FILE")" | shasum -a 256)" ] && echo match || echo differ
```

Prints only `match` or `differ`. To check that it is set at all: `glab variable get "$KEY" -R "$P" -F json --jq '{key,set:(.value|length>0)}'`. Print a value only when the user explicitly asks to see it, and only in the conversation.

### set (write)

```bash
glab variable set "$KEY" -R "$P" --masked --description "what it is for" < "$VALUE_FILE"
```

Add `--protected` when only protected branches and tags may read it, `-s <env>` for an environment scope, `-t file` for a file variable. Prints `✓ Created variable <KEY> …`. Read-back: `list` shows the key and flags, and `check a value` prints `match`.

### update (write)

```bash
glab variable update "$KEY" -R "$P" --masked < "$VALUE_FILE"
```

Read-back: `check a value` prints `match`.

### group list (read)

```bash
GITLAB_HOST="$H" glab variable list -g "$GROUP" -F json --jq '[.[] | {key,masked,protected,environment_scope}]'
```

Needs Owner on the group; Maintainer gets `403`. Proven only as far as the `403`: the proving account had no group Owner.

### delete (destructive)

Preview: `list` filtered to `$KEY`, plus where it is used (`grep -rn "$KEY" .gitlab-ci.yml` in a clone). Show it to the user. After their explicit yes:

```bash
glab variable delete "$KEY" -R "$P"
```

Read-back: `list` no longer has the key. Pipelines that read it get an empty string, not an error.

## Gotchas

- `-g <group>` is ignored when `-R` is also given: you get the project's variables. Use `GITLAB_HOST="$H"` with `-g` and no `-R`.
- Masking needs a value of 8+ characters from a limited set; GitLab rejects `--masked` otherwise.
- `glab variable export` prints every value; leave it out.
