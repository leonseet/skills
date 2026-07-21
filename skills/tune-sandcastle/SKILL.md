---
name: tune-sandcastle
description: Diagnose and improve the .sandcastle agent-loop setup (Dockerfile, prompts, configs, loops, standards, the test suite it runs, and how work is saved to beads as cross-session memory) by mining run logs in .sandcastle/logs and their linked beads issues and comments for efficiency and effectiveness problems. Use when sandcastle runs feel slow, expensive, flaky, or low-quality, when its tests are slow, when beads handoff comments don't carry context across sessions, or when the user asks to tune/optimize/speed up their sandcastle setup.
disable-model-invocation: true
---

# Tune sandcastle

Iteratively improve this repo's `.sandcastle` agent loop by reading the evidence its runs leave behind, then proposing targeted fixes. **Diagnose from logs + issues first; never tune blind.**

Operating mode for this skill:

- **Propose, then apply on approval.** Present a ranked diagnosis with concrete diffs. Do not edit files until the user approves.
- **Keep it in-conversation.** Do not create beads issues for findings (reading them for context is fine).

## Workflow

1. **Scan the runs.** `bash .agents/skills/tune-sandcastle/scripts/scan-logs.sh` (add `--archive` for history). Rows are sorted by **log length (`LINES`)** — the primary prioritisation signal, since a longer log means more turns / exploration / thrash. (The context-window number these runs print is unreliable; the scanner ignores it.) It also reports iterations, max-iter hits, completion, a cross-run friction tally (bd CLI friction, timeouts, warnings, re-reads), and the bead ids referenced.

2. **Read the worst offenders.** Open the 2-3 logs at the **top of the table (longest)**, plus any with `MAXED=YES` or `DONE=no`. Read the narrative where the log balloons — _what was the agent doing when it generated all that?_ See [REFERENCE.md](REFERENCE.md) for the signal catalog and what each symptom usually means.

3. **Pull issue + comment context.** For the flagged bead ids, `bd show <id>` to read both the task spec _and the comments each run posted back_. Ask two things: was the task underspecified (prompt/issue-quality problem)? And would the handoff comments let a fresh session continue without re-deriving (cross-session-memory problem)? Thin or status-only comments are a fixable signal — see [REFERENCE.md](REFERENCE.md) → beads comments as cross-session memory.

4. **Cluster into root causes.** Group symptoms by _recurring_ cause, not per-run noise. A friction that appears in implementer **and** reviewer **and** merger is systemic — fix it upstream once. Map each cause to a tunable surface (see [REFERENCE.md](REFERENCE.md) → Tunable surfaces).

5. **Rank by impact / effort.** Lead with the cheapest edits that kill the most-repeated or most-expensive friction. Note expected effect (e.g. "removes ~Nk context re-reads/run", "cuts a 14s real-model test from every cycle").

6. **Propose, then apply.** Present the ranked diagnosis with a concrete diff per fix. On approval, apply with Edit; re-run the scan to confirm the signal would change where measurable.

## Scope

Tunable surfaces live under `.sandcastle/` (`Dockerfile`, `prompts/`, `configs.mts`, `loops/`, `standards/`, `helpers/`), the **test suite the runs execute** (`make test` → Makefile targets, pytest markers, slow real-model smoke tests), the **environment & resource provisioning** behind those tests (sandbox `onSandboxReady` setup, `COPY_TO_WORKTREE` caches, and the `deployments/*` services — Postgres/pgvector, Milvus, Temporal — that benefit from warming/seeding to kill cold starts), and **beads as external memory** — how issues are organized and especially the **handoff comments each run posts** (governed by the prompts), so a fresh agent session loads context from beads instead of re-deriving it. Repo-wide agent docs (`docs/agents/`, `CONTEXT.md`) are in scope when a log shows agents repeatedly rediscovering something those docs should have stated. See [REFERENCE.md](REFERENCE.md) for the full map and concrete examples drawn from this repo's logs.

Do not change application code or tests to make a task pass — that's the implementer loop's job, not setup tuning. Only change tests when the goal is making the _suite the loop runs_ faster or less flaky without weakening coverage.
