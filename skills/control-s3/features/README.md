# S3 control map

Read this index, then use the matching feature file as the recipe book. Setup, doctor, safety, the recipe variables and output shaping live in [`../SKILL.md`](../SKILL.md).

## Baseline

- `uv run ~/.agents/skills/control-s3/scripts/s3.py doctor` all `ok`, run from inside the repo whose `.env` holds the key.
- Recipes are runnable as written once their shell variables are set: `B`, `K`, `PREFIX`, `FILE`, `DIR`, `OUT`, `B2`/`K2`, plus `DAYS`, `ID`, `NAME`, `UP` where a feature uses them. Each feature's `Finding things` says how to get them.
- Sandbox: bucket `control-s3-sandbox` (SKILL.md says how it comes to exist). Prove write recipes there only.
- `S3_URL=$(uv run ~/.agents/skills/control-s3/scripts/s3.py endpoint)` where a recipe builds a public URL.

## Common tasks

- **What is in this bucket?** [buckets](./buckets.md) `info` → [objects](./objects.md) `list`, walking down `prefixes`.
- **Share a file with someone**: [objects](./objects.md) `upload` (or find the existing key) → `presigned URL` for one person, or `public URL` if the bucket is public.
- **Publish an HTML page or explainer**: [objects](./objects.md) `upload` with `--content-type text/html` into a public bucket such as `agent-explainers` → `public URL` and its `200` check.
- **Pull an artifact locally**: [objects](./objects.md) `find` → `inspect` → `download` into the scratchpad.
- **Why is a browser blocked from loading an object?** [buckets](./buckets.md) `info`: `cors` null, or `policy` not covering the key → [bucket-settings](./bucket-settings.md) `set CORS` or `public read`, with the user's go-ahead.
- **Make a bucket for a new project**: [buckets](./buckets.md) `create` → [bucket-settings](./bucket-settings.md) `set expiry` for scratch data, `public read` for pages → `info` as the read-back.
- **Where did the space go?** [buckets](./buckets.md) `info` (`hidden_versions`, `unfinished_uploads`, `top_prefixes`) → `size` per prefix → [multipart-uploads](./multipart-uploads.md) `list unfinished`.

## Feature entry contract

Each feature file has an H1, one paragraph saying what the resource is here, and a `Commands:` line naming the aws commands and script commands it covers, then exactly four H2s in this order:

1. `Operations`: one line each, tagged `read` / `write` / `destructive`.
2. `Finding things`: how to set the shell variables the recipes use.
3. `Recipes with aws`: one H3 per operation, `### <operation> (<tag>)`: the command, the output shape, and for writes, the read-back.
4. `Gotchas`.

A feature is one resource area. An operation shared between areas has one owner and the others link to it. To find the recipes an AWS CLI upgrade touches, grep the `Commands:` lines.

## Features

Proven live on one Ceph RGW store with one user's key: reads against the live buckets; writes and destructive recipes only in `control-s3-sandbox` and a throwaway `control-s3-sandbox-proof-134810` (created, versioned, purged and deleted). A recipe that fails is possible drift: check `aws <command> help` for the installed version, fix the recipe, and re-prove it.

| File | Covers | Proven | aws | Ceph | Unproven |
| --- | --- | --- | --- | --- | --- |
| [buckets](./buckets.md) | list, info, size, create, delete | 2026-11-06 | 2.39.5 | tentacle | none |
| [bucket-settings](./bucket-settings.md) | policy, set CORS, remove CORS, set expiry, remove expiry, public read, remove policy, enable versioning | 2026-11-06 | 2.39.5 | tentacle | `set expiry` applied over objects older than `DAYS` (sandbox objects were hours old; only its preview ran, read-only, on a live bucket) |
| [objects](./objects.md) | list, find, inspect, peek, download, presigned URL, public URL, upload, upload directory, copy, overwrite, delete, delete prefix, purge versions | 2026-11-06 | 2.39.5 | tentacle | none |
| [multipart-uploads](./multipart-uploads.md) | list unfinished, parts, abort | 2026-11-06 | 2.39.5 | tentacle | none |
