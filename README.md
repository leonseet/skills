# Agent skills

Personal skill package for coding agents.

## Install skills from this repo

```bash
# Preview what is available
npx skills add leonseet/skills --list

# Install everything in this package
npx skills add leonseet/skills

# Install one skill
npx skills add leonseet/skills@skill-name

# Global install (available across projects)
npx skills add leonseet/skills -g
```

## My Skills

Skills authored in this package. Install with `npx skills add leonseet/skills`.


| Skill             | Description                                                          | Install                                            |
| ----------------- | -------------------------------------------------------------------- | -------------------------------------------------- |
| shape-plan        | Shape planning artifacts before any implementation code              | `npx skills add leonseet/skills@shape-plan`        |
| herdr-see-pane    | View the other pane in the current Herdr tab (metadata + transcript) | `npx skills add leonseet/skills@herdr-see-pane`    |
| writing-commit    | Commit messages as `type(scope): imperative summary`, subject only   | `npx skills add leonseet/skills@writing-commit`    |
| system-design-lab | Turns a system-design article into a runnable local walkthrough lab  | `npx skills add leonseet/skills@system-design-lab` |
| push-skill        | Package a local skill and push it to this repo                       | `npx skills add leonseet/skills@push-skill`        |

## External Skills

Useful skills from other authors. Install each from its own repo:


| Skill             | Why                                                              | Install                                                  |
| ----------------- | ---------------------------------------------------------------- | -------------------------------------------------------- |
| agent-browser     | Browser automation via accessibility snapshots                   | `npx skills add vercel-labs/agent-browser@agent-browser` |
| herdr             | Control Herdr agent terminal multiplexer                         | `npx skills add ogulcancelik/herdr@herdr`                |
| mattpocock/skills | Matt Pocock's agent workflows (grill-me, TDD, reviews, and more) | `npx skills add mattpocock/skills`                       |
| makenotion/skills | Notion CLI (`ntn`) for workers, public API, and file uploads     | `npx skills add makenotion/skills`                       |
| impeccable        | Frontend design / redesign / polish / UX critique                | `npx skills add pbakaus/impeccable@impeccable`           |
| langfuse          | Langfuse docs + CLI for traces, prompts, datasets, scores        | `npx skills add langfuse/skills@langfuse`                |
| milvus            | Operate Milvus with pymilvus (collections, search, RBAC)         | `npx skills add zilliztech/milvus-skill@milvus`          |
| postgres          | PostgreSQL design, pgvector, PostGIS, TimescaleDB, migrations    | `npx skills add timescale/pg-aiguide@postgres`           |
| last30days        | Research what people say about a topic in the last 30 days       | `npx skills add mvanhorn/last30days-skill@last30days`    |



## Safety

Treat skills like code. Read `SKILL.md` (and especially any `scripts/`) before installing unfamiliar packages.

## License

MIT - see [LICENSE](./LICENSE).
