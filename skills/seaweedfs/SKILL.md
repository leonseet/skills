---
name: seaweedfs
description: Read, write, update, and inspect objects in SeaweedFS via its S3 gateway using a standalone uv-run script. Use this skill whenever the user wants to do anything with their S3 / SeaweedFS object storage — list buckets or objects, check whether keys exist, count objects or sizes, download or print an object, upload or overwrite files, copy objects, delete keys or prefixes, or verify that a pipeline wrote its outputs. Trigger even when the user just says "S3" or "my bucket" — their S3 is a SeaweedFS gateway, not AWS, so use this rather than assuming AWS defaults.
---

# SeaweedFS S3 operations

Work with a SeaweedFS S3 bucket. SeaweedFS is S3-compatible but not AWS: the
script uses path-style addressing, a placeholder region, and static keys from
the SeaweedFS S3 config — not IAM. Prefer this over hand-writing boto3 or a
generic AWS S3 skill.

`scripts/s3.py` is self-contained with its dependency (boto3) declared inline,
so it runs under `uv` with nothing to install or maintain.

## Setup

Set the connection env vars, then run with `uv run`. If `S3_ENDPOINT_URL` is
missing, ask the user for it rather than guessing.

```bash
export S3_ENDPOINT_URL=http://<seaweedfs-host>:8333   # required
export AWS_ACCESS_KEY_ID=<access-key>                 # from SeaweedFS s3 config
export AWS_SECRET_ACCESS_KEY=<secret-key>
```

## Read / inspect

```bash
uv run scripts/s3.py buckets                                  # list buckets
uv run scripts/s3.py ls --bucket B --prefix emb/ --limit 50   # list objects + sizes
uv run scripts/s3.py count --bucket B --prefix detections/    # object count + total size
uv run scripts/s3.py summary --bucket B                       # count/size per top-level prefix
uv run scripts/s3.py exists --bucket B --key a.npy --key b.npy   # or --keys-file FILE
uv run scripts/s3.py cat --bucket B --key manifest.json       # print object to stdout
uv run scripts/s3.py get --bucket B --key emb/x.npy --dest ./x.npy   # download
```

`exists` exits 1 if any key is missing, so it can gate a pipeline step.
Counts use paginated `ListObjectsV2` and are exact past 1000 objects.

## Write / update

```bash
uv run scripts/s3.py put --bucket B --file ./report.pdf --key docs/report.pdf
uv run scripts/s3.py cp  --bucket B --key a.txt --dest-key b.txt [--dest-bucket B2]
```

`put` to an existing key overwrites it — that is how you update an object in
S3; there is no partial in-place edit. To modify a file: `get`, edit locally,
`put` back to the same key. `cp` is a server-side copy (no download).

## Delete

```bash
uv run scripts/s3.py rm --bucket B --key old/file.txt
uv run scripts/s3.py rm --bucket B --prefix tmp/ --yes
```

Prefix deletes refuse to run without `--yes` and first report how many objects
would be removed — always show the user that count before confirming.

## SeaweedFS notes

- ETag is the MD5 only for single-part uploads; multipart yields a composite
  value. Don't treat ETag as a content hash for large objects.
- Versioning is off by default — deletes and overwrites are permanent.
