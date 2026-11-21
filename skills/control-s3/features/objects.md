# Objects

An object is a key and its bytes in one bucket. Keys look like paths (`crops/<uuid>.jpg`, `snapshots/2026-09.json`), but there are no directories: a "folder" is a key prefix ending in `/`, listed with a delimiter. Every existing bucket backs a live app, so writing to a key that exists overwrites what the app serves.

Commands: `aws s3api list-objects-v2`, `aws s3api head-object`, `aws s3 cp`, `aws s3 sync`, `aws s3 presign`, `aws s3 rm`, `s3.py purge-versions`.

## Operations

- `list` (read): keys and sub-prefixes under a prefix.
- `find` (read): keys under a prefix whose name matches.
- `inspect` (read): one object's size, type, ETag, date and metadata.
- `peek` (read): the first bytes of an object.
- `download` (read): an object into a local file.
- `presigned URL` (read): a time-limited GET link to a private object.
- `public URL` (read): the anonymous link for a public bucket.
- `upload` (write): a local file to a new key.
- `upload directory` (write): a local directory under a prefix.
- `copy` (write): an object to a new key, in the same or another bucket.
- `overwrite` (destructive): replace an existing key.
- `delete` (destructive): one object.
- `delete prefix` (destructive): every object under a prefix.
- `purge versions` (destructive): on a versioned bucket, every old version and delete marker under a prefix.

## Finding things

- `B`: [buckets](./buckets.md) `list`. `PREFIX`: walk down with `list`, starting from `""`; prefixes end in `/`.
- `K`: from `list` or `find`. `B2`/`K2`: the destination the user names.
- `FILE`, `DIR`, `OUT`: local paths. Put downloads in the scratchpad unless the user names a place.
- `NAME`: a substring to match in key names.

## Recipes with aws

### list (read)

```bash
aws --profile control-s3 s3api list-objects-v2 --bucket "$B" --prefix "$PREFIX" --delimiter / --max-items 50 --output json \
  | jq '{prefixes: [.CommonPrefixes[]?.Prefix], objects: [.Contents[]? | {key: .Key, size: .Size, modified: .LastModified}], more: (.NextToken != null)}'
```

Returns `{prefixes, objects: [{key, size, modified}], more}`. `more: true` means items were cut; raise `--max-items` or narrow `PREFIX`. Drop `--delimiter /` to list every key below the prefix.

### find (read)

```bash
aws --profile control-s3 s3api list-objects-v2 --bucket "$B" --prefix "$PREFIX" --max-items 5000 --output json \
  | jq --arg n "$NAME" '{matches: [.Contents[]? | select(.Key | contains($n)) | {key: .Key, size: .Size}][:50], scanned: (.Contents | length), more: (.NextToken != null)}'
```

Matching is client-side over the scanned keys. With `more: true`, a key past the first 5000 can still exist; narrow `PREFIX`.

### inspect (read)

```bash
aws --profile control-s3 s3api head-object --bucket "$B" --key "$K" --output json \
  | jq '{size: .ContentLength, type: .ContentType, etag: .ETag, modified: .LastModified, metadata: .Metadata}'
```

A missing key exits 254 with `(404) … Not Found`. An ETag with a `-<n>` suffix marks a multipart upload of n parts; it is not the file's MD5.

### peek (read)

```bash
aws --profile control-s3 s3 cp "s3://$B/$K" - | head -c 2000
```

### download (read)

```bash
aws --profile control-s3 s3 cp "s3://$B/$K" "$OUT" --no-progress --only-show-errors
```

Prints nothing on success; large objects download in parallel parts. A whole prefix: `aws --profile control-s3 s3 cp "s3://$B/$PREFIX" "$DIR" --recursive --no-progress --only-show-errors`.

### presigned URL (read)

```bash
aws --profile control-s3 s3 presign "s3://$B/$K" --expires-in 3600
```

Prints the URL. Anyone holding it can GET the object until it expires (at most 604800 s, 7 days): give it to the user in the conversation only. `presign` does not check the key exists; `inspect` it first.

### public URL (read)

`$S3_URL/$B/$K`, valid only when the bucket policy grants public read for that key: [bucket-settings](./bucket-settings.md) `policy`. Check: `curl -sS -o /dev/null -w '%{http_code}\n' "$S3_URL/$B/$K"` prints `200`, not `403`.

### upload (write)

```bash
aws --profile control-s3 s3 cp "$FILE" "s3://$B/$K" --no-overwrite --no-progress --only-show-errors
```

`--no-overwrite` makes RGW refuse an existing key, and the CLI then skips silently with exit 0, so the read-back is what tells you it landed. The content type is guessed from the extension; set it with `--content-type text/html` when the key has none or a browser must render it. Files over 8 MB go up as multipart automatically.

Read-back: `inspect` on `K`, whose `size` equals `wc -c < "$FILE"` and whose `modified` is now. An older `modified` or another size means the key already existed and nothing was written: that is an `overwrite`.

### upload directory (write)

Preview with `--dryrun`, which prints one `(dryrun) upload:` line per file:

```bash
aws --profile control-s3 s3 sync "$DIR" "s3://$B/$PREFIX" --dryrun | head -50
aws --profile control-s3 s3 sync "$DIR" "s3://$B/$PREFIX" --no-progress --only-show-errors
```

`sync` uploads files that are new or changed (by size and time) and overwrites changed ones: if the dry run lists keys that exist under `PREFIX` (check with `list`), treat it as an `overwrite`. Read-back: `list` on `PREFIX` without `--delimiter` shows every file. `sync --delete` also deletes remote keys missing locally: `delete prefix` rules apply.

### copy (write)

```bash
aws --profile control-s3 s3 cp "s3://$B/$K" "s3://$B2/$K2" --no-overwrite --no-progress
```

Prints `copy: s3://… to s3://…`, server-side, with nothing downloaded. Read-back: `inspect` on `B2`/`K2` shows the source's size. A move is a copy, then `delete` of the source.

### overwrite (destructive)

Preview: `inspect` on the existing key (size, type, modified) and `peek` if it is text, beside the replacement's size. After the user's yes, the `upload` command without `--no-overwrite`:

```bash
aws --profile control-s3 s3 cp "$FILE" "s3://$B/$K" --no-progress --only-show-errors
```

Read-back: `inspect` shows the new size and a fresh `modified`. Without versioning the old bytes are gone.

### delete (destructive)

Preview: `inspect` on the key. After the user's yes:

```bash
aws --profile control-s3 s3 rm "s3://$B/$K"
```

Prints `delete: s3://<B>/<K>`. Read-back: `inspect` exits 254 with `Not Found`.

### delete prefix (destructive)

Preview: `aws --profile control-s3 s3 rm "s3://$B/$PREFIX" --recursive --dryrun | head -50` (one `(dryrun) delete:` line per key) and [buckets](./buckets.md) `size` for the totals; show both to the user. After their yes:

```bash
aws --profile control-s3 s3 rm "s3://$B/$PREFIX" --recursive --only-show-errors
```

An empty `PREFIX` means the whole bucket. Read-back: `list` on `PREFIX` returns no objects. On a versioned bucket this only adds delete markers; the bytes stay as hidden versions until `purge versions`.

### purge versions (destructive)

Only for a bucket whose [buckets](./buckets.md) `info` shows `versioning: "Enabled"` or `"Suspended"`. Without `--yes` it previews: `{versions_and_markers, keys, sample, deleted: 0}`. Show that to the user; after their explicit yes, rerun with `--yes` appended.

```bash
uv run ~/.agents/skills/control-s3/scripts/s3.py purge-versions -b "$B" --prefix "$PREFIX"
```

This removes current versions too: everything under `PREFIX` is gone for good. Returns `deleted` and any per-key `errors`. Read-back: the preview again shows `versions_and_markers: 0`, and `info` shows `hidden_versions: 0` for a whole-bucket purge.

## Gotchas

- A missing key: `s3 cp` fails with `download failed: … (404) … Not Found`, `s3api get-object` crashes with `NoneType` (code `NoSuchKey`), and `s3 rm`, dry run included, reports `delete:` for a key that never existed. Test existence with `inspect`.
- Keys are case-sensitive and `/` in a key is only a character: `PREFIX="crops"` also matches `crops-old/…`; end prefixes in `/`.
- On a versioned bucket, `overwrite` and `delete` keep the old bytes as hidden versions that `list` and `size` do not show; `info`'s `hidden_versions` counts them (up to 1000).
- RGW stores no additional checksums: `head-object --checksum-mode ENABLED` returns none. Verify a download by size, or by `cmp` against the source.
