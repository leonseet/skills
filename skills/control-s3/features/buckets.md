# Buckets

A bucket is a top-level namespace owned by one RGW user. A key lists and reaches only its own user's buckets, but bucket names are unique across the whole store, so a name another user holds cannot be created. Every existing bucket backs a live app.

Commands: `aws s3api list-buckets`, `aws s3api head-bucket`, `aws s3api create-bucket`, `aws s3 ls`, `aws s3 rb`, `s3.py bucket-info`.

## Operations

- `list` (read): the key's buckets.
- `info` (read): one bucket's settings and top level in one call.
- `size` (read): object count and bytes under a bucket or prefix.
- `create` (write): a new bucket.
- `delete` (destructive): remove a bucket, emptied first.

## Finding things

- `B`: from `list`. A bucket the user names but `list` lacks belongs to another RGW user's key, or does not exist.

## Recipes with aws

### list (read)

```bash
aws --profile control-s3 s3api list-buckets --output json | jq '{owner: .Owner.ID, buckets: [.Buckets[] | {name: .Name, created: .CreationDate[:10]}]}'
```

Returns `{owner, buckets: [{name, created}]}`. `owner` is the RGW user the key belongs to.

### info (read)

```bash
uv run ~/.agents/skills/control-s3/scripts/s3.py bucket-info "$B"
```

Returns `{bucket, versioning, hidden_versions, cors, expiry_rules, policy, public_urls, unfinished_uploads, top_prefixes, top_keys, top_truncated}`. `hidden_versions` counts old versions and delete markers (first 1000 listed) on a versioned bucket, `null` on one never versioned. `public_urls` holds one pattern per anonymous-read grant (`$S3_URL/<bucket>/<prefix>/<key>`); `[]` means private. A setting that was never made is `null` (`versioning: "never enabled"`); the plain `get-bucket-*` commands crash on those instead (SKILL.md, Gotchas). Exits 1 with `no bucket <B> for this key` when the key cannot see it.

### size (read)

```bash
aws --profile control-s3 s3 ls "s3://$B/$PREFIX" --recursive --summarize | tail -2
```

Prints `Total Objects: <n>` and `Total Size: <bytes>`. It lists every key under the prefix, so on a large bucket narrow `PREFIX` first and expect it to take a while.

### create (write)

Check the name is free for this key first: `aws --profile control-s3 s3api head-bucket --bucket "$B"` must exit 254 with `(404) … Not Found`. RGW answers `create-bucket` on a bucket the key already owns with a silent success, so the create alone proves nothing.

```bash
aws --profile control-s3 s3api create-bucket --bucket "$B"
```

Prints nothing on success. A name another RGW user holds fails with `(BucketAlreadyExists)`. New buckets are private, with no CORS, expiry or versioning. Read-back: `list` shows `B`, and `info` returns its empty settings.

### delete (destructive)

Preview first and show it to the user: `info` and `size` on the bucket. `aws s3 rb` has no dry run. After the user's explicit yes, empty the bucket: [objects](./objects.md) `delete prefix` with an empty `PREFIX`, then `purge versions` if `info` shows versioning, then `abort` each of its [unfinished uploads](./multipart-uploads.md). Then:

```bash
aws --profile control-s3 s3 rb "s3://$B"
```

Prints `remove_bucket: <B>`. A bucket still holding objects, hidden versions or unfinished uploads fails with `remove_bucket failed: … NoneType …` (code `BucketNotEmpty`), even when `list` and `size` show it empty. Read-back: `head-bucket` exits 254 with `Not Found`.

## Gotchas

- `head-bucket` and `create-bucket` print nothing on success; read their exit codes.
- Bucket names are global: once another RGW user takes a name, this key can neither create nor see it.
