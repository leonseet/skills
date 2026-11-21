# GitLab control map

Read this index, then use the matching feature file as the recipe book. Setup, doctor, safety, `H`/`P`/`ID` and output shaping live in [`../SKILL.md`](../SKILL.md).

## Baseline

- `uv run ~/.agents/skills/control-gitlab/scripts/gitlab.py doctor` all `ok`.
- `H`, `P` and `ID` set for the host and the target project (SKILL.md, Instances & conventions).
- Recipes are runnable as written once their shell variables are set. Each feature's `Finding things` says how to get them: `N` issue iid, `M` MR iid, `PL` pipeline id, `J` job id, `KEY` variable name, `REF` branch/tag/sha, `FILE` repo path.

## Common tasks

- **Why did CI fail?** `uv run ~/.agents/skills/control-gitlab/scripts/gitlab.py failed-job-log -p "$P" [--pipeline PL | --ref REF]`: failed jobs with cleaned log tails. Then [pipelines](./pipelines.md) `retry job` if it was flaky.
- **Is this MR ready?** [merge-requests](./merge-requests.md) `view` (merge status, head pipeline) → `comments` → `diff`.
- **Open an MR for my branch**: `git push -u origin <branch>`, then [merge-requests](./merge-requests.md) `create`.
- **Pick up an issue**: [issues](./issues.md) `list` with `--label ready-for-agent` → `view` → `comments`.
- **Which child issues can I take?** [issues](./issues.md) `links` on the parent: `takeable` is open, unassigned and unblocked.
- **Finish an issue**: [issues](./issues.md) `comment` with what was done → `close`.
- **Record a result on a parent or map issue**: [issues](./issues.md) `append to section`.
- **What changed between releases?** [repository](./repository.md) `compare` from the previous `vX.Y.Z` tag to the new one.
- **Does CI have the secret it needs?** [ci-variables](./ci-variables.md) `list`, then `check a value` if the user supplies the expected value.

## Feature entry contract

Each feature file has an H1, one paragraph saying what the resource is here, and a `Commands:` line naming the glab groups and API paths it covers, then exactly four H2s in this order:

1. `Operations`: one line each, tagged `read` / `write` / `destructive`.
2. `Finding things`: how to set the shell variables the recipes use.
3. `Recipes with glab`: one H3 per operation, `### <operation> (<tag>)`: the command, the output shape, and for writes, the read-back.
4. `Gotchas`.

A feature is one resource area. An operation shared between areas has one owner and the others link to it. To find the recipes a glab upgrade touches, grep the `Commands:` lines.

## Features

Proven live on one GitLab CE instance: reads against two real projects, writes in a private sandbox project. A recipe that fails is possible drift: check `--help` for the installed glab, fix the recipe, and re-prove it.

| File | Covers | Proven | glab | GitLab | Unproven |
| --- | --- | --- | --- | --- | --- |
| [issues](./issues.md) | list, view, comments, create, comment, edit, append to section, assign, links, link, blocked by, labels, close, reopen, delete | 2026-11-21 | 1.108.0 | 18.11.13 | |
| [merge-requests](./merge-requests.md) | list, view, comments, diff, create, comment, update, approve, merge, close, delete | 2026-11-21 | 1.108.0 | 18.11.13 | |
| [pipelines](./pipelines.md) | list, view, failed log, job log, lint, run, retry, cancel, play manual, delete | 2026-11-21 | 1.108.0 | 18.11.13 | |
| [ci-variables](./ci-variables.md) | list, check a value, set, update, group list, delete | 2026-11-21 | 1.108.0 | 18.11.13 | `group list` (needs group Owner) |
| [repository](./repository.md) | project, search, is member, branches, tags, protected, commits, compare, files, tree, create branch, commit files, create tag, delete branch/tag | 2026-11-21 | 1.108.0 | 18.11.13 | |
