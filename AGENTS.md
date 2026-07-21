# Authoring skills in this repo

This repository is a **skill package**: one or more Agent Skills folders that people install with:

```bash
npx skills add leonseet/skills
```

## Where skills live

Put each skill at:

```text
skills/<skill-name>/SKILL.md
```

Optional companions (progressive disclosure):

- `references/` — long docs, checklists, templates
- `scripts/` — executable helpers (document side effects in README)
- `assets/` — static files the skill may copy or reference

Do **not** nest skills deeper than `skills/<name>/` unless you intentionally want path-based installs.

## Frontmatter requirements

Every `SKILL.md` needs:

- `name` — lowercase letters, numbers, hyphens; must match the folder name
- `description` — what the skill does **and** when to activate it

Recommended:

- `license: MIT`
- `metadata.author` / `metadata.version`

## What belongs here vs elsewhere

| Put in this repo | Put elsewhere |
| ---------------- | ------------- |
| Skills you author and maintain | Third-party skills (link them in README instead) |
| Portable workflows useful across projects | Always-on project rules (`AGENTS.md` / Cursor rules in the *consumer* repo) |
| Stable, reviewable instructions | Secrets, private org runbooks, credentials |

## Grouping on skills.sh

Edit `skills.sh.json` when you have enough skills to group. Skill names in that file must match frontmatter `name` values.

## Local check before push

```bash
npx skills add . --list
```

If a skill does not appear, check folder name, frontmatter `name`/`description`, and that the skill sits under `skills/`.
