#!/usr/bin/env python3
# /// script
# requires-python = ">=3.9"
# dependencies = ["boto3"]
# ///
"""Read, write, and update objects in a SeaweedFS S3 bucket.

Env: S3_ENDPOINT_URL (required), AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY.
Run: uv run s3.py <buckets|ls|count|summary|exists|cat|get|put|cp|rm> [...]
"""

import argparse
import os
import sys

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError, EndpointConnectionError


def client():
    ep = os.environ.get("S3_ENDPOINT_URL")
    if not ep:
        sys.exit("Set S3_ENDPOINT_URL, e.g. http://localhost:8333")
    # SeaweedFS needs path-style; region is a placeholder, creds come from env.
    return boto3.client(
        "s3",
        endpoint_url=ep,
        region_name="us-east-1",
        config=Config(s3={"addressing_style": "path"}),
    )


def human(n):
    for u in ("B", "KiB", "MiB", "GiB", "TiB", "PiB"):
        if abs(n) < 1024 or u == "PiB":
            return f"{n} B" if u == "B" else f"{n:.1f} {u}"
        n /= 1024


def objects(c, bucket, prefix):
    pages = c.get_paginator("list_objects_v2").paginate(
        Bucket=bucket, Prefix=prefix or ""
    )
    for page in pages:
        yield from page.get("Contents", [])


# ---- read ----


def buckets(c, a):
    for b in c.list_buckets().get("Buckets", []):
        print(b["Name"])


def ls(c, a):
    n = 0
    for o in objects(c, a.bucket, a.prefix):
        print(f"{human(o['Size']):>12}  {o['Key']}")
        n += 1
        if a.limit and n >= a.limit:
            break


def count(c, a):
    n = t = 0
    for o in objects(c, a.bucket, a.prefix):
        n += 1
        t += o["Size"]
    print(f"s3://{a.bucket}/{a.prefix}  objects: {n:,}  size: {human(t)}")


def summary(c, a):
    g = {}
    for o in objects(c, a.bucket, a.prefix):
        top = o["Key"].split("/", 1)[0] if "/" in o["Key"] else "(root)"
        d = g.setdefault(top, [0, 0])
        d[0] += 1
        d[1] += o["Size"]
    for name, (n, b) in sorted(g.items(), key=lambda kv: kv[1][1], reverse=True):
        print(f"  {name + '/':<28}{n:>8,} objs  {human(b):>12}")
    print(
        f"  {'TOTAL':<28}{sum(v[0] for v in g.values()):>8,} objs  "
        f"{human(sum(v[1] for v in g.values())):>12}"
    )


def exists(c, a):
    keys = list(a.key)
    if a.keys_file:
        keys += [l.strip() for l in open(a.keys_file) if l.strip()]
    if not keys:
        sys.exit("Pass --key KEY (repeatable) or --keys-file FILE.")
    missing = 0
    for k in keys:
        try:
            h = c.head_object(Bucket=a.bucket, Key=k)
            print(f"[OK]      {k}  ({human(h['ContentLength'])})")
        except ClientError as e:
            if e.response["Error"]["Code"] in ("404", "NoSuchKey", "NotFound"):
                print(f"[MISSING] {k}")
                missing += 1
            else:
                raise
    sys.exit(1 if missing else 0)


def cat(c, a):
    body = c.get_object(Bucket=a.bucket, Key=a.key)["Body"].read()
    sys.stdout.buffer.write(body)


def get(c, a):
    dest = a.dest or os.path.basename(a.key)
    c.download_file(a.bucket, a.key, dest)
    print(f"downloaded s3://{a.bucket}/{a.key} -> {dest}")


# ---- write / update ----


def put(c, a):
    key = a.key or os.path.basename(a.file)
    c.upload_file(a.file, a.bucket, key)  # overwrites if key exists (= update)
    print(f"uploaded {a.file} -> s3://{a.bucket}/{key}")


def cp(c, a):
    c.copy_object(
        Bucket=a.dest_bucket or a.bucket,
        Key=a.dest_key,
        CopySource={"Bucket": a.bucket, "Key": a.key},
    )
    print(
        f"copied s3://{a.bucket}/{a.key} -> "
        f"s3://{a.dest_bucket or a.bucket}/{a.dest_key}"
    )


def rm(c, a):
    if a.prefix:
        keys = [o["Key"] for o in objects(c, a.bucket, a.prefix)]
        if not a.yes:
            sys.exit(
                f"Would delete {len(keys)} object(s) under {a.prefix} — "
                f"re-run with --yes to confirm."
            )
        for i in range(0, len(keys), 1000):
            c.delete_objects(
                Bucket=a.bucket,
                Delete={"Objects": [{"Key": k} for k in keys[i : i + 1000]]},
            )
        print(f"deleted {len(keys)} object(s) under s3://{a.bucket}/{a.prefix}")
    elif a.key:
        c.delete_object(Bucket=a.bucket, Key=a.key)
        print(f"deleted s3://{a.bucket}/{a.key}")
    else:
        sys.exit("Pass --key KEY or --prefix PREFIX.")


def main():
    p = argparse.ArgumentParser(description="SeaweedFS S3 operations.")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("buckets").set_defaults(fn=buckets)

    for name, fn in (("ls", ls), ("count", count), ("summary", summary)):
        s = sub.add_parser(name)
        s.add_argument("--bucket", required=True)
        s.add_argument("--prefix", default="")
        if name == "ls":
            s.add_argument("--limit", type=int, default=0)
        s.set_defaults(fn=fn)

    s = sub.add_parser("exists")
    s.add_argument("--bucket", required=True)
    s.add_argument("--key", action="append", default=[])
    s.add_argument("--keys-file")
    s.set_defaults(fn=exists)

    s = sub.add_parser("cat")
    s.add_argument("--bucket", required=True)
    s.add_argument("--key", required=True)
    s.set_defaults(fn=cat)

    s = sub.add_parser("get")
    s.add_argument("--bucket", required=True)
    s.add_argument("--key", required=True)
    s.add_argument("--dest")
    s.set_defaults(fn=get)

    s = sub.add_parser("put")
    s.add_argument("--bucket", required=True)
    s.add_argument("--file", required=True)
    s.add_argument("--key")
    s.set_defaults(fn=put)

    s = sub.add_parser("cp")
    s.add_argument("--bucket", required=True)
    s.add_argument("--key", required=True)
    s.add_argument("--dest-key", required=True)
    s.add_argument("--dest-bucket")
    s.set_defaults(fn=cp)

    s = sub.add_parser("rm")
    s.add_argument("--bucket", required=True)
    s.add_argument("--key")
    s.add_argument("--prefix")
    s.add_argument("--yes", action="store_true")
    s.set_defaults(fn=rm)

    a = p.parse_args()
    try:
        a.fn(client(), a)
    except EndpointConnectionError:
        sys.exit(
            f"Cannot reach {os.environ.get('S3_ENDPOINT_URL')} — is the gateway up?"
        )
    except ClientError as ex:
        sys.exit(f"S3 error: {ex.response['Error'].get('Code', '')}")


if __name__ == "__main__":
    main()
