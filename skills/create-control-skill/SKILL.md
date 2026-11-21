---
name: create-control-skill
description: "Generate a control-<service> skill: proven, token-efficient CLI recipes for operating a service (GitLab, Postgres, S3, Langfuse, …). Run as /create-control-skill <service>."
argument-hint: "<service>"
disable-model-invocation: true
---

# Create a control skill

A **control skill** (`control-<svc>`) is how an agent operates one service: a GitLab, a Postgres server, an S3 store. It holds the cheapest proven way to do each operation through one CLI, plus the gotchas no `--help` confesses. You write it for the next agent, read cold mid-task by someone who has never touched the service.

A control skill is **portable**: it runs unchanged on any Linux or macOS machine, against whichever instance that machine's settings name. So the skill's files hold mechanics only. What belongs to one instance or one person stays outside them:

- **Where the instance lives** (host, URL, DSN, and per-repo names such as a namespace or task queue) is a setting, read from the current repo's `.env` first, then the shell. The skill carries no default. When a setting is missing, `doctor` fails with a `fix:` line telling the agent to ask the user and where the user puts the answer.
- **What the instance is like** (its groups, databases, buckets, naming conventions, which objects are whose) goes in `~/.config/control-<svc>/instance.md`, a notes file on the machine that the skill points at. Step 5 writes it from what probing found.
- **The sandbox** is agreed with the user each time: the skill names how to find or create one, never a fixed project, bucket or database.
- **Reachability and trust** are tested, never assumed: `doctor` connects to the configured host and reports unreachable (a VPN that is down, a wrong address) apart from untrusted (a private CA the machine lacks).

Load `writing-for-agents` before writing any file. Every generated file follows it.

## 1. Preflight

- `<service>` given, else ask and stop. The target is global, since control skills serve every repo: `~/.config/skillshare/skills/control-<svc>/` when `~/.config/skillshare/skills` exists (skillshare manages the global skills), otherwise `~/.agents/skills/control-<svc>/`.
- If the target already exists, stop: extending or refreshing a control skill is maintenance, not creation.
- Look for an installed skill that already covers the service: `~/.config/skillshare/skills`, `~/.agents/skills`, `~/.claude/skills`, and this repo's `.agents/skills` and `.claude/skills`, by name and description (e.g. `langfuse`, `milvus`). Control skills are meant to replace these. Warn the user and carry the question "replace, or borrow from it?" into the step 4 batch. Read it either way; it is a source.

## 2. Pick the channel

A control skill speaks through **one CLI**. MCP servers are never a channel, even when one exists for the service.

1. **Established CLI.** The official or de-facto CLI (`glab`, `psql`, `s5cmd`, `aws`). Its raw-API passthrough (`glab api`) counts as the same channel and fills gaps; raw `curl` with a token does not. If it is not installed, ask the user before installing, naming the package and install command. This is the one question asked before probing.
2. **Our own CLI**, only when no established CLI exists, or when probing shows the established one cannot do a required operation against the company instance. Build it from [`references/cli-template.py`](references/cli-template.py): one Typer file at `scripts/<svc>.py`, dependencies inline (PEP 723), run as `uv run scripts/<svc>.py <cmd>`, wrapping the service's official Python SDK. Record in SKILL.md why the established CLI lost.

Every control skill ships `scripts/<svc>.py` either way: it holds `doctor`, and, with an established CLI, any **chain** (a recipe of 3+ commands, e.g. `failed-job-log <pipeline>`) as a subcommand that shells out to that CLI with JSON in and out. The established CLI stays the main interface; the script holds only what plain commands make clumsy.

## 3. Probe

Read-only, against the live instance. Answer from probing; ask only what you cannot observe.

- **Version**: CLI version, service version (e.g. `glab api version`).
- **Targeting**: how the CLI picks its instance and project (default host, config, flags). A default that points elsewhere, such as glab's `gitlab.com`, makes every recipe name the instance explicitly.
- **Auth**: where the CLI's own auth lives (`~/.config/glab-cli/config.yml`, `PG*` + `~/.pgpass`) and whether it works. Our own CLI reads credentials from the current repo's `.env` first, then shell environment variables; name the variables (the service's or SDK's standard names such as `GRAFANA_URL`, `LANGFUSE_BASE_URL`, `AWS_ACCESS_KEY_ID`; never a company prefix). Missing in both → the user sets them up; the skill says how.
- **Instances**: the host or server the user's settings name, and how the CLI is pointed at it. Facts about the instance go to the notes file, not the skill.
- **Prerequisites**: everything a fresh Linux or macOS machine needs before the first recipe works: `uv`, the CLI's runtime (Node, Python) and the CLI at a working version, the settings and credentials, helpers such as `jq`. For each: the exact error when it is missing, and the fix on both systems (`apt` and `brew`).
- **TLS trust**: which trust store each runtime in the channel reads. Python scripts use `truststore` (the OS store: Keychain on macOS, the system bundle on Linux) plus the PEM file `CONTROL_CA_FILE` names, the one variable every control skill shares for a private CA. Go CLIs read the OS store. Node and the aws CLI ignore it and must be handed a bundle. Record how the private-CA case is handled for this channel; verification is never turned off.
- **Surface**: `--help` for each subcommand group, docs for the detected version, which commands emit JSON and which flags project fields.
- **Shape of the company's data**: groups, projects, buckets, databases, labels the user can see. This is where conventions surface.

Propose 3-5 **features**: resource areas (issues, merge requests, pipelines; buckets, objects; tables, roles), not tasks and not endpoints. Tasks become the common-task chains in the index.

## 4. Ask once

One batch, after probing. Then run to the end without further prompts, except before installing anything or writing outside the sandbox.

- The features to seed (your proposal).
- The **sandbox**: a target safe to write to during proof (a scratch project, bucket or database), never shared data.
- Conventions probing could not settle: naming, which instances matter, what "the usual project" means.
- The installed-skill question from step 1, if any.

## 5. Generate

Write the files below into the target from step 1. Once its `SKILL.md` exists, link it:

- **skillshare**: `skillshare sync -g` links it into every global target. Recipes reach the script through `~/.agents/skills/`, so `skillshare target list -g` must show a target at `~/.agents/skills`; if none does, tell the user and add one only after their yes.
- **No skillshare**: `ln -s ../../.agents/skills/control-<svc> ~/.claude/skills/control-<svc>`.

Linked when `~/.agents/skills/control-<svc>/SKILL.md` and `~/.claude/skills/control-<svc>/SKILL.md` both resolve. Recipes call the script by that global path: `uv run ~/.agents/skills/control-<svc>/scripts/<svc>.py`. Leave `~/.agents/.skill-lock.json` alone; it tracks installed third-party skills.

**`SKILL.md`**: frontmatter `name: control-<svc>` and a model-facing `description` that names the service, the setting that selects the instance, and the CLI, and lists the trigger branches (e.g. "a self-hosted GitLab (the host GITLAB_HOST names) through glab: issues, merge requests, pipelines, CI variables, repository"). Model-invoked: omit `disable-model-invocation`. Then these sections, each grounded in what probing found, with no placeholders:

- **Setup**: the prerequisites as a numbered list in the order `doctor` checks them, `uv` first (doctor runs on it), each with its install or fix command for Linux and macOS; the settings that name the instance and what to ask the user when one is missing; how auth is established; where credentials live (paths and variable names, never values).
- **Doctor**: `uv run scripts/<svc>.py doctor`, one `ok`/`WARN`/`FAIL` line per prerequisite and check: CLI present at a working version, each setting and credential and where it came from, the configured host reachable (a `fix:` that names the VPN case) and its certificate trusted (a `fix:` that offers `CONTROL_CA_FILE` or the OS trust store), auth valid, CLI and service versions matching the proven ones (`WARN` on mismatch: the map may have drifted). Every `FAIL` prints a `fix:` line under it naming the exact command or the user's step; checks that depend on a failed one are skipped with a note. Run it first, and again whenever anything looks off. The section also carries the first-run rule for the next agent: on a `FAIL`, stop the task, show the user the `fix:` lines and offer to carry them out; run each install or system change only after their yes; the user writes credentials into `.env` or their shell themselves, never into the chat; rerun `doctor` until clean. A `FAIL` with no fix the agent can apply is reported to the user, never worked around.
- **Instances & conventions**: how the instance is selected, the pointer to `~/.config/control-<svc>/instance.md` (read when it exists; offer to record what the user answers), the recipe variables, and the sandbox rule: how to find or create one and that the user confirms it before the first proof write.
- **Safety**: every operation is tagged **read**, **write** or **destructive**. Reads run freely. Writes run when the user asked for that change, and end on their read-back. Destructive operations (delete, drop, force-push, overwrite, revoke) run only after showing a preview of exactly what goes and getting the user's explicit yes in the conversation.
- **Operate**: point at `features/README.md`.
- **Output shaping**: the fewest calls and the least output reaching the agent's context. JSON output piped through a `jq` projection of the needed fields; explicit limits on every listing; large payloads (logs, diffs, dumps) cut with `tail`, `head` or a filter, fetched whole only into a file.
- **Gotchas**: service-wide only; per-feature gotchas live in the feature file.

**`~/.config/control-<svc>/instance.md`** (outside the skill): what probing and step 4 settled about this instance: its host, the names of its groups, databases or buckets, conventions, the sandbox agreed on. Names only, never secrets.

**`agents/openai.yaml`**: `display_name: "Control <Service>"`, `short_description` from the description's first clause, `allow_implicit_invocation: true`.

**`features/`**: a `README.md` index and one file per feature, in the shape of [`references/feature-map-example/`](references/feature-map-example/). Each feature file has exactly four H2s: `Operations`, `Finding things`, `Recipes with <cli>`, `Gotchas`. A **recipe** is the exact command with its `jq` projection and the shape of what comes back; a write recipe ends on its **read-back**, the read command whose output proves the change landed. A recipe takes its inputs as shell variables (`"$P"`, `"$N"`), each defined in `Finding things` or SKILL.md, so it runs exactly as written once they are set; fixed values are generic (`control-sandbox`, `my-bucket`), never identifiers of one instance. Free text that may hold markdown (comments, descriptions) goes in a quoted heredoc (`"$(cat <<'EOF' … EOF)"`), never in `"..."`, where backticks run as commands. An edit to part of a stored text (append a line to a section) is a script command, not a read-edit-write the agent improvises.

**`scripts/<svc>.py`**: from the template. `PROVEN` at its top holds the CLI and service versions the proof ran against; `doctor` compares the installed ones to it.

Secrets never enter any file: no tokens, keys, passwords or DSNs with credentials, not even in an example. A value that looks like one is replaced by the name of where it lives.

## 6. Prove

A control skill that was never run is a draft. Run its own instructions, as written, against the live instance. Extract each recipe's code block from the feature file and run that text with its variables set, rather than retyping it, so the proof covers the words a later agent will read:

1. `doctor`: all `ok`. Then break each prerequisite you can simulate without changing the machine (credentials unset, a `PATH` without the CLI or its runtime, a CA bundle without the internal CA via a scratch copy of the script) and check that its `FAIL` prints the right `fix:` line.
2. Every **read** recipe in every seeded feature. The output matches the shape the recipe states.
3. Every **write** recipe the sandbox can host, inside the sandbox only, each followed by its read-back, then undone with the gentlest inverse (close, revert, unset). At minimum one full write round trip.
4. **Destructive** recipes are never run. They, and any write the sandbox could not host, are listed as unproven.

A recipe that fails gets fixed, then rerun. Fill the proof table in `features/README.md` (feature, date, CLI version, service version, unproven recipes) and set `PROVEN` in the script to the same versions.

Done when every read recipe and every hostable write recipe has passed in this run, every simulated prerequisite `FAIL` printed its fix, the proof table is filled, and `doctor` is clean.

## 7. Report

Tell the user: the skill path, the features and their recipe counts, what is unproven and why, any sandbox objects left behind, and what to install or configure on another machine (Setup). Mention any installed skill this one replaces from step 1, so they can remove it.
