---
name: push-leon-skills
description: >-
  Package a local skill (SKILL.md, agents/openai.yaml, references/) and push it
  to the repo it belongs to: github.com/leonseet/skills or the GitLab leon-skills
  repo (dandelion/coding-agent-utils/leon-skills). Use when the user says
  push-leon-skills, /push-leon-skills, or asks to publish/package a skill into
  either repo.
argument-hint: "<skill> [github|gitlab]"
disable-model-invocation: true
---

# Push Leon Skills

Package `<skill>` into its **home repo** and push `main`. A skill has one home repo; every `<…>` below is that repo's cell in this table.

| | `github` | `gitlab` |
| --- | --- | --- |
| `<remote>` | `https://github.com/leonseet/skills.git` | `git@vc1.klass.dev:dandelion/coding-agent-utils/leon-skills.git` |
| `<clone>` (usual) | `~/dev/personal/repo/skills` | `~/dev/KLASS/internal_repos/skills` |
| `<install>` | `npx skills add leonseet/skills@<name>` | `npx skills add git@vc1.klass.dev:dandelion/coding-agent-utils/leon-skills.git --skill <name>` |
| `<readme-heading>` | **My Skills** | **Skills** |
| `<tree-url>` | `https://github.com/leonseet/skills/tree/main/skills/<name>` | `https://vc1.klass.dev/dandelion/coding-agent-utils/leon-skills/-/tree/main/skills/<name>` |

1. **Source.** `<skill>` is a name or a path to a dir with `SKILL.md`; none given → ask and stop. Check, in order: the given path, `.agent/skills/<name>`, `.cursor/skills/<name>`, `.claude/skills/<name>`, `skills/<name>`, `~/.config/skillshare/skills/<name>`. Several matches → the one being edited, else ask. Read all of it first.
2. **Home repo.** First that decides:
   1. the `github`/`gitlab` argument;
   2. the skill's skillshare source (`skillshare list -g --json`, the entry named `<name>`): `leonseet/skills` → `github`, `leon-skills` → `gitlab`;
   3. the one repo that already holds `skills/<name>/`;
   4. ask the user and stop. A skill in both repos with no argument and no skillshare source is this case.
3. **Clone.** The clone whose `origin` is `<remote>` (ssh or https form), usually `<clone>`; else search nearby clones. Never create one. On `main`, `git pull --ff-only origin main`.
4. **Package** into `skills/<name>/`, replacing any existing copy:
   - `SKILL.md`: body and frontmatter as-is (`name` = folder; `description` = what + when; keep `argument-hint` and `disable-model-invocation`; add no `license`/`metadata`). Only edits: fix links, and reword source-repo-relative phrases (`this repo's frontend/…`) to name the source project or drop them.
   - Loose `*.md` beside `SKILL.md` → `references/`, fix links. Keep existing subfolders (`scripts/`, `assets/`, `features/`, `references/`) as they are; note non-obvious script side effects in `SKILL.md`.
   - Never copy secrets (`.env`, tokens), `skills-lock.json`, `.agents/`, `.claude/`, `.cursor/`, `.codex/`, `__pycache__`, `.DS_Store`, swap files, or nested skills.
   - `github` is public: stop on anything internal to KLASS (hostnames, project paths, people) and ask.
   - Always write `agents/openai.yaml`:
     ```yaml
     interface:
       display_name: "Push Leon Skills"  # name in title case
       short_description: "Package a skill and push it to its home repo"  # description's first clause
     policy:
       allow_implicit_invocation: false  # true only for ambient skills, e.g. commit-message style
     ```
5. **README.** Add or update one row under `<readme-heading>`; no `###` section, no third-party skills, no other install flags:
   ```markdown
   | <name> | <short what it does> | `<install>` |
   ```
6. **Verify.** `npx skills add . --list` must list `<name>`; if not, check folder, `name`, `description`.
7. **Commit + push.** Subject only via `writing-commit`: `feat(skills): add <name>` for a new skill, else `feat(<name>): <what changed>` (`update skill` if nothing more specific). No body, trailers, `git config`, or empty commit. `git push origin HEAD`, never `--force`/`--no-verify`. Tell the user the home repo, the commit, `<tree-url>` and `<install>`.

**Stop and report** (don't force or branch) on: no `SKILL.md`, no home repo decided, no clone, non-fast-forward pull, a dirty tree you didn't make, secrets in the copy, failed verify, or rejected push.
