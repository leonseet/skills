---
name: control-gitlab
description: "Operate a self-hosted GitLab (the host GITLAB_HOST names) through glab: issues, merge requests, pipelines and job logs, CI/CD variables, and remote branches, tags and files. Use whenever a task reads or changes anything on that GitLab. Local git work (commit, push, pull) is plain git."
---

# Control GitLab

The GitLab instance is the host `GITLAB_HOST` names (proven on GitLab CE 18). Every operation goes through `glab`: its subcommands first, `glab api` for the rest. Local repository work (stage, commit, push, pull, rebase) is plain `git` and lives outside this skill.

## Setup

A new machine needs, in this order (`doctor` checks each and prints the fix for what is missing):

1. `uv`: `curl -LsSf https://astral.sh/uv/install.sh | sh`. `doctor` runs on it, so this one comes first.
2. `glab`: `brew install glab` when Homebrew is present, otherwise a release from https://gitlab.com/gitlab-org/cli/-/releases.
3. `jq`: `sudo apt install jq` on Linux, `brew install jq` on macOS.
4. `GITLAB_HOST`: the instance's host name, without `https://`. The skill carries no default. The script reads it from the current repo's `.env` first, then the shell. When both lack it, ask the user; `doctor` suggests the `origin` remote's host and the hosts glab is logged in to. They put it in the repo's `.env` when it belongs to that project, or export it in their shell's startup file (`~/.bashrc`, `~/.zshrc`) for every repo.
5. A reachable, trusted host. `doctor` connects to it. An internal host answers only on the network or VPN that serves it. glab trusts the OS trust store (Keychain on macOS, the system bundle on Linux); for a host whose certificate comes from a private CA the machine lacks, the user either adds that CA to the OS store or runs `glab config set ca_cert /path/to/ca.pem --host "$H"`.
6. Auth: a personal access token with scope `api`, created at `https://$H/-/user_settings/personal_access_tokens`. The user runs `glab auth login --hostname "$H"` in their own terminal (it prompts interactively) and pastes it there; glab stores it in its own config (`~/.config/glab-cli/config.yml` on Linux). Nothing else holds a token.

## Doctor

```bash
uv run ~/.agents/skills/control-gitlab/scripts/gitlab.py doctor
```

One `ok`/`WARN`/`FAIL` line each: glab and its version, `jq`, `GITLAB_HOST` and where it came from, the host (reachable, certificate trusted), auth; then the API user and the GitLab version against the ones this map was proven on. Every `FAIL` has a `fix:` line under it. Run it first, and again whenever a command fails strangely.

On a `FAIL`, stop the task and walk the user through the `fix:` lines one at a time, offering to run each fix yourself; then rerun `doctor` until it is clean. Install commands and other system changes run only after the user's yes; the user enters credentials themselves, never into the chat. A `FAIL host` that says unreachable is usually a VPN that is down: say so and let the user connect. A `FAIL` with no fix you can apply is reported to the user, never worked around. A version `WARN` means a recipe may have drifted: check its `--help`.

## Instances & conventions

- **One instance**: the host `GITLAB_HOST` names. glab's own default host is `gitlab.com` and a repo `.env` is invisible to glab, so every recipe names the host through `H`: `-R "$H/<group>/<project>"` on subcommands, `--hostname "$H"` on `glab api`.
- **Host and project variables**: recipes use `H` (host), `P` (host-qualified path) and `ID` (numeric project id, for `glab api`). Set them once per shell:
  ```bash
  H=$(uv run ~/.agents/skills/control-gitlab/scripts/gitlab.py host)
  P=$H/<group>/<project>
  ID=$(glab repo view "$P" -F json --jq .id)
  ```
  Default project: the `origin` remote of the repo you are in (`git remote get-url origin`) when it points at `$H`; otherwise ask the user which project.
- **Instance notes**: `~/.config/control-gitlab/instance.md`, this machine's notes on the instance `GITLAB_HOST` names: its groups, label vocabulary, branch and release practice, CI runners and image registry. Read it before the first recipe when it exists. For what it lacks, observe the instance, then ask the user, and offer to record their answer there (names and conventions, never secrets).
- **Project conventions**: the repo's `AGENTS.md`, `CLAUDE.md` or `CONTRIBUTING.md`, then what [repository](features/repository.md) `protected branches` and recent MRs show.
- **Sandbox**: a project the user picks, never a default. Before the first proof write, look for candidates among the user's own projects, then tell the user which project the test writes will land in (or that you would create a private `control-sandbox` in their namespace) and wait for their yes:
  ```bash
  glab api --hostname "$H" "projects?owned=true&search=sandbox&simple=true&per_page=20" | jq -r '.[].path_with_namespace'
  ```

## Safety

Every operation in `features/` is tagged:

- **read**: run freely.
- **write**: run when the user asked for that change, then run the recipe's read-back and report what it shows.
- **destructive** (delete, force-push, overwrite, revoke): show the user exactly what goes, using the recipe's preview, and run it only after their explicit yes in the conversation.

CI/CD variable **values** are secrets: they never appear in your output, files, commits or messages. See [ci-variables](features/ci-variables.md).

## Operate

Read [`features/README.md`](features/README.md): the common-task chains, then one recipe file per resource area.

## Output shaping

Keep calls few and output small:

- Subcommands take `-F json --jq '<projection>'` (`glab issue list` takes `-O json` instead). Project only the fields the task needs. `glab api` has no `--jq`; pipe it to `jq`.
- Every listing sets a limit: `-P <n>` on subcommands, `per_page=<n>` on `glab api`.
- Cut big text at the source: `.description[:800]`, the last few notes, `tail -n` on job logs, `git apply --stat` on diffs. Fetch a full body, log or diff only into a file, then read the part you need.

## Gotchas

- A bare `-R group/project` outside a clone of the instance silently goes to gitlab.com and fails with `404` or `401`. Always use the `$H/` prefix.
- `glab --jq` prints object keys sorted alphabetically, not in the order of your projection.
- Placeholders such as `projects/:id/...` in `glab api` resolve only inside a clone of the instance; use `$ID`.
