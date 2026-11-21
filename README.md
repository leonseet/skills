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


| Skill                  | Description                                                                               | Install                                                 |
| ---------------------- | ----------------------------------------------------------------------------------------- | ------------------------------------------------------- |
| writing-commit         | Commit messages as `type(scope): imperative summary`, subject only                        | `npx skills add leonseet/skills@writing-commit`         |
| system-design-lab      | Turns a system-design article into a runnable local walkthrough lab                       | `npx skills add leonseet/skills@system-design-lab`      |
| control-excalidraw     | Operate an Excalidraw+ workspace and local .excalidraw files through the excalidraw CLI   | `npx skills add leonseet/skills@control-excalidraw`     |
| control-gitlab         | Operate a self-hosted GitLab through glab                                                 | `npx skills add leonseet/skills@control-gitlab`         |
| control-langfuse       | Operate a Langfuse v4 instance through the langfuse CLI and scripts/langfuse.py           | `npx skills add leonseet/skills@control-langfuse`       |
| control-milvus         | Operate a Milvus instance through scripts/milvus.py on pymilvus                           | `npx skills add leonseet/skills@control-milvus`         |
| control-notion         | Operate a Notion workspace through the ntn CLI                                            | `npx skills add leonseet/skills@control-notion`         |
| control-postgres       | Operate a PostgreSQL server through psql                                                  | `npx skills add leonseet/skills@control-postgres`       |
| control-s3             | Operate an S3-compatible object store through the aws CLI                                 | `npx skills add leonseet/skills@control-s3`             |
| control-temporal       | Operate a Temporal server through scripts/temporal.py                                     | `npx skills add leonseet/skills@control-temporal`       |
| create-control-skill   | Generate a proven control-<service> skill for operating a company service through one CLI | `npx skills add leonseet/skills@create-control-skill`   |
| notion-review-comments | Answer and act on the open review comments of a Notion page                               | `npx skills add leonseet/skills@notion-review-comments` |
| push-leon-skills       | Package a local skill and push it to its home repo (this one or GitLab leon-skills)       | `npx skills add leonseet/skills@push-leon-skills`       |

## License

MIT - see [LICENSE](./LICENSE).
