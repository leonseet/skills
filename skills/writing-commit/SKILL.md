---
name: writing-commit
description: >-
  Commit messages as `type(scope): imperative summary`. Use when drafting or
  proposing a commit message, or when another skill needs commit message styling.
---

# Writing Commit

Subject line only — nothing after it (no body, no trailers, no `Co-Authored-By` from Cursor/Claude/Copilot or any other model):

```
type(scope): imperative summary
```

- **type** — conventional (`feat`, `fix`, `docs`, `chore`, `refactor`, `test`, `perf`, …) matching what the change does
- **scope** — short area from paths or concern (`skills`, `ingestion`, `cv`, …)
- **summary** — imperative mood, lowercase start, no trailing period; match recent `git log` voice
