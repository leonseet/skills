# Repository

The server side of a project's repository: project lookup and settings, remote branches and tags, protection rules, history, and reading files without a clone. Local work (stage, commit, push, pull, rebase, checkout) is plain `git` in a clone; this file covers what lives on the server.

Commands: `glab repo view`, `glab api projects`, `glab api projects/:id/repository/{branches,tags,commits,compare,files,tree}`, `glab api projects/:id/protected_branches`.

## Operations

- `project` (read): id, default branch, merge settings.
- `search projects` (read): find a project by name.
- `is member` (read): is a user a member of the project, directly or through a group?
- `branches` (read).
- `tags` (read).
- `protected branches` (read).
- `commits` (read): recent history on a ref.
- `compare` (read): commits and files between two refs.
- `read file` (read): a file's content at a ref.
- `tree` (read): a directory listing at a ref.
- `create branch` (write).
- `commit files` (write): commit without a clone.
- `create tag` (write).
- `delete branch` / `delete tag` (destructive).

## Finding things

- `P` and `ID`: SKILL.md. For a project you only know by name, `search projects`.
- `REF`: a branch, tag or sha. Release tags are `vX.Y.Z`; the newest is first in `tags`.
- `FILE`: a repo path. URL-encode `/` as `%2F` in the `files` endpoint: `FILE_ENC=$(jq -rn --arg f "$FILE" '$f|@uri')`.

## Recipes with glab

### project (read)

```bash
glab repo view "$P" -F json --jq '{id,path_with_namespace,default_branch,visibility,merge_method,squash_option,remove_source_branch_after_merge,web_url}'
```

### search projects (read)

```bash
glab api --hostname "$H" "projects?search=$Q&membership=true&simple=true&per_page=10" | jq -r '.[].path_with_namespace'
```

`membership=true` keeps it to projects you belong to.

### is member (read)

```bash
U_ID=$(glab api --hostname "$H" "users?username=$USERNAME" | jq '.[0].id')
glab api --hostname "$H" "projects/$ID/members/all/$U_ID" 2>/dev/null | jq -ce 'select(.username) | {username,access_level}' || echo not-a-member
```

Counts membership through groups too. Prints `{username,access_level}` (30 Developer, 40 Maintainer, 50 Owner) or `not-a-member`.

### branches (read)

```bash
glab api --hostname "$H" "projects/$ID/repository/branches?per_page=50" | jq -c '[.[] | {name,protected,merged,sha:.commit.short_id,at:.commit.committed_date}]'
```

Add `&search=<prefix>` to filter.

### tags (read)

```bash
glab api --hostname "$H" "projects/$ID/repository/tags?per_page=10" | jq -c '[.[] | {name,sha:.commit.short_id,at:.commit.committed_date}]'
```

Newest first.

### protected branches (read)

```bash
glab api --hostname "$H" "projects/$ID/protected_branches" | jq -c '[.[] | {name,push:[.push_access_levels[].access_level_description],merge:[.merge_access_levels[].access_level_description],force:.allow_force_push}]'
```

### commits (read)

```bash
glab api --hostname "$H" "projects/$ID/repository/commits?ref_name=$REF&per_page=10" | jq -c '[.[] | {sha:.short_id,title,author:.author_name,at:.committed_date}]'
```

### compare (read)

```bash
glab api --hostname "$H" "projects/$ID/repository/compare?from=$FROM&to=$REF" | jq '{commits:[.commits[] | {sha:.short_id,title}],files:[.diffs[].new_path]}'
```

Leaves out the per-file diffs. One file's diff: `jq -r --arg f "$FILE" '.diffs[] | select(.new_path==$f) | .diff'`.

### read file (read)

```bash
glab api --hostname "$H" "projects/$ID/repository/files/$FILE_ENC/raw?ref=$REF" | head -n 200
```

Metadata only (size, last commit): drop `/raw` and project `{file_path,size,last_commit_id}` with `jq`.

### tree (read)

```bash
glab api --hostname "$H" "projects/$ID/repository/tree?ref=$REF&path=&per_page=100" | jq -r '.[] | "\(.type) \(.path)"'
```

Set `path=<dir>` for a subdirectory, add `&recursive=true` for everything below it (paginate with `&page=N`).

### create branch (write)

```bash
glab api -X POST --hostname "$H" "projects/$ID/repository/branches" -f branch="$BRANCH" -f ref="$REF" | jq -c '{name,sha:.commit.short_id}'
```

Read-back: `branches` with `&search=$BRANCH`.

### commit files (write)

For a small change on a remote branch without a clone; in a clone, use `git`.

```bash
jq -n --arg b "$BRANCH" --arg f "$FILE" --rawfile c ./local-file '{branch:$b,commit_message:"docs: update",actions:[{action:"update",file_path:$f,content:$c}]}' \
  | glab api -X POST --hostname "$H" "projects/$ID/repository/commits" -H "Content-Type: application/json" --input - | jq -c '{short_id,title}'
```

`action` is `create`, `update`, `delete` or `move`; several actions make one commit. Read-back: `commits` on `$BRANCH` starts with the new sha. A push to a branch with CI starts a pipeline.

### create tag (write)

```bash
glab api -X POST --hostname "$H" "projects/$ID/repository/tags" -f tag_name="$TAG" -f ref="$REF" -f message="Release $TAG" | jq -c '{name,sha:.commit.short_id}'
```

Read-back: `tags` lists it first. In projects whose CI runs on tags (a `vX.Y.Z` tag that builds and deploys, say), this starts that pipeline. Say so before creating one.

### delete branch / delete tag (destructive)

Preview: the ref's sha, and for a branch whether it is `merged` and has an open MR (`glab mr list -R "$P" -s "$BRANCH"`). Show it to the user. After their explicit yes:

```bash
glab api -X DELETE --hostname "$H" "projects/$ID/repository/branches/$(jq -rn --arg b "$BRANCH" '$b|@uri')"
glab api -X DELETE --hostname "$H" "projects/$ID/repository/tags/$TAG"
```

Read-back: `branches` / `tags` no longer list it. Protected branches and tags refuse deletion.

## Gotchas

- Branch names with `/` (`release/v0.12.0`) must be URL-encoded in path segments (`release%2Fv0.12.0`); in query strings (`ref=`) they work as is.
- `simple=true` on project search drops settings fields; use `project` for those.
- The API's `merged` on a branch is about the default branch only.
