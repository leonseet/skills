# /// script
# requires-python = ">=3.11"
# dependencies = ["typer>=0.12", "python-dotenv>=1.0", "langfuse>=5.1.0,<6", "truststore>=0.10"]
# ///
"""control-langfuse helper: doctor and the chains the langfuse CLI makes clumsy. JSON out.

Run as: uv run -q ~/.agents/skills/control-langfuse/scripts/langfuse.py <command>
"""

from __future__ import annotations

import sys
from pathlib import Path

# This file is named langfuse.py: drop its own folder from the import path so `import langfuse` finds the SDK.
_HERE = Path(__file__).resolve().parent
sys.path[:] = [p for p in sys.path if Path(p or ".").resolve() != _HERE]

import json  # noqa: E402
import os  # noqa: E402
import shlex  # noqa: E402
import shutil  # noqa: E402
import ssl  # noqa: E402
import subprocess  # noqa: E402
from urllib.parse import urlsplit  # noqa: E402
from typing import Any, Optional  # noqa: E402

import typer  # noqa: E402
from dotenv import dotenv_values  # noqa: E402

SERVICE = "langfuse"
# Versions the last proof ran against. doctor warns when the installed ones differ.
PROVEN = {"cli": "1.3.1", "service": "4.75.0", "sdk": "5.1.0"}
# Where the instance lives and the keys for it: settings read from the repo .env first, then the shell. No default URL.
URL_VAR = "LANGFUSE_BASE_URL"
CREDENTIALS = ["LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY", URL_VAR]
# Optional: a PEM file holding a private CA, trusted on top of the OS trust store. Shared by every control skill.
CA_VAR = "CONTROL_CA_FILE"
# Linux system bundles, which hold whatever CA was added to the OS store. Node ignores them unless told.
SYSTEM_BUNDLES = ["/etc/ssl/certs/ca-certificates.crt", "/etc/pki/tls/certs/ca-bundle.crt", "/etc/ssl/ca-bundle.pem"]
SANDBOX_ENV = "control-sandbox"

app = typer.Typer(no_args_is_help=True, add_completion=False, pretty_exceptions_enable=False)


# --- helpers --------------------------------------------------------------


def repo_root() -> Optional[Path]:
    try:
        out = subprocess.run(["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True, check=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None
    return Path(out.stdout.strip())


def repo_env_path() -> Optional[Path]:
    root = repo_root()
    path = root / ".env" if root else None
    return path if path and path.exists() else None


def setting(name: str) -> tuple[Optional[str], str]:
    """(value, source): repo .env first, then the shell environment."""
    path = repo_env_path()
    if path:
        value = dotenv_values(path).get(name)
        if value:
            return value, ".env"
    if os.environ.get(name):
        return os.environ[name], "shell"
    if name == URL_VAR:  # the name older Langfuse SDKs read, still common in repo .env files
        value, source = setting("LANGFUSE_HOST")
        if value:
            return value, f"{source} as LANGFUSE_HOST"
    return None, "unset"


def creds() -> dict[str, str]:
    values = {n: setting(n)[0] for n in CREDENTIALS}
    missing = [n for n, v in values.items() if not v]
    if missing:
        typer.echo(f"missing {', '.join(missing)}: not in the current repo's .env or the shell; run `doctor` for the fix", err=True)
        raise typer.Exit(2)
    return values  # type: ignore[return-value]


def emit(data: Any) -> None:
    typer.echo(json.dumps(data, separators=(",", ":"), default=str, ensure_ascii=False))


def ca_file() -> Optional[Path]:
    ca, source = setting(CA_VAR)
    if not ca:
        return None
    path = Path(ca).expanduser()
    if not path.is_file():
        typer.echo(f"{CA_VAR} ({source}) names {path}, which is not a file", err=True)
        raise typer.Exit(2)
    return path


def tls_context() -> ssl.SSLContext:
    """The OS trust store (Keychain on macOS, the system bundle on Linux), plus the CA in CONTROL_CA_FILE when set."""
    import truststore

    ctx = truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ca = ca_file()
    if ca:
        ctx.load_verify_locations(cafile=str(ca))
    return ctx


def node_env() -> dict[str, str]:
    """What makes Node trust what this machine trusts: Node reads only its own bundled roots by default."""
    env: dict[str, str] = {}
    url = setting(URL_VAR)[0]
    if url:
        env[URL_VAR] = url
    ca = ca_file()
    bundle = ca or next((Path(b) for b in SYSTEM_BUNDLES if Path(b).is_file()), None)
    if bundle:
        env["NODE_EXTRA_CA_CERTS"] = str(bundle)
    elif sys.platform == "darwin":
        node = shutil.which("node")
        v = subprocess.run([node, "--version"], capture_output=True, text=True).stdout.strip().lstrip("v") if node else ""
        parts = tuple(int(x) for x in v.split(".")[:2]) if v else (0, 0)
        if parts >= (23, 8) or (parts[0] == 22 and parts >= (22, 15)):  # the Keychain, where an added CA lives
            env["NODE_OPTIONS"] = (os.environ.get("NODE_OPTIONS", "") + " --use-system-ca").strip()
    return env


def cli_argv() -> list[str]:
    path = repo_env_path()
    return ["langfuse", *(["--env", str(path)] if path else [])]


def cli(*args: str) -> Any:
    """Run `langfuse api ...` with the same environment the recipes' $LF gives it; parse the JSON body."""
    proc = subprocess.run([*cli_argv(), "api", *args], capture_output=True, text=True, env={**os.environ, **node_env()})
    if proc.returncode != 0:
        typer.echo(f"langfuse api {' '.join(args[:2])} failed ({proc.returncode}): {(proc.stdout + proc.stderr).strip()[-500:]}", err=True)
        raise typer.Exit(proc.returncode)
    return json.loads(proc.stdout) if proc.stdout.strip() else None


def sdk(environment: Optional[str] = None):
    import truststore

    truststore.inject_into_ssl()  # the SDK's certifi bundle knows no private CA; the OS trust store may
    ca = ca_file()
    if ca:  # httpx and requests under the SDK honour these on top of the injected store
        os.environ.setdefault("SSL_CERT_FILE", str(ca))
        os.environ.setdefault("REQUESTS_CA_BUNDLE", str(ca))
    from langfuse import Langfuse

    c = creds()
    return Langfuse(
        public_key=c["LANGFUSE_PUBLIC_KEY"],
        secret_key=c["LANGFUSE_SECRET_KEY"],
        base_url=c["LANGFUSE_BASE_URL"],
        environment=environment,
    )


def cut(value: Any, n: int) -> Any:
    text = value if isinstance(value, str) else json.dumps(value, default=str, ensure_ascii=False)
    return text if len(text) <= n else text[:n] + f"…(+{len(text) - n})"


def line(status: str, check: str, detail: str = "") -> bool:
    typer.echo(f"{status:<4} {check}" + (f"  {detail}" if detail else ""))
    return status != "FAIL"


def fix(text: str) -> None:
    """The step that clears the check above, printed under it."""
    typer.echo(f"     fix: {text}")


# --- doctor ---------------------------------------------------------------

CLI_INSTALL = f"npm install -g @langfuse/cli@{PROVEN['cli']}"
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
    + STARTUP + ", so only the control skills trust it; (b) add it to the OS trust store, so every tool does: "
    "Debian/Ubuntu `sudo cp ca.pem /usr/local/share/ca-certificates/<name>.crt && sudo update-ca-certificates`, "
    "macOS `sudo security add-trusted-cert -d -r trustRoot -k /Library/Keychains/System.keychain ca.pem`. "
    "Certificate verification stays on"
)


def host_check(url: str) -> tuple[str, str]:
    """('ok' | 'tls' | 'net', detail): connect to the URL's host and, for https, verify its certificate."""
    import socket

    u = urlsplit(url)
    host, port = u.hostname or "", u.port or (443 if u.scheme == "https" else 80)
    try:
        with socket.create_connection((host, port), timeout=10) as sock:
            if u.scheme != "https":
                return "ok", f"{host}:{port} reachable"
            with tls_context().wrap_socket(sock, server_hostname=host):
                return "ok", f"{host}:{port} reachable, certificate trusted"
    except (ssl.SSLCertVerificationError, typer.Exit) as e:
        return "tls", f"{host}:{port}: {str(e)[:200] or 'see the error above'}"
    except Exception as e:  # noqa: BLE001  DNS, refused, timeout
        return "net", f"{host}:{port}: {type(e).__name__}: {str(e)[:200]}"


@app.command()
def lf() -> None:
    """Read. Print the CLI prefix recipes use as $LF: the URL, Node's CA setting, and --env for the repo's .env."""
    typer.echo(" ".join(["env", *(f"{k}={shlex.quote(v)}" for k, v in node_env().items()), *map(shlex.quote, cli_argv())]))


@app.command()
def doctor() -> None:
    """Read-only: one ok/WARN/FAIL line per check, with a `fix:` line under each FAIL. Exit 1 on any FAIL."""
    ok = True
    node = shutil.which("node")
    node_v = subprocess.run([node, "--version"], capture_output=True, text=True).stdout.strip() if node else ""
    node_ok = bool(node_v) and int(node_v.lstrip("v").split(".")[0]) >= 20
    ok &= line("ok" if node_ok else "FAIL", "node", node_v or "not on PATH")
    if not node_ok:
        fix("install Node.js 20 or newer (nodejs.org, or a version manager such as fnm: `fnm install 22`)")
    exe = shutil.which("langfuse")
    ok &= line("ok" if exe else "FAIL", "langfuse cli", exe or "not on PATH")
    if not exe:
        fix(CLI_INSTALL)
    else:
        v = subprocess.run([exe, "--version"], capture_output=True, text=True).stdout.strip()
        if v.startswith("0."):
            ok &= line("FAIL", "cli version", f"{v} is the old `langfuse-cli` package; it lacks the v4 endpoints")
            fix(f"npm uninstall -g langfuse-cli && {CLI_INSTALL}")
        else:
            line("ok" if v == PROVEN["cli"] else "WARN", "cli version", f"{v} (proven {PROVEN['cli']})")
    for name in [URL_VAR, *[n for n in CREDENTIALS if n != URL_VAR]]:
        value, source = setting(name)
        detail = f"from {source}" + (f": {value}" if name == URL_VAR and value else "")
        ok &= line("ok" if value else "FAIL", name, detail if value else "not in the current repo's .env or the shell")
        if not value and name == URL_VAR:
            fix(f"ask the user for their Langfuse URL (https://<host>, what the browser shows). They add {name}=… to the "
                f"current repo's .env when it belongs to this project, or `export {name}=…` to {STARTUP} for every repo")
        elif not value:
            fix(f"the user adds {name}=… to the current repo's .env, or exports it in {STARTUP}, themselves "
                "(Langfuse UI → Project settings → API Keys); never paste keys into chat")
    base_url = setting(URL_VAR)[0]
    if base_url:
        kind, detail = host_check(base_url)
        ok &= line("ok" if kind == "ok" else "FAIL", "host", detail)
        if kind == "tls":
            fix(TLS_FIX.format(host=urlsplit(base_url).hostname))
        elif kind == "net":
            fix(NET_FIX.format(host=urlsplit(base_url).hostname, source=URL_VAR))
    jq = shutil.which("jq")
    ok &= line("ok" if jq else "FAIL", "jq", jq or "not on PATH")
    if not jq:
        fix(JQ_FIX)
    if not ok:
        typer.echo("skip host, auth and sdk checks until the FAILs above are fixed; then rerun doctor")
        sys.exit(1)
    try:
        health = cli("health", "get")
        version = health.get("version", "?")
        line("ok", "cli health", health.get("status", ""))
        line("ok" if version == PROVEN["service"] else "WARN", "server version", f"{version} (proven {PROVEN['service']})")
        projects = cli("projects", "list")["data"]
        ok &= line("ok", "cli auth", "project " + ", ".join(f"{p['name']} ({p['id']})" for p in projects))
    except typer.Exit:
        ok &= line("FAIL", "cli call", "see the error above")
        fix("401 means the key pair is wrong or revoked: the user re-copies both keys from the same project into .env. "
            "`fetch failed` while `host` above is ok means Node does not trust the certificate that Python does: the "
            f"user points {CA_VAR} at the CA's PEM file (see the TLS fix: option a), which `lf` hands to Node")
    try:
        import langfuse as sdk_pkg

        sv = getattr(sdk_pkg, "__version__", "?")
        line("ok" if sv == PROVEN["sdk"] else "WARN", "python sdk", f"{sv} (proven {PROVEN['sdk']})")
        ok &= line("ok" if sdk().auth_check() else "FAIL", "sdk auth")
    except Exception as e:  # noqa: BLE001
        ok &= line("FAIL", "sdk auth", f"{type(e).__name__}: {str(e)[:200]}")
        fix("if `cli auth` is ok, the keys work: rerun once (uv may still be installing the SDK), else report it")
    sys.exit(0 if ok else 1)


# --- observations ---------------------------------------------------------


@app.command()
def trace(
    trace_id: str = typer.Argument(..., help="Trace id (32 hex)."),
    io: int = typer.Option(0, "--io", help="Include input/output cut to this many chars. 0 leaves them out."),
    max_items: int = typer.Option(500, help="Cap on observations fetched."),
) -> None:
    """Read. One trace as an indented observation tree, plus its scores and UI link."""
    fields = "core,basic,model,usage,metrics,trace_context" + (",io" if io else "")
    rows = cli("observations", "list", "--trace-id", trace_id, "--fields", fields,
               "--limit", "1000", "--all", "--max-items", str(max_items))
    rows = rows["data"] if isinstance(rows, dict) else rows
    if not rows:
        emit({"trace_id": trace_id, "observations": [], "note": "no observations: wrong id, wrong project, or not ingested"})
        return
    by_parent: dict[Optional[str], list[dict]] = {}
    ids = {r["id"] for r in rows}
    for r in rows:
        parent = r.get("parentObservationId")
        by_parent.setdefault(parent if parent in ids else None, []).append(r)
    out: list[dict] = []

    def walk(parent: Optional[str], depth: int) -> None:
        for r in sorted(by_parent.get(parent, []), key=lambda r: r["startTime"]):
            from datetime import datetime

            start, end = r.get("startTime"), r.get("endTime")
            ms = None
            if start and end:
                ms = round((datetime.fromisoformat(end.replace("Z", "+00:00")) - datetime.fromisoformat(start.replace("Z", "+00:00"))).total_seconds() * 1000)
            node = {"depth": depth, "id": r["id"], "type": r["type"], "name": r.get("name"), "level": r.get("level"),
                    "start": start, "ms": ms}
            if r.get("statusMessage"):
                node["status"] = cut(r["statusMessage"], 300)
            if r.get("model"):
                node.update(model=r["model"], tokens=r.get("totalUsage"), cost=r.get("totalCost"))
            if io:
                node.update(input=cut(r.get("input"), io), output=cut(r.get("output"), io))
            out.append(node)
            walk(r["id"], depth + 1)

    walk(None, 0)
    first = rows[0]
    scores = cli("scores", "list", "--trace-id", trace_id, "--limit", "100")["data"]
    emit({
        "trace_id": trace_id,
        "name": first.get("traceName"), "environment": first.get("environment"),
        "user": first.get("userId"), "session": first.get("sessionId"), "tags": first.get("tags"),
        "url": f"{creds()['LANGFUSE_BASE_URL']}/project/{first['projectId']}/traces/{trace_id}",
        "observations": out,
        "scores": [{"name": s["name"], "value": s["value"], "source": s["source"]} for s in scores],
    })


@app.command("send-trace")
def send_trace(
    name: str = typer.Option("control-sandbox-smoke", help="Trace and root span name."),
    environment: str = typer.Option(SANDBOX_ENV, help="Langfuse environment the trace lands in."),
    error: bool = typer.Option(False, "--error", help="Mark the generation level ERROR with a status message."),
) -> None:
    """Write. Send a two-observation test trace (span + generation) over OpenTelemetry and print its id and link."""
    from langfuse import propagate_attributes

    lf = sdk(environment=environment)
    with propagate_attributes(user_id=SANDBOX_ENV, session_id=f"{SANDBOX_ENV}-session", tags=[SANDBOX_ENV], trace_name=name):
        with lf.start_as_current_observation(name=name, as_type="span", input={"q": "ping"}) as root:
            with lf.start_as_current_observation(
                name="fake-llm", as_type="generation", model="gpt-4o-mini",
                input=[{"role": "user", "content": "ping"}], output="pong", usage_details={"input": 3, "output": 1},
                level="ERROR" if error else None, status_message="control-sandbox: simulated failure" if error else None,
            ):
                pass
            root.update(output={"a": "pong"})
            trace_id = lf.get_current_trace_id()
    lf.flush()
    emit({"trace_id": trace_id, "environment": environment, "url": lf.get_trace_url(trace_id=trace_id)})


# --- prompts --------------------------------------------------------------


@app.command("prompt-push")
def prompt_push(
    name: str = typer.Option(..., "--name", help="Existing prompt name."),
    file: Path = typer.Option(..., "--file", exists=True, dir_okay=False, help="New prompt body: plain text for a text prompt, a JSON message array for a chat prompt."),
    label: list[str] = typer.Option([], "--label", help="Label(s) for the new version, e.g. production. Repeatable."),
    message: Optional[str] = typer.Option(None, "--message", help="Commit message."),
) -> None:
    """Write. New version of an existing prompt from a file, keeping the latest version's type, config and tags."""
    latest = cli("prompts", "get", name, "--label", "latest", "--no-resolve")
    raw = file.read_text()
    body: Any = raw.rstrip("\n")  # pull and editors add a final newline; don't let it accumulate per round trip
    if latest["type"] == "chat":
        body = json.loads(raw)
        if not isinstance(body, list):
            typer.echo("chat prompt file must hold a JSON array of messages", err=True)
            raise typer.Exit(2)
    payload = {"name": name, "type": latest["type"], "prompt": body, "config": latest.get("config") or {},
               "tags": latest.get("tags") or [], "labels": label}
    if message:
        payload["commitMessage"] = message
    created = cli("prompts", "create", "--body-json", json.dumps(payload))
    emit({"name": created["name"], "version": created["version"], "previous": latest["version"], "labels": created["labels"]})


if __name__ == "__main__":
    app()
