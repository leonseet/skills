# /// script
# requires-python = ">=3.11"
# dependencies = ["typer>=0.12", "python-dotenv>=1.0", "truststore>=0.10"]
# ///
"""control-s3 helpers: doctor, the `control-s3` AWS profile, and chains over the aws CLI. aws stays the main interface.

Run as: uv run ~/.agents/skills/control-s3/scripts/s3.py <command>
"""

from __future__ import annotations

import configparser
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional
import ssl
from urllib.parse import urlparse

import typer
from dotenv import dotenv_values

SERVICE = "s3"
# Where the store lives: a setting, read from the current repo's .env first, then the shell. No default.
URL_VAR = "S3_ENDPOINT_URL"
PROFILE = "control-s3"
# Optional: a PEM file holding a private CA. Shared by every control skill.
CA_VAR = "CONTROL_CA_FILE"
# Linux system bundles, which hold whatever CA was added to the OS store. The aws CLI ignores them unless told.
SYSTEM_BUNDLES = ["/etc/ssl/certs/ca-certificates.crt", "/etc/pki/tls/certs/ca-bundle.crt", "/etc/ssl/ca-bundle.pem"]
# Versions the last proof ran against. doctor warns when the installed ones differ.
PROVEN = {"cli": "2.39.5", "service": "tentacle"}
# Credential variables. Names only, never values.
CREDENTIALS = ["S3_ACCESS_KEY", "S3_SECRET_KEY"]
SCRIPT = Path(__file__).resolve()

app = typer.Typer(no_args_is_help=True, add_completion=False)


# --- helpers --------------------------------------------------------------


def repo_env_path() -> Optional[Path]:
    try:
        root = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True, check=True
        ).stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None
    path = Path(root) / ".env"
    return path if path.exists() else None


def setting(name: str) -> tuple[Optional[str], str]:
    """(value, source): the current repo's .env first, then the shell."""
    path = repo_env_path()
    if path:
        value = dotenv_values(path).get(name)
        if value:
            return value, f"repo .env ({path})"
    value = os.environ.get(name)
    return (value, "shell environment") if value else (None, "not in the current repo's .env or the shell")


def endpoint() -> str:
    value, source = setting(URL_VAR)
    if not value:
        typer.echo(f"control-s3: {URL_VAR} {source}; run `doctor` for the fix", err=True)
        raise typer.Exit(2)
    return (value if "://" in value else f"https://{value}").rstrip("/")


def ca_bundle() -> Optional[str]:
    """The CA list handed to the aws CLI: CONTROL_CA_FILE when set, else the Linux system bundle, else None
    (macOS: the CLI's own public roots)."""
    ca = setting(CA_VAR)[0]
    if ca:
        return str(Path(ca).expanduser())
    return next((b for b in SYSTEM_BUNDLES if Path(b).is_file()), None)


def find_credentials() -> tuple[Optional[dict[str, str]], str]:
    """(values, source): each of the key's two variables from the current repo's .env first, then the shell."""
    found = {n: setting(n) for n in CREDENTIALS}
    if all(v for v, _ in found.values()):
        return {n: v for n, (v, _) in found.items()}, found[CREDENTIALS[0]][1]  # type: ignore[misc]
    return None, f"{' and '.join(n for n, (v, _) in found.items() if not v)} not in the current repo's .env or the shell"


def config_path() -> Path:
    return Path(os.environ.get("AWS_CONFIG_FILE", Path.home() / ".aws" / "config"))


def profile_settings() -> dict[str, str]:
    """What the `control-s3` profile must hold for the endpoint and CA in force now."""
    uv = shutil.which("uv") or "uv"
    return {
        "endpoint_url": endpoint(),
        "region": "us-east-1",
        **({"ca_bundle": ca_bundle()} if ca_bundle() else {}),
        "credential_process": f"{uv} run --quiet {SCRIPT} credential-process",
    }


def aws(*argv: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["aws", "--profile", PROFILE, *argv], capture_output=True, text=True)


def error_code(argv: tuple[str, ...], proc: subprocess.CompletedProcess[str]) -> str:
    """The S3 error code. RGW sends an empty <Message>, which crashes aws's error printer; --debug still shows <Code>."""
    m = re.search(r"An error occurred \(([^)]+)\)", proc.stderr)
    if m:
        return m.group(1)
    dbg = aws(*argv, "--debug").stderr
    codes = re.findall(r"<Code>([^<]+)</Code>", dbg)
    return codes[-1] if codes else proc.stderr.strip()[-300:]


def aws_json(*argv: str, missing_ok: tuple[str, ...] = ()) -> Any:
    """Run aws with JSON output. An error whose code is in missing_ok returns None; any other error exits."""
    proc = aws(*argv, "--output", "json")
    if proc.returncode != 0:
        code = error_code(argv, proc)
        if code in missing_ok:
            return None
        typer.echo(f"aws {' '.join(argv[:2])} failed: {code}", err=True)
        raise typer.Exit(proc.returncode or 1)
    return json.loads(proc.stdout) if proc.stdout.strip() else {}


def emit(data: Any) -> None:
    typer.echo(json.dumps(data, separators=(",", ":"), default=str))


def line(status: str, check: str, detail: str = "") -> bool:
    typer.echo(f"{status:<4} {check}" + (f"  {detail}" if detail else ""))
    return status != "FAIL"


def fix(text: str) -> None:
    """The step that clears the FAIL above, printed under it."""
    typer.echo(f"     fix: {text}")


STARTUP = "the shell's startup file (~/.bashrc, ~/.zshrc)"
JQ_FIX = "`brew install jq` (macOS) or `sudo apt install jq` (Debian/Ubuntu; other Linux: your package manager)"
NET_FIX = (
    "this machine cannot reach {host}. Check that the address in {source} is right; when the service is internal, "
    "the user connects to the network or VPN that serves it, then rerun doctor"
)
TLS_FIX = (
    "{host} presents a certificate signed by a CA this machine does not trust, typically an organisation's private CA. "
    "The user gets that CA's root certificate as a PEM file from whoever runs the service, or copies it from a machine "
    "that already trusts it, then does one of: (a) set CONTROL_CA_FILE=/path/to/ca.pem in the repo .env or "
    + STARTUP + ", then rerun `setup-profile`, so only the control skills trust it; (b) add it to the OS trust store, so every tool does (Linux only: the aws CLI cannot read the macOS Keychain): "
    "Debian/Ubuntu `sudo cp ca.pem /usr/local/share/ca-certificates/<name>.crt && sudo update-ca-certificates`, "
    "macOS `sudo security add-trusted-cert -d -r trustRoot -k /Library/Keychains/System.keychain ca.pem`. "
    "Certificate verification stays on"
)


def host_check(url: str) -> tuple[str, str]:
    """('ok' | 'tls' | 'net', detail): connect to the endpoint's host and verify its certificate against the
    CA list the aws CLI will be handed."""
    import socket

    u = urlparse(url)
    host, port = u.hostname or "", u.port or (443 if u.scheme == "https" else 80)
    bundle = ca_bundle()
    try:
        with socket.create_connection((host, port), timeout=10) as sock:
            if u.scheme != "https":
                return "ok", f"{host}:{port} reachable"
            if bundle:
                ctx = ssl.create_default_context(cafile=bundle)
            else:
                import truststore

                ctx = truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
            with ctx.wrap_socket(sock, server_hostname=host):
                return "ok", f"{host}:{port} reachable, certificate trusted" + (f" through {bundle}" if bundle else "")
    except (ssl.SSLCertVerificationError, FileNotFoundError) as e:
        return "tls", f"{host}:{port}: {str(e)[:200]}"
    except Exception as e:  # noqa: BLE001  DNS, refused, timeout
        return "net", f"{host}:{port}: {type(e).__name__}: {str(e)[:200]}"


def server_release() -> Optional[str]:
    import urllib.request

    try:
        with urllib.request.urlopen(urllib.request.Request(endpoint(), method="HEAD"), timeout=10, context=ssl.create_default_context(cafile=ca_bundle())) as r:
            server = r.headers.get("Server", "")
    except Exception as e:  # noqa: BLE001
        server = getattr(e, "headers", {}).get("Server", "") if hasattr(e, "headers") else ""
    m = re.search(r"Ceph Object Gateway \(([^)]+)\)", server or "")
    return m.group(1) if m else None


# --- doctor ---------------------------------------------------------------


@app.command()
def doctor() -> None:
    """Read-only: one ok/WARN/FAIL line per check, a `fix:` line under each FAIL. Exit 1 on any FAIL."""
    ok = True
    line("ok", "uv", shutil.which("uv") or "running")

    exe = shutil.which("aws")
    ok &= line("ok" if exe else "FAIL", "aws", exe or "not on PATH")
    if not exe:
        fix('macOS: `brew install awscli`. Linux, AWS CLI v2 into the home directory, no sudo (aarch64 for x86_64 on ARM): `D=$(mktemp -d) && curl -sSo "$D/a.zip" '
            "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip && unzip -q \"$D/a.zip\" -d \"$D\" && "
            '"$D/aws/install" -i ~/.local/aws-cli -b ~/.local/bin` (~/.local/bin must be on PATH)')
    else:
        out = subprocess.run(["aws", "--version"], capture_output=True, text=True).stdout
        m = re.search(r"aws-cli/(\d+\.\d+\.\d+)", out)
        cli = m.group(1) if m else "unknown"
        if not cli.startswith("2."):
            ok &= line("FAIL", "aws version", f"{cli}: this map is for AWS CLI v2")
            fix("install AWS CLI v2 with the command above; v1 lacks `s3 cp --no-overwrite` and reads config differently")
        else:
            line("ok" if cli == PROVEN["cli"] else "WARN", "aws version", f"{cli} (proven {PROVEN['cli']})")

    jq = shutil.which("jq")
    ok &= line("ok" if jq else "FAIL", "jq", jq or "not on PATH (recipes pipe aws output through jq)")
    if not jq:
        fix(JQ_FIX)

    url, url_source = setting(URL_VAR)
    ok &= line("ok" if url else "FAIL", URL_VAR, f"{url} ({url_source})" if url else url_source)
    if not url:
        fix(f"ask the user for their store's endpoint (https://<host>). They add {URL_VAR}=… to the current repo's .env "
            f"beside the key, or `export {URL_VAR}=…` to {STARTUP} for every repo")
        typer.echo("skip host, profile, credentials and auth checks until the FAILs above are fixed; then rerun doctor")
        sys.exit(1)
    kind, detail = host_check(endpoint())
    ok &= line("ok" if kind == "ok" else "FAIL", "host", detail)
    if kind == "tls":
        fix(TLS_FIX.format(host=urlparse(endpoint()).hostname))
    elif kind == "net":
        fix(NET_FIX.format(host=urlparse(endpoint()).hostname, source=f"{URL_VAR} ({url_source})"))

    cfg = configparser.RawConfigParser()
    cfg.read(config_path())
    want = profile_settings()
    section = f"profile {PROFILE}"
    have = dict(cfg[section]) if cfg.has_section(section) else {}
    wrong = [k for k in ("endpoint_url", "region", "ca_bundle") if have.get(k) != want.get(k)]
    cp = have.get("credential_process", "").split()
    # Any working uv may run the hook; the script path and command must match.
    if not (cp and Path(cp[0]).exists() and " ".join(cp[1:]) == want["credential_process"].split(" ", 1)[1]):
        wrong.append("credential_process")
    ok &= line("ok" if not wrong else "FAIL", f"profile {PROFILE}",
               str(config_path()) if not wrong else f"{config_path()}: {'missing' if not have else 'differs in ' + ', '.join(wrong)}")
    if wrong:
        fix(f"uv run {SCRIPT} setup-profile   (writes only the [{section}] section; ask the user first)")

    for var in ("AWS_ENDPOINT_URL", "AWS_ENDPOINT_URL_S3", "AWS_CA_BUNDLE"):
        if os.environ.get(var):
            line("WARN", var, "set in the shell; it overrides the profile, so commands may reach another store")

    creds, source = find_credentials()
    ok &= line("ok" if creds else "FAIL", "credentials", source if creds else source)
    if not creds:
        fix("the user adds S3_ACCESS_KEY=… and S3_SECRET_KEY=… (a user's S3 key, from whoever administers the store) "
            f"to the current repo's .env themselves, beside {URL_VAR}; never into the chat")

    if not ok:
        typer.echo("skip auth and service version checks until the FAILs above are fixed; then rerun doctor")
        sys.exit(1)

    proc = aws("s3api", "list-buckets", "--output", "json")
    if proc.returncode == 0:
        data = json.loads(proc.stdout)
        line("ok", "auth", f"user {data.get('Owner', {}).get('ID', '?')}, {len(data.get('Buckets', []))} buckets")
    else:
        code = error_code(("s3api", "list-buckets"), proc)
        ok &= line("FAIL", "auth", code)
        fix("InvalidAccessKeyId or SignatureDoesNotMatch: the key in the credentials source above is wrong or revoked; "
            "the user replaces it there themselves")

    rel = server_release()
    if rel:
        line("ok" if rel == PROVEN["service"] else "WARN", "ceph release", f"{rel} (proven {PROVEN['service']})")
    else:
        line("WARN", "store", f"not a Ceph Object Gateway, or it hides its release; this map was proven on Ceph {PROVEN['service']}")
    sys.exit(0 if ok else 1)


# --- profile and credentials ---------------------------------------------


@app.command("setup-profile")
def setup_profile() -> None:
    """Write. Create or correct the [profile control-s3] section of ~/.aws/config; other sections are kept as they are."""
    path = config_path()
    cfg = configparser.RawConfigParser()
    cfg.read(path)
    section = f"profile {PROFILE}"
    if not cfg.has_section(section):
        cfg.add_section(section)
    for k, v in profile_settings().items():
        cfg.set(section, k, v)
    if "ca_bundle" not in profile_settings():
        cfg.remove_option(section, "ca_bundle")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as f:
        cfg.write(f)
    emit({"written": str(path), "section": section, "keys": list(profile_settings())})


@app.command("endpoint")
def endpoint_cmd() -> None:
    """Read. Print the store's endpoint URL, which recipes use as `S3_URL`."""
    typer.echo(endpoint())


@app.command("credential-process", hidden=True)
def credential_process() -> None:
    """Called by the aws CLI through the profile's credential_process; its stdout goes to aws only."""
    creds, source = find_credentials()
    if not creds:
        typer.echo(f"control-s3: no S3 key: {source}. Run `uv run {SCRIPT} doctor` for the fix.", err=True)
        raise typer.Exit(1)
    emit({"Version": 1, "AccessKeyId": creds["S3_ACCESS_KEY"], "SecretAccessKey": creds["S3_SECRET_KEY"]})


# --- bucket chains --------------------------------------------------------


@app.command("bucket-info")
def bucket_info(bucket: str = typer.Argument(..., help="Bucket name.")) -> None:
    """Read. A bucket's settings in one JSON object: versioning, CORS, expiry rules, policy, unfinished uploads, top-level prefixes."""
    head = aws_json("s3api", "head-bucket", "--bucket", bucket, missing_ok=("404", "NoSuchBucket"))
    if head is None:
        typer.echo(f"no bucket {bucket} for this key", err=True)
        raise typer.Exit(1)
    ver = aws_json("s3api", "get-bucket-versioning", "--bucket", bucket)
    cors = aws_json("s3api", "get-bucket-cors", "--bucket", bucket, missing_ok=("NoSuchCORSConfiguration",))
    life = aws_json("s3api", "get-bucket-lifecycle-configuration", "--bucket", bucket,
                    missing_ok=("NoSuchLifecycleConfiguration",))
    pol = aws_json("s3api", "get-bucket-policy", "--bucket", bucket, missing_ok=("NoSuchBucketPolicy",))
    statements = json.loads(pol["Policy"])["Statement"] if pol else []
    public = []
    for s in statements:
        actions = s.get("Action") if isinstance(s.get("Action"), list) else [s.get("Action")]
        if s.get("Effect") == "Allow" and s.get("Principal") in ("*", {"AWS": "*"}) and \
                any(a in ("s3:GetObject", "s3:*") for a in actions):
            for res in s["Resource"] if isinstance(s["Resource"], list) else [s["Resource"]]:
                public.append(f"{endpoint()}/" + res.removeprefix("arn:aws:s3:::").removesuffix("*") + "<key>")
    ups = aws_json("s3api", "list-multipart-uploads", "--bucket", bucket, "--max-uploads", "100")
    top = aws_json("s3api", "list-objects-v2", "--bucket", bucket, "--delimiter", "/", "--max-items", "50")
    hidden = None
    if (ver or {}).get("Status"):
        vers = aws_json("s3api", "list-object-versions", "--bucket", bucket, "--max-items", "1000")
        hidden = len([v for v in vers.get("Versions") or [] if not v.get("IsLatest")]) + len(vers.get("DeleteMarkers") or [])
    emit({
        "bucket": bucket,
        "versioning": (ver or {}).get("Status", "never enabled"),
        "hidden_versions": hidden,
        "cors": (cors or {}).get("CORSRules"),
        "expiry_rules": (life or {}).get("Rules"),
        "policy": statements or None,
        "public_urls": public,
        "unfinished_uploads": len((ups or {}).get("Uploads") or []),
        "top_prefixes": [p["Prefix"] for p in top.get("CommonPrefixes") or []],
        "top_keys": [o["Key"] for o in top.get("Contents") or []][:20],
        "top_truncated": bool(top.get("NextToken")),
    })


def rule_prefix(rule: dict) -> str:
    return (rule.get("Filter") or {}).get("Prefix", rule.get("Prefix", ""))


@app.command("set-expiry")
def set_expiry(
    bucket: str = typer.Option(..., "--bucket", "-b"),
    days: int = typer.Option(..., help="Delete objects this many days after they were written."),
    prefix: str = typer.Option("", help="Only keys under this prefix. Default: the whole bucket."),
    rule_id: Optional[str] = typer.Option(None, "--id", help="Rule id. Default: expire-<prefix>-after-<days>d."),
    abort_uploads_days: Optional[int] = typer.Option(None, help="Also abort multipart uploads left unfinished this many days."),
    scan: int = typer.Option(5000, help="Objects to scan for the would_expire preview."),
    yes: bool = typer.Option(False, "--yes", help="Apply. Without it, only the preview is printed."),
) -> None:
    """Write or destructive. Add or replace one expiry rule; the bucket's other rules are kept. Preview by default."""
    rid = rule_id or f"expire-{prefix.strip('/').replace('/', '-') + '-' if prefix else ''}after-{days}d"
    life = aws_json("s3api", "get-bucket-lifecycle-configuration", "--bucket", bucket,
                    missing_ok=("NoSuchLifecycleConfiguration",))
    rules = [r for r in (life or {}).get("Rules", []) if r.get("ID") != rid]
    new: dict[str, Any] = {"ID": rid, "Filter": {"Prefix": prefix}, "Status": "Enabled", "Expiration": {"Days": days}}
    if abort_uploads_days:
        new["AbortIncompleteMultipartUpload"] = {"DaysAfterInitiation": abort_uploads_days}
    rules.append(new)
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    listing = aws_json("s3api", "list-objects-v2", "--bucket", bucket, "--prefix", prefix, "--max-items", str(scan))
    objs = listing.get("Contents") or []
    old = [o for o in objs if datetime.fromisoformat(o["LastModified"]) < cutoff]
    preview = {
        "bucket": bucket, "rule": new, "kept_rules": [r.get("ID") for r in rules[:-1]],
        "replaces_rule": any(r.get("ID") == rid for r in (life or {}).get("Rules", [])),
        "scanned": len(objs), "scan_truncated": bool(listing.get("NextToken")),
        "would_expire": len(old), "would_expire_sample": [o["Key"] for o in old[:10]],
        "applied": False,
    }
    if yes:
        body = json.dumps({"Rules": rules})
        aws_json("s3api", "put-bucket-lifecycle-configuration", "--bucket", bucket, "--lifecycle-configuration", body)
        preview["applied"] = True
    emit(preview)


@app.command("remove-expiry")
def remove_expiry(
    bucket: str = typer.Option(..., "--bucket", "-b"),
    rule_id: str = typer.Option(..., "--id", help="The rule id, from bucket-info's expiry_rules."),
) -> None:
    """Write. Remove one expiry rule and keep the others; with none left, the lifecycle config is deleted."""
    life = aws_json("s3api", "get-bucket-lifecycle-configuration", "--bucket", bucket,
                    missing_ok=("NoSuchLifecycleConfiguration",))
    rules = (life or {}).get("Rules", [])
    keep = [r for r in rules if r.get("ID") != rule_id]
    if len(keep) == len(rules):
        typer.echo(f"no rule {rule_id} on {bucket}", err=True)
        raise typer.Exit(1)
    if keep:
        aws_json("s3api", "put-bucket-lifecycle-configuration", "--bucket", bucket,
                 "--lifecycle-configuration", json.dumps({"Rules": keep}))
    else:
        aws_json("s3api", "delete-bucket-lifecycle", "--bucket", bucket)
    emit({"bucket": bucket, "removed": rule_id, "kept_rules": [r.get("ID") for r in keep]})


@app.command("purge-versions")
def purge_versions(
    bucket: str = typer.Option(..., "--bucket", "-b"),
    prefix: str = typer.Option("", help="Only keys under this prefix. Default: the whole bucket."),
    yes: bool = typer.Option(False, "--yes", help="Delete. Without it, only the preview is printed."),
) -> None:
    """Destructive. Delete every version and delete marker under a prefix of a versioned bucket. Preview by default."""
    items: list[dict[str, str]] = []
    token: Optional[str] = None
    while True:
        argv = ["s3api", "list-object-versions", "--bucket", bucket, "--prefix", prefix, "--max-items", "1000"]
        data = aws_json(*argv, *(["--starting-token", token] if token else []))
        items += [{"Key": v["Key"], "VersionId": v["VersionId"]} for v in (data.get("Versions") or []) + (data.get("DeleteMarkers") or [])]
        token = data.get("NextToken")
        if not token:
            break
    out: dict[str, Any] = {"bucket": bucket, "prefix": prefix, "versions_and_markers": len(items),
                           "keys": len({i["Key"] for i in items}), "sample": sorted({i["Key"] for i in items})[:10],
                           "deleted": 0, "errors": []}
    if yes:
        for i in range(0, len(items), 1000):
            body = json.dumps({"Objects": items[i:i + 1000], "Quiet": True})
            res = aws_json("s3api", "delete-objects", "--bucket", bucket, "--delete", body)
            errs = (res or {}).get("Errors") or []
            out["errors"] += [{"key": e.get("Key"), "code": e.get("Code")} for e in errs][:20]
            out["deleted"] += len(items[i:i + 1000]) - len(errs)
    emit(out)


@app.command("public-read")
def public_read(
    bucket: str = typer.Option(..., "--bucket", "-b"),
    prefix: str = typer.Option("", help="Only keys under this prefix. Default: the whole bucket."),
) -> None:
    """Write. Add an anonymous-GET statement for bucket/prefix* to the bucket policy; other statements are kept."""
    pol = aws_json("s3api", "get-bucket-policy", "--bucket", bucket, missing_ok=("NoSuchBucketPolicy",))
    doc = json.loads(pol["Policy"]) if pol else {"Version": "2012-10-17", "Statement": []}
    resource = f"arn:aws:s3:::{bucket}/{prefix}*"
    sid = "PublicRead" + ("-" + re.sub(r"[^A-Za-z0-9]", "", prefix.title()) if prefix else "")
    stmts = [s for s in doc["Statement"] if s.get("Sid") != sid]
    stmts.append({"Sid": sid, "Effect": "Allow", "Principal": "*", "Action": "s3:GetObject", "Resource": resource})
    doc["Statement"] = stmts
    aws_json("s3api", "put-bucket-policy", "--bucket", bucket, "--policy", json.dumps(doc))
    emit({"bucket": bucket, "sid": sid, "resource": resource, "statements": [s.get("Sid") for s in stmts],
          "public_url": f"{endpoint()}/{bucket}/{prefix}<key>"})


if __name__ == "__main__":
    app()
