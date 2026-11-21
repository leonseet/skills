# Bucket settings

Per-bucket configuration that live apps depend on: CORS (browsers loading objects cross-origin), expiry rules (lifecycle rules that delete objects after N days), the bucket policy (anonymous public read), and versioning. Each setting is one document per bucket that a `put` replaces whole, so the script commands merge into it instead.

Commands: `aws s3api get-bucket-cors`, `put-bucket-cors`, `delete-bucket-cors`, `get-bucket-policy`, `delete-bucket-policy`, `get-bucket-versioning`, `put-bucket-versioning`, `s3.py bucket-info`, `s3.py set-expiry`, `s3.py remove-expiry`, `s3.py public-read`.

## Operations

- `show` (read): all settings of a bucket: [buckets](./buckets.md) `info`.
- `policy` (read): the full bucket policy document.
- `set CORS` (write, or destructive when the bucket already has CORS): set the CORS rules.
- `remove CORS` (destructive): browsers lose cross-origin access.
- `set expiry` (write, or destructive when existing objects would expire): add or replace one expiry rule.
- `remove expiry` (write): drop one expiry rule; objects then persist.
- `public read` (write): let anyone GET keys under a prefix.
- `remove policy` (destructive): revoke all public access.
- `enable versioning` (destructive): one-way; a bucket never returns to unversioned.

## Finding things

- `B`: [buckets](./buckets.md) `list`.
- Expiry rule `ID`: `expiry_rules[].ID` from `show`. Existing ids read `expire-after-<n>d`.
- `DAYS`, `PREFIX` (empty for the whole bucket): from the user.

## Recipes with aws

### policy (read)

```bash
aws --profile control-s3 s3api get-bucket-policy --bucket "$B" --output json | jq '.Policy | fromjson | .Statement'
```

Returns the statements, e.g. `[{"Sid":"PublicRead","Effect":"Allow","Principal":"*","Action":"s3:GetObject","Resource":"arn:aws:s3:::my-bucket/*"}]`. No policy at all fails with `(NoSuchBucketPolicy)`; `show` reports it as `policy: null`.

### set CORS (write)

Check `show` first: `cors: null` makes this a write. Existing rules make it an overwrite: show them to the user with the new ones and get their yes. The rules below are the store's usual read-only set.

```bash
CORS="$(cat <<'EOF'
{"CORSRules":[{"AllowedOrigins":["*"],"AllowedMethods":["GET","HEAD"],"AllowedHeaders":["*"],"MaxAgeSeconds":3600}]}
EOF
)"
aws --profile control-s3 s3api put-bucket-cors --bucket "$B" --cors-configuration "$CORS"
```

Prints nothing on success. Read-back: `aws --profile control-s3 s3api get-bucket-cors --bucket "$B" --output json | jq -c .CORSRules` returns the rules, and `curl -sSI -H 'Origin: https://example.org' "$S3_URL/$B/$K" | grep -i access-control` shows `Access-Control-Allow-Origin: *` for an existing `K` the request may read.

### remove CORS (destructive)

Preview: `show`'s `cors`, and which app loads this bucket from a browser. After the user's yes:

```bash
aws --profile control-s3 s3api delete-bucket-cors --bucket "$B"
```

Read-back: `show` returns `cors: null`.

### set expiry (write)

```bash
uv run ~/.agents/skills/control-s3/scripts/s3.py set-expiry -b "$B" --days "$DAYS" --prefix "$PREFIX"
```

Without `--yes` it only previews: `{rule, kept_rules, replaces_rule, scanned, scan_truncated, would_expire, would_expire_sample, applied: false}`. `would_expire: 0` with `scan_truncated: false` makes it a write: rerun with `--yes` appended. Anything else is destructive, because RGW deletes those objects on its next lifecycle pass: show the preview and get the user's yes before `--yes`. `--abort-uploads-days N` also aborts uploads left unfinished N days. The rule id defaults to `expire-[<prefix>-]after-<days>d`; the bucket's other rules are kept.

Read-back: `show`'s `expiry_rules` holds the rule. A whole-bucket rule comes back from RGW as `"Prefix": ""` rather than the `Filter` it was written with; a prefixed rule keeps its `Filter`.

### remove expiry (write)

```bash
uv run ~/.agents/skills/control-s3/scripts/s3.py remove-expiry -b "$B" --id "$ID"
```

Returns `{bucket, removed, kept_rules}`; with no rules left it deletes the lifecycle config. Read-back: `show`'s `expiry_rules` lacks the id.

### public read (write)

Everything under `PREFIX` (empty: the whole bucket) becomes readable by anyone with the URL. Confirm the user means public, not shared with one person (that is [objects](./objects.md) `presigned URL`).

```bash
uv run ~/.agents/skills/control-s3/scripts/s3.py public-read -b "$B" --prefix "$PREFIX"
```

Adds statement `PublicRead[-<Prefix>]` and keeps the policy's others; rerunning is a no-op. Returns `{bucket, sid, resource, statements, public_url}`. Read-back: `curl -sS -o /dev/null -w '%{http_code}\n' "$S3_URL/$B/$K"` prints `200` for a key under the prefix and `403` outside it.

### remove policy (destructive)

Preview: `policy`, and what serves those public URLs (explainer links, web players). After the user's yes:

```bash
aws --profile control-s3 s3api delete-bucket-policy --bucket "$B"
```

Read-back: `show` returns `policy: null`; the public URL returns `403`.

### enable versioning (destructive)

One-way: afterwards versioning can only be suspended, and every overwrite and delete keeps old versions that count against storage, stay hidden from listings, and block bucket deletion until [objects](./objects.md) `purge versions`. Preview: `show`'s `versioning`. After the user's yes:

```bash
aws --profile control-s3 s3api put-bucket-versioning --bucket "$B" --versioning-configuration Status=Enabled
```

Read-back: `aws --profile control-s3 s3api get-bucket-versioning --bucket "$B" --output json` returns `{"Status":"Enabled","MFADelete":"Disabled"}`.

## Gotchas

- `put-bucket-cors`, `put-bucket-policy` and `put-bucket-lifecycle-configuration` replace the whole document. Change expiry and public read only through the script commands, which merge.
- `get-bucket-versioning` on a never-versioned bucket prints nothing and exits 0.
