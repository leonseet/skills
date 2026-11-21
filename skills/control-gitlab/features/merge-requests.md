# Merge requests

A merge request (MR) proposes merging a source branch into a target branch, usually `main`, which is protected: only Maintainers merge. An MR is addressed by its per-project `iid`; many glab commands also accept the source branch name.

Commands: `glab mr`, `glab mr note`, `glab api projects/:id/merge_requests`.

## Operations

- `list` (read): MRs by state, author, label or branch.
- `view` (read): state, merge readiness, head pipeline, size.
- `comments` (read): the last human discussion notes.
- `diff` (read): a file-level summary, or one file's diff.
- `create` (write): open an MR from a pushed branch.
- `comment` (write).
- `update` (write): title, description, labels, draft/ready, reviewers.
- `approve` / `revoke` (write).
- `merge` (write).
- `close` / `reopen` (write).
- `delete` (destructive).

## Finding things

- `M` from a branch: `glab mr list -R "$P" -s <branch> -F json --jq '.[0].iid'`; from a URL, the segment after `/-/merge_requests/`.
- An MR's head pipeline: `view` returns its status; its id is `.head_pipeline.id` for [pipelines](./pipelines.md).

## Recipes with glab

### list (read)

```bash
glab mr list -R "$P" -P 20 -F json --jq '[.[] | {iid,title,state,source_branch,author:.author.username,draft}]'
```

Default is open MRs. Filters: `--all`, `--merged`, `--closed`, `--author @me`, `--reviewer @me`, `-l <label>`, `-s <source-branch>`, `-t <target-branch>`.

### view (read)

```bash
glab mr view "$M" -R "$P" -F json --jq '{iid,title,state,draft,source_branch,target_branch,detailed_merge_status,has_conflicts,pipeline:.head_pipeline.status,changes_count,labels,reviewers:[.reviewers[].username],description:(.description // "" | .[:600]),web_url}'
```

`detailed_merge_status` says why an MR can't merge: `mergeable`, `ci_still_running`, `not_approved`, `conflict`, `draft_status`, `not_open`, …

### comments (read)

```bash
glab mr note list "$M" -R "$P" -F json --jq '[.[].notes[] | select(.system|not) | {by:.author.username,at:.created_at,resolved,body:(.body[:300])}] | .[-8:]'
```

### diff (read)

File summary, small enough to read whole:

```bash
glab mr diff "$M" -R "$P" --raw | git apply --stat
```

One file's diff:

```bash
glab api --hostname "$H" "projects/$ID/merge_requests/$M/diffs?per_page=100" | jq -r --arg f "$FILE" '.[] | select(.new_path==$f) | .diff'
```

For the full diff, write it to a file (`glab mr diff "$M" -R "$P" --raw > /tmp/mr.diff`) and read the parts you need.

### create (write)

Push the branch first (`git push -u origin <branch>`). Inside a clone of the project:

```bash
glab mr create -s "$BRANCH" -b main -t "feat(x): title" -d "$(cat <<'EOF'
Body in markdown.
EOF
)" --remove-source-branch -y
```

Outside a clone, `glab mr create` fails (`git: exit status 128`); use the API:

```bash
glab api -X POST --hostname "$H" "projects/$ID/merge_requests" -f source_branch="$BRANCH" -f target_branch=main -f title="feat(x): title" -f description="Body" -F remove_source_branch=true | jq '{iid,web_url}'
```

Read-back: `view` shows the branches, `state: "opened"` and a `detailed_merge_status`.

### comment (write)

```bash
glab mr note create "$M" -R "$P" -m "$(cat <<'EOF'
Comment in markdown. `code`, $vars and "quotes" stay literal.
EOF
)"
```

Keep the quoted heredoc for markdown: inside `-m "..."`, backticks run as commands. Read-back: `comments` ends with the new body.

### update (write)

```bash
glab mr update "$M" -R "$P" -l ready-for-agent -y        # also: -t, -d, -u <label>, --draft, -r (ready), --reviewer <user>
```

Read-back: `view` shows the changed fields.

### approve / revoke (write)

```bash
glab mr approve "$M" -R "$P"     # or: glab mr revoke "$M" -R "$P"
```

Read-back: `glab api --hostname "$H" "projects/$ID/merge_requests/$M/approvals" | jq '{approved, by:[.approved_by[].user.username]}'`.

### merge (write)

Run only when the user asked for this merge; there is no undo but a revert MR. Check `view` first: `detailed_merge_status` must be `mergeable`.

```bash
glab mr merge "$M" -R "$P" --auto-merge=false -y
```

Read-back: `glab mr view "$M" -R "$P" -F json --jq '{state,merged_by:.merged_by.username,merge_commit_sha}'` shows `state: "merged"`.

### close / reopen (write)

```bash
glab mr close "$M" -R "$P"     # or: glab mr reopen "$M" -R "$P"
```

Read-back: `glab mr view "$M" -R "$P" -F json --jq .state` is `closed` / `opened`.

### delete (destructive)

Preview with `view` and show it to the user. After their explicit yes:

```bash
glab mr delete "$M" -R "$P"
```

Needs Owner. Read-back: `glab mr view "$M" -R "$P"` fails. Prefer `close`.

## Gotchas

- `glab mr merge` defaults to `--auto-merge=true`: with a running pipeline it only schedules the merge. Pass `--auto-merge=false` to merge now, or keep auto-merge deliberately and say so.
- `glab mr view -c` returns an empty `Notes` list; read comments with `glab mr note list`.
- `glab mr create` needs a git checkout of the target project, even with `-R`. From another clone it fails with `is not a fork of the target project`.
- A new MR reports `detailed_merge_status: "preparing"` and an empty `changes_count` for a few seconds. Re-run `view` before deciding it can't merge.
- `git apply --stat` lists binary and lock files with no line counts; `changes_count` in `view` is the true file count.
