# Packaging conventions for leonseet/skills

Copy this layout. Do not invent a different one.

## Target layout

```
skills/<skill-name>/
├── SKILL.md
├── agents/openai.yaml
├── references/          # companion markdown only
└── scripts/             # only if the source already has executable helpers
```

- Folder name = frontmatter `name` = install id (`npx skills add leonseet/skills@<skill-name>`).
- `SKILL.md` is required. Everything else is optional except `agents/openai.yaml` — always write that file.
- Long docs, checklists, examples, and templates go in `references/`. If the source has loose `*.md` next to `SKILL.md`, move them into `references/` and rewrite links in `SKILL.md` (one level deep: `references/foo.md`).
- Keep `scripts/` and `assets/` at the skill root if the source already uses them. Document script side effects in the package README when they are non-obvious.
- Do not nest another skill inside this folder.

## SKILL.md frontmatter

Keep the source frontmatter. After copy, ensure:

| Field | Rule |
| --- | --- |
| `name` | lowercase letters, numbers, hyphens; matches folder |
| `description` | what it does **and** when to run it |
| `argument-hint` | keep if present; add only when the skill takes a clear argument |
| `disable-model-invocation` | keep the source value; do not flip it |

Do not add `license` / `metadata.*` unless sibling first-party skills already use them.

## `agents/openai.yaml`

Always present. Match siblings:

```yaml
interface:
  display_name: "Title Case Name"
  short_description: "one-line what it does"
policy:
  allow_implicit_invocation: false
```

- `display_name`: human title from the `name` (`push-skill` → `Push Skill`).
- `short_description`: first clause of the skill description, no "Use when…".
- `allow_implicit_invocation`: `false` when `disable-model-invocation: true` (or the field is absent and the skill is meant to be named). `true` only when the source is clearly ambient (example: `writing-commit`).

## Package README (`README.md`)

Under **My Skills**, add or update one table row:

```markdown
| <skill-name> | <short what it does> | `npx skills add leonseet/skills@<skill-name> -y` |
```

Use `-g -y` in the install cell only when the skill is meant to be global (Herdr, commit style, and similar always-on helpers). Default is `-y`.

Add a `### <skill-name>` subsection only when a human needs more than the table row (invoke form, output contract, companion files). Keep it short.

Do not list third-party skills under **My Skills**. Those stay in **External Skills**.

## Copy rules

- Copy the skill body as-is. Packaging is layout + `openai.yaml` + README + link fixes after a `references/` move. Do not rewrite the author's instructions.
- Rephrase source-relative lines that only make sense in the original repo (`this repo's frontend/…` → name the source lab or drop the local assumption).
- Never copy `.env`, credentials, `skills-lock.json`, or agent install junk (`.agents/`, `.claude/`, `.cursor/`, `.codex/`).
- Skip `__pycache__`, `.DS_Store`, and editor swap files.

## Git

- Work on `main`. `git pull --ff-only origin main` before editing.
- Commit subject only, via `writing-commit`: `type(scope): imperative summary`.
  - new skill: `feat(skills): add <skill-name>`
  - existing skill, packaging only: `feat(<skill-name>): package skill with openai.yaml`
- No commit body, no trailers, no `Co-Authored-By`.
- Push `git push origin HEAD`. Never `--force`, never `--no-verify`.
- Do not `git config`. Do not commit if there is nothing to commit.

## Verify

From the package repo root:

```bash
npx skills add . --list
```

The skill name must appear. If it does not: folder is not `skills/<name>/`, or frontmatter `name` / `description` is missing.
