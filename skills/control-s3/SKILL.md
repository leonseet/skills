---
name: control-s3
description: "Operate an S3-compatible object store (the one S3_ENDPOINT_URL names; proven on Ceph RGW) through the aws CLI: buckets, bucket settings (CORS, expiry rules, public-read policy, versioning), objects (list, inspect, download, upload, copy, sync, presigned and public URLs, delete) and unfinished multipart uploads. Use whenever a task reads or changes anything in that store."
---

# Control S3

The store is the S3-compatible endpoint `S3_ENDPOINT_URL` names (proven on a Ceph Object Gateway, release `tentacle`). Every operation goes through AWS CLI v2 with the profile `control-s3`: `aws --profile control-s3 s3 …` for transfers, `aws --profile control-s3 s3api …` for everything else. `scripts/s3.py` holds `doctor`, the profile setup, and the chains plain commands make clumsy.

## Setup

A new machine needs, in this order (`doctor` checks each and prints the fix for what is missing):

1. `uv`: `curl -LsSf https://astral.sh/uv/install.sh | sh`. `doctor` and the profile's credential hook run on it.
2. AWS CLI v2. macOS: `brew install awscli`. Linux, into the home directory with no sudo (`aarch64` in place of `x86_64` on ARM):
   ```bash
   D=$(mktemp -d) && curl -sSo "$D/a.zip" https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip \
     && unzip -q "$D/a.zip" -d "$D" && "$D/aws/install" -i ~/.local/aws-cli -b ~/.local/bin
   ```
   `~/.local/bin` must be on `PATH`.
3. `jq`: `sudo apt install jq` on Linux, `brew install jq` on macOS.
4. `S3_ENDPOINT_URL`: the store's URL (`https://<host>`). The skill carries no default. The script reads it from the current repo's `.env` first, then the shell. When both lack it, ask the user; they put it in the repo's `.env` beside the key, or export it in their shell's startup file (`~/.bashrc`, `~/.zshrc`) for every repo.
5. Credentials: a user's S3 key in `S3_ACCESS_KEY` and `S3_SECRET_KEY`, read from the same two places by the profile's credential hook. Whoever administers the store issues it; the user writes it in themselves. Nothing is copied into `~/.aws`; the key stays where the user put it.
6. A reachable, trusted host. `doctor` connects to the endpoint's host. An internal host answers only on the network or VPN that serves it. The AWS CLI ships its own CA list and ignores the OS trust store (`SSL validation failed … CERTIFICATE_VERIFY_FAILED` on a private CA), so the profile hands it a `ca_bundle`: the PEM file `CONTROL_CA_FILE` names when set (read like the endpoint), else the Linux system bundle, which holds any CA added to the OS store. On macOS a private CA always needs `CONTROL_CA_FILE`: the CLI cannot read the Keychain.
7. Profile: `uv run ~/.agents/skills/control-s3/scripts/s3.py setup-profile` writes `[profile control-s3]` into `~/.aws/config`: `endpoint_url`, `region`, `ca_bundle`, and a `credential_process` that calls the script. Ask the user before running it: it changes only that section, but it rewrites the whole file, so comments elsewhere in `~/.aws/config` are lost. Run it again after the endpoint or the CA file changes; `doctor` says when.

## Doctor

```bash
uv run ~/.agents/skills/control-s3/scripts/s3.py doctor
```

One `ok`/`WARN`/`FAIL` line each: uv, aws and its version, jq, `S3_ENDPOINT_URL` and where it came from, the host (reachable, certificate trusted through the bundle aws will use), the `control-s3` profile, shell variables that would override it, credentials and where they came from; then auth (the user and its bucket count) and, on Ceph, the release against the one this map was proven on. Every `FAIL` has a `fix:` line under it. Run it first, and again whenever a command fails strangely.

On a `FAIL`, stop the task and walk the user through the `fix:` lines one at a time, offering to run each fix yourself; then rerun `doctor` until it is clean. Install commands and other system changes run only after the user's yes. The user writes keys into `.env` or their shell themselves, never into the chat. A `FAIL host` that says unreachable is usually a VPN that is down: say so and let the user connect. A `FAIL` with no fix you can apply is reported to the user, never worked around. A version `WARN` means a recipe may have drifted: check its `help`.

## Instances & conventions

- **One store** per `S3_ENDPOINT_URL`, addressed path-style (`$S3_URL/<bucket>/<key>`); the profile's region name is a placeholder (`us-east-1`). `S3_URL=$(uv run ~/.agents/skills/control-s3/scripts/s3.py endpoint)` where a recipe builds a public URL.
- **A key is one user of the store.** It sees only that user's buckets; `doctor` names the user. The profile follows whichever key and endpoint the current repo's `.env` holds, so run commands from inside that repo.
- **Instance notes**: `~/.config/control-s3/instance.md`, this machine's notes on the store: which key is which user, what each bucket is for, which are public. Read it before the first recipe when it exists. For what it lacks, observe the store, then ask the user, and offer to record their answer there (names and conventions, never secrets).
- **Treat every bucket as backing a live app.** Outside the sandbox, write only to the bucket and keys the user named, and treat overwriting an existing key as destructive.
- **Public buckets** carry a `PublicRead` bucket-policy statement; their objects load anonymously at the public URL. Everything else needs the key or a presigned URL.
- **Recipe variables**: `B` bucket, `K` key, `PREFIX` key prefix ending in `/`, `FILE` local file to upload, `OUT` local download path, `DIR` local directory, `B2`/`K2` copy destination. Each feature's `Finding things` says how to get them.
- **Sandbox**: bucket `control-s3-sandbox`, owned by the current key's user, with a 1-day expiry on every object and on unfinished uploads. When [buckets](features/buckets.md) `list` lacks it, tell the user you will create it under that user and wait for their yes. Prove new write recipes there.

## Safety

Every operation in `features/` is tagged:

- **read**: run freely.
- **write**: run when the user asked for that change, then run the recipe's read-back and report what it shows.
- **destructive** (delete, overwrite, revoke access, schedule expiry over existing objects): show the user exactly what goes, using the recipe's preview, and run it only after their explicit yes in the conversation.

S3 keys never appear in your output, files, commits or messages. A presigned URL is a bearer credential until it expires: give it to the user in the conversation only, never in files, commits or shared messages.

## Operate

Read [`features/README.md`](features/README.md): the common-task chains, then one recipe file per resource area.

## Output shaping

Keep calls few and output small:

- `s3api` commands take `--output json`, piped to a `jq` projection of the fields the task needs. `s3` transfer commands take `--no-progress --only-show-errors`.
- Every listing sets `--max-items <n>`. Without it the CLI pages through the whole bucket.
- Read big objects in part: `aws --profile control-s3 s3 cp "s3://$B/$K" - | head -c 2000`. Fetch a whole object only into a file.

## Gotchas

- `aws: [ERROR]: argument of type 'NoneType' is not a container or iterable` means RGW returned an error with an empty message, which crashes the CLI's error printer; exit code 255. The real code: rerun with `--debug 2>&1 | grep -o '<Code>[^<]*</Code>' | tail -1` (`NoSuchKey`, `NoSuchBucket`, `NoSuchCORSConfiguration`, `PreconditionFailed`, …). HEAD requests (`head-object`, `head-bucket`) print a plain `404`.
- `Error when retrieving credentials from custom-process: control-s3: no S3 key` means the current directory is not inside a repo whose `.env` holds the key, and the shell does not either. `cd` into that repo, or run `doctor` there.
- `AWS_ENDPOINT_URL`, `AWS_ENDPOINT_URL_S3` or `AWS_CA_BUNDLE` set in the shell override the profile; `doctor` warns. `AWS_ACCESS_KEY_ID` in the shell is ignored while `--profile` is given.
