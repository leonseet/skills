# Tune sandcastle — reference

## How the loop is wired (orient before tuning)

`.sandcastle/loops/*.mts` drive sandboxed agent runs; each run streams to a log in `.sandcastle/logs/`. Knobs live in `configs.mts`:

- `MAX_REVIEW_CYCLES` (impl↔review cycles), `MAX_IMPLEMENT_ITERATIONS`, `MAX_REVIEW_ITERATIONS`, `MAX_COMMIT_ITERATIONS`, `SANDBOX_IDLE_TIMEOUT`.
- Agent/model/effort per role: `IMPLEMENT_AGENT`, `REVIEW_AGENT`, `MERGE_AGENT`, `COMMIT_AGENT`.
- `COPY_TO_WORKTREE` — what's seeded into each worktree (caches, `.models`, data).

Prompts the agents run under, grouped by loop in `.sandcastle/prompts/`: `implement/` (`implementer.md`, `reviewer.md`), `merge/` (`merger.md`, `reviewer.md`), and `shared/` (`committer.md`, loop-agnostic). Coding standards injected into context: `.sandcastle/standards/`. The test command the loop runs to verify work: `make test` (Makefile + `backend/` pytest).

## Log filename format

`sandcastle-<epicId>-<role>-<childId>-<cycle>[.iter].log` (merge runs are `sandcastle-merge-<epicId>-merger-<coordId>-<n>.log`). The `<childId>` (e.g. `agentic-reid-poc-5bf.1`) is the bead — `bd show` it for the task spec behind the run.

## Signal catalog (symptom → likely cause → surface to tune)

| Symptom in log | Usually means | Tune |
|---|---|---|
| Long log relative to peers (top of the `LINES`-sorted scan) | Agent explored too much: re-read skills/docs, spelunked dependency internals, re-derived facts | Pre-state facts in the prompt/standards or `docs/agents/`; pre-expand stable context via the loop's shell-expression preamble; tighten issue spec |
| `MAXED=YES` / `DONE=no` | Loop bound hit before convergence, or unparseable verdict | Raise the relevant `MAX_*`; or fix why it stalled (bad acceptance criteria, flaky test, ambiguous review rubric) |
| Same CLI friction across roles (e.g. `bd show --comments` unsupported → rediscover `--thread`) | A tool's real interface isn't documented where agents look | State the correct invocation in `docs/agents/issue-tracker.md` and/or the prompts |
| Repeated `sed -n ... SKILL.md / CONTEXT.md` | Agent re-reads the same context every run | Inline the essential bits into the prompt, or pre-expand via the preamble |
| `idle timeout` / long `timeout N` waits / slow `make test` | Verification dominates wall-clock | Speed the suite (below); revisit `SANDBOX_IDLE_TIMEOUT` |
| Time lost to `pnpm install` / `uv sync`, schema creation, model downloads, or "waiting for DB/service" before tests do real work | Cold-start: per-run env/resource provisioning isn't warmed or seeded | Warm & seed up front — pre-built caches/weights via `COPY_TO_WORKTREE`, template/pre-seeded DBs, healthchecked long-lived services (below: environment & resource provisioning) |
| Connection errors / retries against Postgres, pgvector, Milvus, Temporal, etc. | Resource not ready or not seeded when the test connects | Add readiness/healthchecks; seed the resource before the run rather than inside each test |
| Recurring beads backup/permission warnings | Env noise that costs tokens + can mask real failures | Fix in the `Dockerfile` / beads setup so the warning never prints |
| Many review cycles to converge | Implementer under-constrained or rubric unclear | Sharpen `implement/implementer.md` acceptance framing and the review rubric |
| Agent rediscovers task context the bead should have held (re-reads ADRs/CONTEXT, asks "is this the first pass?", re-derives acceptance criteria) | Beads not serving as external memory: thin descriptions, missing acceptance criteria, decisions left in chat instead of `bd comment`/`bd note`, no `discovered-from`/`blocks` links | Improve **issue organization** (below): how issues are written, labelled, linked, and annotated so a fresh session loads context from beads |

## Tunable surfaces

- **`Dockerfile`** — base image, toolchain, what's preinstalled vs fetched per run, env that suppresses noisy warnings. Fewer cold installs / less runtime noise = faster, cleaner runs.
- **`prompts/`** — the highest-leverage surface. Most context blow-ups and review-cycle churn trace to a prompt that under-specifies, omits a known gotcha, or makes the agent rediscover the environment.
- **`configs.mts`** — loop bounds, idle timeout, model/effort per role, `COPY_TO_WORKTREE`. Raise bounds only when logs show real progress being cut off; lower effort/model where a cheaper tier already converges.
- **`standards/`** — coding standards injected into agent context; encode recurring review nits here so they stop recurring.
- **`loops/` & `helpers/`** — the orchestration itself (shell-expression preamble, sandbox setup). Change last and carefully; verify with a dry reasoning pass since you can't cheaply re-run the loop.
- **Environment & resource provisioning (cold starts)** — every sandbox pays its setup cost up front: `helpers/sandboxes.mts` `onSandboxReady` runs `pnpm install`
  + `uv sync --frozen`, mounts the uv cache, and `COPY_TO_WORKTREE` seeds `node_modules`/`.models`/`data`. Tests then reach host services (`network: host`) defined in `deployments/*/docker-compose.yml` — Postgres/pgvector, Milvus, Temporal, Langfuse, SeaweedFS. Levers when the logs show time bleeding into setup or "waiting for"/connection retries: (1) **warm** — make sure every heavy dependency is cached/copied, not re-fetched (extend `COPY_TO_WORKTREE`, seed caches in the `Dockerfile`); (2) **seed before, not during** — pre-load DB schema
  + fixture data once into a template/persistent volume so each test connects to a ready DB instead of building state inline (Postgres `CREATE DATABASE … TEMPLATE`, pre-seeded pgvector/Milvus collections); (3) **keep resources up & healthy** — long-lived compose services with healthchecks so runs don't cold-start or race a not-yet-ready resource. Verify changes here by reasoning + a single targeted run; you can't cheaply re-run the whole loop.
- **The test suite (`make test`)** — the loop runs it every cycle, so its runtime is paid on every iteration. Levers: gate slow **real-model smoke tests** behind a marker so they run once at the end rather than each cycle; cache/seed model weights via `COPY_TO_WORKTREE` so tests don't redownload; parallelize pytest (`-n auto`); shrink fixtures. Never weaken assertions or drop coverage to go faster — that defeats the loop's purpose.
- **`docs/agents/` & `CONTEXT.md`** — repo-wide context agents read. If a log shows agents repeatedly rediscovering a fact (CLI shape, where weights live), the durable fix is to state it here.
- **Beads comments as cross-session memory (highest-leverage memory lever)** — every run ends by posting a `bd comment` to its bead (e.g. `Implementor: PASS …`, the reviewer verdict, `Merge: pass …`). That comment is the handoff the *next* session reads instead of re-deriving — so what it captures is a setup choice, dictated by the prompts. Read the comments the logs actually posted (`bd show
  <id>`) and ask: would a cold agent next session avoid redoing work from this?
  Good handoff comments record **decisions and the why**, **gotchas/dead-ends discovered** (so they aren't re-explored — the longest implementer logs here ballooned spelunking a dependency's internals), **pointers to the key files/symbols touched**, **what was verified and how**, and **what's deliberately left for later**. If comments are thin, terse, or pure status, the lever is the prompt instruction that governs them (`implement/implementer.md`, `*/reviewer.md`, `merge/merger.md`): prescribe a short structured handoff block. Adjacent issue-organization knobs: explicit testable **acceptance criteria** (vague → extra review cycles), `bd link` dependencies (`blocks`, `discovered-from`), and labels per `docs/agents/triage-labels.md`. The durable fix is usually in the prompts (and the `create-epic`/`create-features`/`create-tasks`/`triage` surfaces that produce issues), not hand-editing one bead. (This skill reads/edits issues and comments for quality but does not file new beads for its own findings.)

## What NOT to do

- Don't tune from a single log — confirm a signal **recurs** before acting.
- Don't change app code/tests to make a specific task pass; that's the implementer loop's job.
- Don't raise loop bounds to paper over a stall whose real cause is a bad prompt, flaky test, or unclear rubric — fix the cause.
