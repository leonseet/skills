# Multipart uploads

An upload over 8 MB goes up in parts (`aws s3 cp` does this on its own). An upload that is started and never completed or aborted leaves an **unfinished upload**: its parts hide from listings but still take storage, until someone aborts it or an `AbortIncompleteMultipartUpload` expiry rule clears it. An unfinished upload may also be an app's transfer still in progress.

Commands: `aws s3api list-multipart-uploads`, `aws s3api list-parts`, `aws s3api abort-multipart-upload`.

## Operations

- `list unfinished` (read): uploads started and not completed in a bucket.
- `parts` (read): the parts one upload has so far.
- `abort` (destructive): discard an upload and its parts.

## Finding things

- `B`: [buckets](./buckets.md) `list`; `info` reports `unfinished_uploads` per bucket.
- `K` and `UP` (the upload id): from `list unfinished`. The id is long; copy it from the JSON, never retype it.

## Recipes with aws

### list unfinished (read)

```bash
aws --profile control-s3 s3api list-multipart-uploads --bucket "$B" --max-uploads 50 --output json \
  | jq '[.Uploads[]? | {key: .Key, upload_id: .UploadId, initiated: .Initiated}]'
```

Returns `[{key, upload_id, initiated}]`; `[]` when there are none. An `initiated` within the last hours may be a transfer still running.

### parts (read)

```bash
aws --profile control-s3 s3api list-parts --bucket "$B" --key "$K" --upload-id "$UP" --max-items 100 --output json \
  | jq '{parts: [.Parts[]? | {n: .PartNumber, size: .Size, modified: .LastModified}], more: (.NextToken != null)}'
```

`parts: []` means nothing was sent after the upload started.

### abort (destructive)

Preview: `list unfinished` and `parts` for that upload, with its age; confirm no app is still sending it. After the user's yes:

```bash
aws --profile control-s3 s3api abort-multipart-upload --bucket "$B" --key "$K" --upload-id "$UP"
```

Prints nothing on success. Read-back: `list unfinished` no longer shows `UP`. To clear old ones on a schedule instead, [bucket-settings](./bucket-settings.md) `set expiry` with `--abort-uploads-days`.

## Gotchas

- `list-parts` on an aborted, completed or unknown upload id crashes with `NoneType`; the `--debug` code is `NoSuchKey` (RGW's answer, where AWS says `NoSuchUpload`).
- A killed `aws s3 cp` (Ctrl-C, OOM) can leave an unfinished upload behind.
