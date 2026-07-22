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


| Skill           | Description                                                          | Install                                            |
| --------------- | -------------------------------------------------------------------- | -------------------------------------------------- |
| herdr-see-pane  | View the other pane in the current Herdr tab (metadata + transcript) | `npx skills add leonseet/skills@herdr-see-pane -g` |
| manual-qa       | Run a ticket's Manual QA checklist — agent executes, human audits    | `npx skills add leonseet/skills@manual-qa`         |
| seaweedfs       | Read/write/inspect SeaweedFS via its S3 gateway (`uv run` script)    | `npx skills add leonseet/skills@seaweedfs`         |
| tune-sandcastle | Diagnose and improve `.sandcastle` agent-loop setups from run logs   | `npx skills add leonseet/skills@tune-sandcastle`   |


```bash
# Quick install all my skills
npx skills add leonseet/skills@herdr-see-pane -g -y
npx skills add leonseet/skills@manual-qa -y
npx skills add leonseet/skills@seaweedfs -y
npx skills add leonseet/skills@tune-sandcastle -y
```



## External Skills

Useful skills from other authors. Install each from its own repo:


| Skill             | Why                                                              | Install                                                  |
| ----------------- | ---------------------------------------------------------------- | -------------------------------------------------------- |
| agent-browser     | Browser automation via accessibility snapshots                   | `npx skills add vercel-labs/agent-browser@agent-browser` |
| herdr             | Control Herdr agent terminal multiplexer                         | `npx skills add ogulcancelik/herdr@herdr`                |
| mattpocock/skills | Matt Pocock's agent workflows (grill-me, TDD, reviews, and more) | `npx skills add mattpocock/skills`                       |
| impeccable        | Frontend design / redesign / polish / UX critique                | `npx skills add pbakaus/impeccable@impeccable`           |
| langfuse          | Langfuse docs + CLI for traces, prompts, datasets, scores        | `npx skills add langfuse/skills@langfuse`                |
| milvus            | Operate Milvus with pymilvus (collections, search, RBAC)         | `npx skills add zilliztech/milvus-skill@milvus`          |
| postgres          | PostgreSQL design, pgvector, PostGIS, TimescaleDB, migrations    | `npx skills add timescale/pg-aiguide@postgres`           |
| last30days        | Research what people say about a topic in the last 30 days       | `npx skills add mvanhorn/last30days-skill@last30days`    |


```bash
# Quick install all external skills
npx skills add vercel-labs/agent-browser@agent-browser -g -y
npx skills add ogulcancelik/herdr@herdr -g -y
npx skills add mattpocock/skills -y
npx skills add pbakaus/impeccable@impeccable -y
npx skills add langfuse/skills@langfuse -y
npx skills add zilliztech/milvus-skill@milvus -y
npx skills add timescale/pg-aiguide@postgres -y
npx skills add mvanhorn/last30days-skill@last30days -y
```



## Safety

Treat skills like code. Read `SKILL.md` (and especially any `scripts/`) before installing unfamiliar packages.

## License

MIT - see [LICENSE](./LICENSE).
