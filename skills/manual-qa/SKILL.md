---
name: manual-qa
description: Run a ticket's Manual QA checklist together — agent executes, human audits the transcripts.
argument-hint: "<ticket-id>"
disable-model-invocation: true
---

# Manual QA

You run the ticket's `## Manual QA` checks and capture transcripts; the human audits them. Do not close the ticket or leave Human QA PASS/FAIL unless asked after they audit.

## Steps

1. **Plan.** Read `docs/agents/issue-tracker.md`, fetch `<ticket-id>`, extract every Backend (Command / Expected) and Frontend (Steps / Expected) check under `## Manual QA`. If missing/empty, stop. List the numbered plan (title · command/steps · expected) before running anything.

2. **Execute.** From repo root (`data/...` fixtures; never `cd backend`). `mkdir -p tmp/manual-qa-<ticket-id>`. For check *N*, capture a live shell transcript into `tmp/manual-qa-<ticket-id>/check-N.log` (descriptive suffix OK):
   ```bash
   LOG=tmp/manual-qa-<ticket-id>/check-N.log
   {
     set -v
     <cmd>
     set +v
     echo "(exit $?)"
   } 2>&1 | tee "$LOG"
   ```
   **Run the real commands inside the tee — do not `echo` them.** `tee` only records what the shell writes; a separate `echo "$ …"` (or soft labels like `$ postgres: check span`, or `...` ellipsis) is fake and forbidden. Put the actual invocations (full one-liners / full heredocs) in the `{ … }` block so `set -v` prints them as the shell reads them, then their stdout/stderr follow. Every evidence-producing step (ingest, `psql`/`python` probes, Milvus queries, follow-ups) runs in that block — or append with the same pattern and `tee -a "$LOG"`. Never run outside the tee and rewrite/paste the log afterward.
   Score each check agent-pass / agent-fail / blocked vs Expected. Missing CLI → tee `--help`, stop that check, ask. Frontend → artifacts (URLs, videos, screenshots). Only start needed infra; note what you reused.

3. **Audit pack.** Point at transcript files; short Excerpt only — never paste full logs. Match the shape below. Lookouts = concrete observables in *this* transcript (exit code, counts, paths, frame N), not a restatement of Expected.

## Audit pack

```markdown
## Manual QA — <ticket-id> · <title>

### Rollup
| # | Check | Agent score | Needs human |
|---|-------|-------------|-------------|
| 1 | … | pass / fail / blocked | yes/no (what) |

### Check 1 — <title>
- **Command / Steps:** `…`
- **Expected:** …
- **Agent score:** pass | fail | blocked — one-line why
- **Transcript:** `tmp/manual-qa-<ticket-id>/check-1.log`
- **Excerpt:**
  ```text
  …
  (exit <code>)
  ```
- **Lookout:**
  - …
- **Artifacts:** (omit if none)
```
