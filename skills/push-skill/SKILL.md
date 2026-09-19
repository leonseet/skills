---
name: push-skill
description: >-
  Package a local skill the way first-party skills in leonseet/skills are
  packaged (SKILL.md, agents/openai.yaml, references/) and push it to
  https://github.com/leonseet/skills. Use when the user says push-skill,
  /push-skill, or asks to publish/package a skill into that repo.
argument-hint: "<skill>"
disable-model-invocation: true
---

# Push Skill

`push-skill <skill>` packages that skill into [leonseet/skills](https://github.com/leonseet/skills) and pushes `main`.

`<skill>` is a folder name (`system-design-lab`) or a path to a skill directory that contains `SKILL.md`. No argument → ask and stop.

Layout, `openai.yaml`, README row, and git voice: [references/packaging.md](references/packaging.md).

## Progress

```
Push skill:
- [ ] 1. Find source
- [ ] 2. Find package repo
- [ ] 3. Pull
- [ ] 4. Package
- [ ] 5. README
- [ ] 6. Verify
- [ ] 7. Commit + push
```

### 1. Find source

Resolve `<skill>` to a directory with `SKILL.md`. Search the current workspace in order:

1. the path the user gave
2. `.agent/skills/<name>/`
3. `.cursor/skills/<name>/`
4. `.claude/skills/<name>/`
5. `skills/<name>/`

Read `SKILL.md` (and any companions) before copying. If several matches, pick the one the user is editing; if still ambiguous, ask.

### 2. Find package repo

Git remote `https://github.com/leonseet/skills.git` (ssh form is fine). Known clone: `~/Desktop/home/projects/skills`. If that path is missing or the remote does not match, search nearby clones; do not create a new repo.

### 3. Pull

In the package repo: `git checkout main` if needed, then `git pull --ff-only origin main`. Stop on divergence or a dirty tree you did not make.

### 4. Package

Write `skills/<name>/` per [references/packaging.md](references/packaging.md):

- `SKILL.md` (frontmatter `name` matches folder)
- `agents/openai.yaml` (always)
- companions in `references/`; fix links if you moved them
- `scripts/` / `assets/` only if the source has them

Overwrite the existing packaged copy of the same name. Do not rewrite the author's workflow text except link fixes and source-relative phrases that would be wrong in the package.

### 5. README

Add or update the **My Skills** row. Add a short `### <name>` subsection only when a human needs invoke form or companion paths.

### 6. Verify

```bash
npx skills add . --list
```

`<name>` must appear.

### 7. Commit + push

`writing-commit` subject only. Then `git push origin HEAD`.

Tell the user: commit, GitHub URL, and

```bash
npx skills add leonseet/skills@<name> -y
```

## Stop if

- no `<skill>` / no `SKILL.md`
- package repo not found
- pull is not fast-forward
- verify does not list the skill
- the copy would include secrets
