# Issues

Issues are a project's tracker and, in repos set up with the Matt Pocock skills, its spec and triage queue: the `needs-triage` / `ready-for-agent` / … labels drive who picks an issue up. GitLab calls comments "notes". An issue is addressed by its per-project `iid`.

Commands: `glab issue`, `glab label`, `glab api projects/:id/issues/:iid/links`, `scripts/gitlab.py linked-issues`.

## Operations

- `list` (read): issues filtered by state, label, assignee or search text.
- `view` (read): one issue's fields and a cut of its description.
- `comments` (read): the last human comments.
- `create` (write): a new issue.
- `comment` (write): add a note.
- `edit` (write): title or description.
- `append to section` (write): add a line at the end of one `## ` section of the description.
- `assign` / `unassign` (write).
- `links` (read): issues linked to an issue, with blockers and whether each is takeable.
- `link` (write): link two issues.
- `blocked by` (write): mark an issue blocked by others.
- `labels` (write): add and remove labels.
- `close` / `reopen` (write).
- `delete` (destructive).

## Finding things

- `N` from a title: `list` with `--search "<words>"`; from a URL, the last path segment (`/-/issues/42` or `/-/work_items/42` → `42`).
- A user for `assign`: their username, or `@me` for yourself.
- Labels that exist in the project: `glab label list -R "$P" -P 100 -F json --jq '[.[].name]'`.

## Recipes with glab

### list (read)

```bash
glab issue list -R "$P" -P 20 -O json --jq '[.[] | {iid,title,state,labels,assignee:.assignee.username}]'
```

Add filters as needed: `--label ready-for-agent`, `--assignee @me`, `--search "words"`, `--closed` or `--all` (default is open only). Returns `[{assignee,iid,labels,state,title}]`.

### view (read)

```bash
glab issue view "$N" -R "$P" -F json --jq '{iid,title,state,labels,assignees:[.assignees[].username],author:.author.username,description:(.description // "" | .[:800]),notes:.user_notes_count,web_url}'
```

### comments (read)

```bash
glab issue view "$N" -R "$P" -c -F json --jq '[.Notes[] | select(.system|not) | {by:.author.username,at:.created_at,body:(.body[:300])}] | .[-5:]'
```

The last five human notes, oldest first; `system` notes (label changes, mentions) are dropped.

### create (write)

```bash
glab issue create -R "$P" -t "Title" -d "$(cat <<'EOF'
Body in markdown.
EOF
)" -l needs-triage -y
```

Prints the new issue's URL last; its last path segment is `N`. Read-back: `view` shows the title, labels and `state: "opened"`.

### comment (write)

```bash
glab issue note "$N" -R "$P" -m "$(cat <<'EOF'
Comment in markdown. `code`, $vars and "quotes" stay literal.
EOF
)"
```

Keep the quoted heredoc for any markdown: inside `-m "..."`, backticks run as commands and `$x` expands. Prints the note's URL. Read-back: `comments` ends with the new body.

### edit (write)

```bash
glab issue update "$N" -R "$P" -d "$(cat <<'EOF'
New description in markdown.
EOF
)"
```

`-t "New title"` changes the title. `-d` replaces the whole description: read it with `view` first and send the edited text. Read-back: `view`. To add one line to a section, use `append to section` instead.

### append to section (write)

```bash
uv run ~/.agents/skills/control-gitlab/scripts/gitlab.py append-to-section -p "$P" -i "$N" --section "Decisions so far" --text "- [Title](url): gist"
```

Adds `--text` after the last non-blank line under `## <section>`, before the next `## ` heading; everything else is kept byte for byte. Exits 1 if the heading is missing. Read-back: `glab issue view "$N" -R "$P" -F json --jq .description | sed -n '/^## Decisions so far/,/^## /p'`.

### assign / unassign (write)

```bash
glab issue update "$N" -R "$P" -a @me
```

`-a <username>` assigns someone else; `--unassign` clears all. Read-back: `glab issue view "$N" -R "$P" -F json --jq '[.assignees[].username]'`.

### links (read)

```bash
uv run ~/.agents/skills/control-gitlab/scripts/gitlab.py linked-issues -p "$P" -i "$N"
```

Add `--label-prefix wayfinder:` to keep only issues with such a label. Returns `[{iid,title,state,labels,assignees,blocked_by:[{iid,state}],takeable}]`, sorted by iid. `blocked_by` comes from the `Blocked by:` line (see `blocked by`); `takeable` is open, unassigned, and every blocker closed. Raw links without the blocker check: `glab api --hostname "$H" "projects/$ID/issues/$N/links" | jq -c '[.[] | {iid,title,state,link_type}]'`.

### link (write)

Link `$N` to `$TARGET`, both in this project:

```bash
glab api -X POST --hostname "$H" "projects/$ID/issues/$N/links" -f target_project_id="$ID" -f target_issue_iid="$TARGET" -f link_type=relates_to | jq -c '{src:.source_issue.iid,tgt:.target_issue.iid,link_type}'
```

At creation, add `--linked-issues "$TARGET" --link-type relates_to` to `create` instead. Read-back: `links` on `$TARGET` lists `$N`.

### blocked by (write)

GitLab CE has no native blocking links. An issue is blocked by the issues on a `Blocked by: #<n>, #<n>` line at the top of its description. Set it while keeping the rest of the description (`BLOCKERS="#12, #13"`):

```bash
REST=$(glab issue view "$N" -R "$P" -F json --jq '.description // ""' | sed '/^Blocked by:/d' | sed '/./,$!d')
glab issue update "$N" -R "$P" -d "$(printf 'Blocked by: %s\n\n%s' "$BLOCKERS" "$REST")"
```

Read-back: `links` on the parent shows the blockers in `blocked_by`, or `view` shows the line.

### labels (write)

```bash
glab issue update "$N" -R "$P" -l ready-for-agent -u needs-triage
```

`-l` adds and `-u` removes; other labels stay. Read-back: `glab issue view "$N" -R "$P" -F json --jq .labels`.

### close / reopen (write)

```bash
glab issue close "$N" -R "$P"     # or: glab issue reopen "$N" -R "$P"
```

`close` takes no comment: post the reason with `comment` first. Read-back: `glab issue view "$N" -R "$P" -F json --jq .state` is `closed` / `opened`.

### delete (destructive)

Preview and show it to the user: `view` plus the comment count. After their explicit yes:

```bash
glab issue delete "$N" -R "$P"
```

Needs Owner on the project. Read-back: `glab issue view "$N" -R "$P"` fails with `404`. Prefer `close`: it keeps history.

## Gotchas

- `glab issue list` takes `-O json`; its `-F` means `details|ids|urls`. Every other command here uses `-F json`.
- Open is `"opened"` in JSON, not `"open"`.
- glab 1.108 on GitLab 18 prints issue URLs as `/-/work_items/<iid>`; the iid is the same.
- Native blocking (`link_type=is_blocked_by`, the `/blocked_by` quick action) is Premium: the API answers `400 link_type does not have a valid value`, and the quick action is silently ignored. Use `blocked by`.
- Child issues (an issue under an issue) are Premium too. A parent/child relation here is a `relates_to` link plus a `Part of #<parent>` line in the child's description.
- `glab label create -R "$P" --name <l> --color "#hex"` adds a missing label; labels are per project here, so a new project starts without the triage vocabulary.
