# /// script
# requires-python = ">=3.11"
# dependencies = ["typer>=0.12", "python-dotenv>=1.0", "httpx>=0.27", "truststore>=0.10"]
# ///
"""control-temporal: operate a Temporal server over the Temporal Web UI's HTTP API (/api/v1).

Run as: uv run ~/.agents/skills/control-temporal/scripts/temporal.py <command>
Reads print compact JSON. `terminate`, `reset` and `schedule delete` print a preview and a confirm token first,
and change nothing until rerun with --confirm <token>.

Why not the `temporal` CLI: it speaks only gRPC (port 7233), which a VPN or ingress often does not route; the
UI's HTTP API answers wherever the UI loads, and does reads and writes.
"""

from __future__ import annotations

import base64
import datetime as dt
import getpass
import hashlib
import json
import os
import shutil
import ssl
import subprocess
import sys
import uuid
from pathlib import Path
from typing import Any, Optional
from urllib.parse import quote, urlsplit

import httpx
import typer
from dotenv import dotenv_values

SERVICE = "temporal"
LOCAL_URL = "http://localhost:8080"
# Versions the last proof ran against. doctor warns when the installed ones differ.
PROVEN = {"ui": "2.54.1", "service": "1.32.0"}
# Settings this script reads (repo .env first, then the shell). Names only; Temporal here has no credentials.
# Settings, read from the current repo's .env first, then the shell. No default URL or task queue.
URL_VAR, NS_VAR, TQ_VAR = "TEMPORAL_UI_URL", "TEMPORAL_NAMESPACE", "TEMPORAL_TASK_QUEUE"
# Optional: a PEM file holding a private CA, trusted on top of the OS trust store. Shared by every control skill.
CA_VAR = "CONTROL_CA_FILE"
IDENTITY = f"control-temporal:{getpass.getuser()}"
PREFIX_STATUS = "WORKFLOW_EXECUTION_STATUS_"
PREFIX_EVENT = "EVENT_TYPE_"
# Workflow-task bookkeeping: hidden from `history` unless --all.
NOISE = {"WORKFLOW_TASK_SCHEDULED", "WORKFLOW_TASK_STARTED", "WORKFLOW_TASK_COMPLETED"}
FAILURE_EVENTS = {
    "ACTIVITY_TASK_FAILED", "ACTIVITY_TASK_TIMED_OUT", "WORKFLOW_TASK_FAILED", "WORKFLOW_TASK_TIMED_OUT",
    "WORKFLOW_EXECUTION_FAILED", "WORKFLOW_EXECUTION_TIMED_OUT", "WORKFLOW_EXECUTION_TERMINATED",
    "CHILD_WORKFLOW_EXECUTION_FAILED", "CHILD_WORKFLOW_EXECUTION_TIMED_OUT",
}
CLOSE_EVENTS = {
    "WORKFLOW_EXECUTION_COMPLETED", "WORKFLOW_EXECUTION_FAILED", "WORKFLOW_EXECUTION_TIMED_OUT",
    "WORKFLOW_EXECUTION_CANCELED", "WORKFLOW_EXECUTION_TERMINATED", "WORKFLOW_EXECUTION_CONTINUED_AS_NEW",
}

app = typer.Typer(no_args_is_help=True, add_completion=False)
schedule_app = typer.Typer(no_args_is_help=True, add_completion=False, help="Schedules (cron-started workflows).")
app.add_typer(schedule_app, name="schedule")

STATE: dict[str, Any] = {"url": None, "url_source": "", "ns": None, "ns_source": ""}


class Fail(Exception):
    """A problem the caller can act on; printed on stderr, exit 1."""


# --- helpers --------------------------------------------------------------


def repo_env() -> dict[str, str]:
    try:
        root = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True, check=True
        ).stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return {}
    path = Path(root) / ".env"
    return {k: v for k, v in dotenv_values(path).items() if v} if path.exists() else {}


def setting(name: str) -> tuple[Optional[str], str]:
    """(value, source): the current repo's .env first, then the shell."""
    value = repo_env().get(name)
    if value:
        return value, "repo .env"
    value = os.environ.get(name)
    return (value, "shell environment") if value else (None, "default")


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


def tls_context() -> ssl.SSLContext:
    """The OS trust store (Keychain on macOS, the system bundle on Linux), plus the CA in CONTROL_CA_FILE when set."""
    import truststore

    ctx = truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ca, source = setting(CA_VAR)
    if ca:
        path = Path(ca).expanduser()
        if not path.is_file():
            raise Fail(f"{CA_VAR} ({source}) names {path}, which is not a file")
        ctx.load_verify_locations(cafile=str(path))
    return ctx


def emit(data: Any) -> None:
    typer.echo(json.dumps(data, separators=(",", ":"), default=str, ensure_ascii=False))


def line(status: str, check: str, detail: str = "") -> bool:
    typer.echo(f"{status:<4} {check}" + (f"  {detail}" if detail else ""))
    return status != "FAIL"


def fix(text: str) -> None:
    """The step that clears the FAIL above, printed under it."""
    typer.echo(f"     fix: {text}")


def drop_none(d: dict) -> dict:
    return {k: v for k, v in d.items() if v not in (None, "", [], {})}


def short(value: Optional[str], prefix: str) -> Optional[str]:
    return value[len(prefix):] if value and value.startswith(prefix) else value


def stamp(value: Optional[str]) -> Optional[str]:
    """ISO time cut to seconds: 2026-11-16T02:18:07Z."""
    return value[:19] + "Z" if value and len(value) >= 19 else value


def age(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    try:
        then = dt.datetime.fromisoformat(value[:19] + "+00:00")
    except ValueError:
        return None
    s = int((dt.datetime.now(dt.UTC) - then).total_seconds())
    for unit, n in (("d", 86400), ("h", 3600), ("m", 60)):
        if s >= n:
            return f"{s // n}{unit}"
    return f"{max(s, 0)}s"


def seconds_text(value: Optional[str]) -> Optional[str]:
    """A proto duration ("419348.67s") as 4d / 3h / 12m / 5s."""
    try:
        s = int(float((value or "0s").rstrip("s")))
    except ValueError:
        return value
    for unit, n in (("d", 86400), ("h", 3600), ("m", 60)):
        if s >= n:
            return f"{s // n}{unit}"
    return f"{s}s"


def clip(value: Any, width: int) -> Any:
    """Cut a decoded payload to `width` characters of JSON; small values pass through unchanged."""
    text = json.dumps(value, separators=(",", ":"), default=str, ensure_ascii=False)
    return value if len(text) <= width else text[:width] + f"…(+{len(text) - width} chars)"


def b64(text: str) -> str:
    return base64.b64encode(text.encode()).decode()


def unb64(text: Optional[str]) -> str:
    return base64.b64decode(text or "").decode("utf-8", errors="replace")


def decode(payload: dict, width: int = 300) -> Any:
    """A Temporal payload as a value. JSON is decoded; an S3-offloaded payload becomes {"$s3": {bucket, key, bytes}}."""
    meta = {k: unb64(v) for k, v in (payload.get("metadata") or {}).items()}
    enc = meta.get("encoding", "")
    if enc == "binary/null":
        return None
    if enc == "json/plain":
        try:
            return clip(json.loads(unb64(payload.get("data"))), width)
        except ValueError:
            return clip(unb64(payload.get("data")), width)
    if meta.get("messageType") == "temporal.api.sdk.v1.ExternalStorageReference":
        try:
            claim = json.loads(unb64(payload.get("data"))).get("claimData", {})
        except ValueError:
            claim = {}
        size = sum(int(p.get("sizeBytes", 0)) for p in payload.get("externalPayloads") or [])
        return {"$s3": drop_none({"bucket": claim.get("bucket"), "key": claim.get("key"), "bytes": size or None})}
    return {"$encoding": enc or "unknown", "bytes": len(base64.b64decode(payload.get("data") or ""))}


def decode_all(payloads: Optional[dict], width: int = 300) -> Any:
    items = [decode(p, width) for p in (payloads or {}).get("payloads") or []]
    return items[0] if len(items) == 1 else (items or None)


def encode_inputs(inputs: list[str]) -> Optional[dict]:
    """Each --input is one JSON argument."""
    if not inputs:
        return None
    payloads = []
    for raw in inputs:
        try:
            json.loads(raw)
        except ValueError as e:
            raise Fail(f"--input must be JSON (quote strings: '\"text\"'): {raw[:80]}") from e
        payloads.append({"metadata": {"encoding": b64("json/plain")}, "data": b64(raw)})
    return {"payloads": payloads}


def failure(f: Optional[dict], width: int = 300) -> Optional[dict]:
    """A Temporal Failure, flattened: message, type, timeout type, and the innermost cause."""
    if not f:
        return None
    inner = f
    while inner.get("cause"):
        inner = inner["cause"]
    out = {
        "message": (f.get("message") or "")[:width],
        "type": (f.get("applicationFailureInfo") or {}).get("type"),
        "timeout": short((f.get("timeoutFailureInfo") or {}).get("timeoutType"), "TIMEOUT_TYPE_"),
        "nonRetryable": (f.get("applicationFailureInfo") or {}).get("nonRetryable"),
    }
    if inner is not f:
        out["cause"] = drop_none({
            "message": (inner.get("message") or "")[:width],
            "type": (inner.get("applicationFailureInfo") or {}).get("type"),
            "timeout": short((inner.get("timeoutFailureInfo") or {}).get("timeoutType"), "TIMEOUT_TYPE_"),
        })
    return drop_none(out)


def token(*parts: Any) -> str:
    return hashlib.sha256("|".join(str(p) for p in parts).encode()).hexdigest()[:10]


# --- client ---------------------------------------------------------------


class UI:
    """The Temporal Web UI's HTTP API. GETs need nothing; other methods need the UI's _csrf cookie echoed back."""

    def __init__(self) -> None:
        if not STATE["url"]:
            raise Fail(f"{URL_VAR} is not in the current repo's .env or the shell; run `doctor` for the fix")
        self.base = STATE["url"].rstrip("/")
        self.ns = STATE["ns"]
        verify: Any = tls_context() if self.base.startswith("https") else False
        self.http = httpx.Client(base_url=self.base, verify=verify, timeout=30, headers={"Accept": "application/json"})
        self.csrf: Optional[str] = None

    def _csrf(self) -> str:
        if not self.csrf:
            r = self.http.get("/")
            self.csrf = r.cookies.get("_csrf") or self.http.cookies.get("_csrf")
            if not self.csrf:
                raise Fail(f"{self.base} set no _csrf cookie, so writes cannot be sent; run `doctor`")
        return self.csrf

    def call(self, method: str, path: str, params: Optional[dict] = None, body: Any = None, timeout: float = 30) -> Any:
        url = f"/api/v1/{path}"
        # The cookie is sent by hand: the UI marks it Secure, so a cookie jar withholds it from a plain-http UI (--local).
        headers = {} if method == "GET" else {"X-CSRF-Token": self._csrf(), "Cookie": f"_csrf={self._csrf()}",
                                              "Content-Type": "application/json"}
        params = {k: v for k, v in (params or {}).items() if v not in (None, "")}
        try:
            r = self.http.request(method, url, params=params, json=body, headers=headers, timeout=timeout)
        except httpx.HTTPError as e:
            if method != "GET":
                raise Fail(f"{method} {url} got no answer ({e or type(e).__name__}). It may still have been accepted: "
                           "read it back with `describe` before sending it again") from e
            raise Fail(f"cannot reach {self.base}: {e or type(e).__name__}; run `doctor`") from e
        if r.status_code >= 400:
            try:
                detail = r.json().get("message") or r.text[:300]
            except ValueError:
                detail = r.text[:300]
            raise Fail(f"{method} {url} -> HTTP {r.status_code}: {detail}")
        return r.json() if r.content else {}

    def get(self, path: str, **params: Any) -> Any:
        return self.call("GET", path, params)

    def post(self, path: str, body: dict, timeout: float = 30, request_id: bool = True) -> Any:
        """request_id: the request type carries a requestId (dedupes retries); query and terminate do not."""
        return self.call("POST", path, body={**body, "requestId": str(uuid.uuid4())} if request_id else body,
                         timeout=timeout)

    def wf(self, wid: str) -> str:
        return f"namespaces/{self.ns}/workflows/{quote(wid, safe='')}"

    # -- lookups

    def describe(self, wid: str, run: Optional[str]) -> dict:
        return self.get(self.wf(wid), **{"execution.runId": run})

    def history(self, wid: str, run: Optional[str]) -> list[dict]:
        events, page = [], None
        while True:
            got = self.get(f"{self.wf(wid)}/history", **{"execution.runId": run, "maximumPageSize": 1000,
                                                        "nextPageToken": page})
            events += (got.get("history") or {}).get("events") or []
            page = got.get("nextPageToken")
            if not page:
                return events

    def last_event(self, wid: str, run: Optional[str]) -> Optional[dict]:
        got = self.get(f"{self.wf(wid)}/history-reverse", **{"execution.runId": run, "maximumPageSize": 1})
        events = (got.get("history") or {}).get("events") or []
        return events[0] if events else None


def run_cmd(fn) -> None:  # noqa: ANN001
    try:
        fn()
    except Fail as e:
        typer.echo(f"error: {e}", err=True)
        raise typer.Exit(1)


@app.callback()
def main(
    local: bool = typer.Option(False, "--local", help=f"Target the local docker Temporal UI ({LOCAL_URL})."),
    url: Optional[str] = typer.Option(None, "--url", help=f"Temporal UI base URL. Default: ${URL_VAR}."),
    namespace: Optional[str] = typer.Option(None, "--namespace", "-n", help=f"Default: ${NS_VAR}, else default."),
) -> None:
    if url or local:
        STATE["url"], STATE["url_source"] = url or LOCAL_URL, "--url" if url else "--local"
    else:
        value, source = setting(URL_VAR)
        STATE["url"], STATE["url_source"] = value, source
    if namespace:
        STATE["ns"], STATE["ns_source"] = namespace, "--namespace"
    else:
        value, source = setting(NS_VAR)
        STATE["ns"], STATE["ns_source"] = value or "default", source


# --- doctor ---------------------------------------------------------------


@app.command()
def doctor() -> None:
    """Read-only: one ok/WARN/FAIL line per check, a `fix:` line under each FAIL. Exit 1 on any FAIL."""
    ok = True
    line("ok", "uv", shutil.which("uv") or "running")
    jq = shutil.which("jq")
    ok &= line("ok" if jq else "FAIL", "jq", jq or "not on PATH (recipes pipe output through jq)")
    if not jq:
        fix(JQ_FIX)
    if not STATE["url"]:
        line("FAIL", URL_VAR, "not in the current repo's .env or the shell")
        fix(f"ask the user for their Temporal Web UI's URL (https://<host>, what the browser shows). They add "
            f"{URL_VAR}=… to the current repo's .env when it belongs to this project, or `export {URL_VAR}=…` to "
            f"{STARTUP} for every repo. For a docker Temporal on this machine, rerun as `temporal.py --local doctor`")
        typer.echo("skip reach, ui, namespace and version checks until the FAILs above are fixed; then rerun doctor")
        sys.exit(1)
    base = STATE["url"].rstrip("/")
    line("ok", "ui url", f"{base} ({STATE['url_source']})")
    tq, tq_source = setting(TQ_VAR)
    line("ok", "task queue", f"{tq} ({TQ_VAR}, {tq_source})" if tq else f"{TQ_VAR} unset: recipes that need this repo's queue will ask the user")

    reach = None
    try:
        verify: Any = tls_context() if base.startswith("https") else False
        reach = httpx.get(f"{base}/api/v1/settings", verify=verify, timeout=10)
        reach.raise_for_status()
        settings = reach.json()
        line("ok", "reach + tls", f"{base} answers" + (", certificate trusted" if base.startswith("https") else ""))
    except Exception as e:  # noqa: BLE001
        text = str(e) or type(e).__name__
        ok &= line("FAIL", "reach + tls", text[:200])
        if "CERTIFICATE_VERIFY_FAILED" in text:
            fix(TLS_FIX.format(host=urlsplit(base).hostname))
        elif "localhost" in base or "127.0.0.1" in base:
            fix(f"nothing answers at {base}: the local Temporal is down, or on another port. The user starts their "
                "docker Temporal (`docker ps -a | grep temporal`)")
        else:
            fix(NET_FIX.format(host=urlsplit(base).hostname, source=f"{URL_VAR} ({STATE['url_source']})"))
        typer.echo("skip ui, namespace and version checks until the FAILs above are fixed; then rerun doctor")
        sys.exit(1)

    auth = (settings.get("Auth") or {}).get("Enabled")
    ok &= line("FAIL" if auth else "ok", "ui auth", "enabled: this script sends no login" if auth else "disabled (none needed)")
    if auth:
        fix("the UI now requires login, which this script does not support; tell the user the skill needs an update")
    ui_version = settings.get("Version", "unknown")
    line("ok", "ui version", f"{ui_version} (proven on {PROVEN['ui']})")
    writes_off = settings.get("DisableWriteActions")
    line("WARN" if writes_off else "ok", "ui write actions", "disabled: writes will be refused" if writes_off else "enabled")

    try:
        ui = UI()
        ui._csrf()
        line("ok", "csrf cookie", "writes can be sent")
        info = ui.get("cluster-info")
        version = info.get("serverVersion", "unknown")
        line("ok", "server version", f"{version} (proven on {PROVEN['service']})")
    except Fail as e:
        ok &= line("FAIL", "csrf cookie", str(e))
        fix("the UI changed how it guards writes; tell the user the skill needs an update")

    try:
        ns = UI().get(f"namespaces/{STATE['ns']}")
        retention = (ns.get("config") or {}).get("workflowExecutionRetentionTtl", "?")
        line("ok", "namespace", f"{STATE['ns']} ({STATE['ns_source']}), history kept {retention}")
    except Fail as e:
        ok &= line("FAIL", "namespace", f"{STATE['ns']} ({STATE['ns_source']}): {e}")
        names = [n["namespaceInfo"]["name"] for n in (UI().get("namespaces").get("namespaces") or [])]
        fix(f"pass -n with one of {names}, or correct {NS_VAR} in the repo .env")
    sys.exit(0 if ok else 1)


# --- namespace & cluster --------------------------------------------------


@app.command()
def info() -> None:
    """Read. Server, UI and namespace facts: versions, retention, namespaces."""
    def go() -> None:
        ui = UI()
        cluster = ui.get("cluster-info")
        settings = ui.get("settings")
        ns = ui.get(f"namespaces/{ui.ns}")
        emit({
            "ui": ui.base, "uiVersion": settings.get("Version"), "server": cluster.get("serverVersion"),
            "persistence": cluster.get("persistenceStore"),
            "namespaces": [n["namespaceInfo"]["name"] for n in ui.get("namespaces").get("namespaces") or []],
            "namespace": ui.ns, "retention": (ns.get("config") or {}).get("workflowExecutionRetentionTtl"),
            "state": short((ns.get("namespaceInfo") or {}).get("state"), "NAMESPACE_STATE_"),
            "taskQueue": setting(TQ_VAR)[0],
        })
    run_cmd(go)


@app.command("search-attributes")
def search_attributes(system: bool = typer.Option(False, "--system", help="Also list the built-in ones.")) -> None:
    """Read. Search attributes usable in --query, with their types."""
    def go() -> None:
        ui = UI()
        got = ui.get(f"namespaces/{ui.ns}/search-attributes")
        strip = lambda d: {k: short(v, "INDEXED_VALUE_TYPE_") for k, v in (d or {}).items()}  # noqa: E731
        out = {"custom": strip(got.get("customAttributes"))}
        if system:
            out["system"] = strip(got.get("systemAttributes"))
        emit(out)
    run_cmd(go)


# --- workflows ------------------------------------------------------------


STATUSES = {"running": "Running", "completed": "Completed", "failed": "Failed", "canceled": "Canceled",
            "terminated": "Terminated", "timed_out": "TimedOut", "continued_as_new": "ContinuedAsNew"}


def build_query(query: Optional[str], status: Optional[str], wtype: Optional[str], task_queue: Optional[str],
                since: Optional[str]) -> Optional[str]:
    parts = [f"({query})"] if query else []
    if status:
        if status.lower() not in STATUSES:
            raise Fail(f"--status is one of {', '.join(STATUSES)}")
        parts.append(f"ExecutionStatus='{STATUSES[status.lower()]}'")
    if wtype:
        parts.append(f"WorkflowType='{wtype}'")
    if task_queue:
        parts.append(f"TaskQueue='{task_queue}'")
    if since:
        units = {"m": 60, "h": 3600, "d": 86400}
        if not since[:-1].isdigit() or since[-1] not in units:
            raise Fail("--since is like 30m, 6h, 2d")
        start = dt.datetime.now(dt.UTC) - dt.timedelta(seconds=int(since[:-1]) * units[since[-1]])
        parts.append(f"StartTime > '{start.strftime('%Y-%m-%dT%H:%M:%SZ')}'")
    return " AND ".join(parts) or None


def row(e: dict) -> dict:
    return drop_none({
        "id": e["execution"]["workflowId"], "run": e["execution"]["runId"], "type": (e.get("type") or {}).get("name"),
        "status": short(e.get("status"), PREFIX_STATUS), "taskQueue": e.get("taskQueue"),
        "start": stamp(e.get("startTime")), "close": stamp(e.get("closeTime")), "events": e.get("historyLength"),
    })


QUERY = typer.Option(None, "--query", "-q", help="Visibility query, e.g. \"WorkflowType='MyWorkflow'\".")
STATUS = typer.Option(None, "--status", help="running, completed, failed, canceled, terminated, timed_out.")
TYPE = typer.Option(None, "--type", help="Workflow type, e.g. MyWorkflow.")
TQ = typer.Option(None, "--task-queue", "--tq", help="Task queue, e.g. the repo's $TEMPORAL_TASK_QUEUE.")
SINCE = typer.Option(None, "--since", help="Started within, e.g. 30m, 6h, 2d.")
RUN = typer.Option(None, "--run", help="Run id. Default: the latest run of the workflow id.")


@app.command("list")
def list_(
    query: Optional[str] = QUERY, status: Optional[str] = STATUS, wtype: Optional[str] = TYPE,
    task_queue: Optional[str] = TQ, since: Optional[str] = SINCE,
    limit: int = typer.Option(20, "--limit", help="Maximum rows, newest first."),
) -> None:
    """Read. Workflow executions, newest first: [{id, run, type, status, taskQueue, start, close, events}]."""
    def go() -> None:
        ui = UI()
        q = build_query(query, status, wtype, task_queue, since)
        out, page = [], None
        while len(out) < limit:
            got = ui.get(f"namespaces/{ui.ns}/workflows", query=q, pageSize=min(limit - len(out), 1000),
                         nextPageToken=page)
            out += [row(e) for e in got.get("executions") or []]
            page = got.get("nextPageToken")
            if not page:
                break
        emit(out[:limit])
    run_cmd(go)


@app.command()
def count(
    query: Optional[str] = QUERY, status: Optional[str] = STATUS, wtype: Optional[str] = TYPE,
    task_queue: Optional[str] = TQ, since: Optional[str] = SINCE,
    by_status: bool = typer.Option(False, "--by-status", help="Break the count down by status."),
) -> None:
    """Read. How many executions match: {count} or {count, byStatus: {Running: n, …}}."""
    def go() -> None:
        ui = UI()
        q = build_query(query, status, wtype, task_queue, since)
        if by_status:
            q = f"{q or ''} GROUP BY ExecutionStatus".strip()
        got = ui.get(f"namespaces/{ui.ns}/workflow-count", query=q)
        out: dict[str, Any] = {"count": int(got.get("count", 0))}
        if by_status:
            out["byStatus"] = {decode(g["groupValues"][0]): int(g.get("count", 0)) for g in got.get("groups") or []}
        emit(out)
    run_cmd(go)


def summarize(d: dict, width: int) -> dict:
    wi = d.get("workflowExecutionInfo") or {}
    pending = []
    for a in d.get("pendingActivities") or []:
        pending.append(drop_none({
            "activity": (a.get("activityType") or {}).get("name"), "id": a.get("activityId"),
            "state": short(a.get("state"), "PENDING_ACTIVITY_STATE_"), "attempt": a.get("attempt"),
            "maxAttempts": a.get("maximumAttempts"), "scheduled": stamp(a.get("scheduledTime")),
            "lastStarted": stamp(a.get("lastStartedTime")), "lastHeartbeat": stamp(a.get("lastHeartbeatTime")),
            "lastWorker": a.get("lastWorkerIdentity"), "nextAttempt": stamp(a.get("nextAttemptScheduleTime")),
            "lastFailure": failure(a.get("lastFailure"), width),
        }))
    wt = d.get("pendingWorkflowTask") or {}
    return drop_none({
        "id": wi.get("execution", {}).get("workflowId"), "run": wi.get("execution", {}).get("runId"),
        "type": (wi.get("type") or {}).get("name"), "status": short(wi.get("status"), PREFIX_STATUS),
        "taskQueue": wi.get("taskQueue"), "start": stamp(wi.get("startTime")), "age": age(wi.get("startTime")),
        "close": stamp(wi.get("closeTime")), "events": wi.get("historyLength"),
        "historyBytes": wi.get("historySizeBytes"),
        "parent": (wi.get("parentExecution") or {}).get("workflowId"),
        "pendingWorkflowTask": drop_none({"state": short(wt.get("state"), "PENDING_WORKFLOW_TASK_STATE_"),
                                          "attempt": wt.get("attempt"), "scheduled": stamp(wt.get("scheduledTime"))}),
        "pendingActivities": pending,
        "pendingChildren": [c.get("workflowId") for c in d.get("pendingChildren") or []],
    })


WIDTH = typer.Option(300, "--width", help="Characters kept of each message or decoded payload.")


@app.command()
def describe(wid: str, run: Optional[str] = RUN, width: int = WIDTH) -> None:
    """Read. One execution: status, age, history size, pending workflow task and pending activities."""
    run_cmd(lambda: emit(summarize(UI().describe(wid, run), width)))


def compact(e: dict, names: dict[str, str], payloads: bool, width: int) -> dict:
    kind = short(e.get("eventType"), PREFIX_EVENT)
    attrs = next((v for k, v in e.items() if k.endswith("EventAttributes")), {}) or {}
    out: dict[str, Any] = {"id": int(e["eventId"]), "t": stamp(e.get("eventTime")), "e": kind}
    if kind == "ACTIVITY_TASK_SCHEDULED":
        names[e["eventId"]] = attrs.get("activityType", {}).get("name")
    sched = attrs.get("scheduledEventId")
    if kind.startswith("ACTIVITY_TASK_") and sched:
        out["activity"] = names.get(sched)
        out["sched"] = int(sched)
    out.update(drop_none({
        "activity": out.get("activity") or (attrs.get("activityType") or {}).get("name"),
        "type": (attrs.get("workflowType") or {}).get("name"),
        "taskQueue": (attrs.get("taskQueue") or {}).get("name") if kind == "WORKFLOW_EXECUTION_STARTED" else None,
        "attempt": attrs.get("attempt") if kind == "ACTIVITY_TASK_STARTED" and attrs.get("attempt", 1) > 1 else None,
        "signal": attrs.get("signalName"), "timer": attrs.get("timerId"),
        "fireIn": attrs.get("startToFireTimeout"), "reason": attrs.get("reason") or None,
        "cause": short(attrs.get("cause"), "WORKFLOW_TASK_FAILED_CAUSE_"),
        "retryState": short(attrs.get("retryState"), "RETRY_STATE_"),
        "failure": failure(attrs.get("failure"), width), "identity": attrs.get("identity") if kind in
        {"WORKFLOW_EXECUTION_SIGNALED", "WORKFLOW_EXECUTION_CANCEL_REQUESTED", "WORKFLOW_EXECUTION_TERMINATED"} else None,
    }))
    if payloads:
        for key in ("input", "result", "details"):
            if attrs.get(key):
                out[key] = decode_all(attrs[key], width)
    return out


@app.command()
def history(
    wid: str, run: Optional[str] = RUN,
    last: int = typer.Option(40, "--last", help="Keep the last N matching events."),
    only: Optional[str] = typer.Option(None, "--only", help="failures | activities | signals."),
    all_: bool = typer.Option(False, "--all", help="Include workflow-task bookkeeping events."),
    payloads: bool = typer.Option(False, "--payloads", help="Decode inputs and results (cut to --width)."),
    width: int = WIDTH,
) -> None:
    """Read. The event history, compacted: [{id, t, e, activity?, failure?, …}], last N kept."""
    def go() -> None:
        names: dict[str, str] = {}
        events = [compact(e, names, payloads, width) for e in UI().history(wid, run)]
        if only == "failures":
            events = [e for e in events if e["e"] in FAILURE_EVENTS]
        elif only == "activities":
            events = [e for e in events if e["e"].startswith("ACTIVITY_TASK_")]
        elif only == "signals":
            events = [e for e in events if e["e"] == "WORKFLOW_EXECUTION_SIGNALED"]
        elif only:
            raise Fail("--only is failures, activities or signals")
        elif not all_:
            events = [e for e in events if e["e"] not in NOISE]
        emit(events[-last:])
    run_cmd(go)


@app.command()
def result(wid: str, run: Optional[str] = RUN, width: int = typer.Option(2000, "--width")) -> None:
    """Read. How a closed execution ended: {status, result | failure | reason}. A running one says so."""
    def go() -> None:
        ui = UI()
        wi = ui.describe(wid, run).get("workflowExecutionInfo") or {}
        status = short(wi.get("status"), PREFIX_STATUS)
        if status == "RUNNING":
            emit({"status": status, "note": "still running; `describe` shows what it waits on"})
            return
        last = ui.last_event(wid, wi.get("execution", {}).get("runId")) or {}
        attrs = next((v for k, v in last.items() if k.endswith("EventAttributes")), {}) or {}
        emit(drop_none({
            "status": status, "close": stamp(wi.get("closeTime")), "event": short(last.get("eventType"), PREFIX_EVENT),
            "result": decode_all(attrs.get("result"), width), "failure": failure(attrs.get("failure"), width),
            "reason": attrs.get("reason"), "identity": attrs.get("identity"),
            "newRun": attrs.get("newExecutionRunId"),
        }))
    run_cmd(go)


def queue_view(ui: UI, tq: str) -> dict:
    out = {"taskQueue": tq}
    for kind, code in (("workflow", 1), ("activity", 2)):
        got = ui.get(f"namespaces/{ui.ns}/task-queues/{quote(tq, safe='')}", taskQueueType=code, reportStats="true")
        stats = got.get("stats") or {}
        out[kind] = drop_none({
            "pollers": [{"identity": p.get("identity"), "seen": age(p.get("lastAccessTime")),
                         "buildId": (p.get("workerVersionCapabilities") or {}).get("buildId")}
                        for p in got.get("pollers") or []] or "none",
            "backlog": int(stats.get("approximateBacklogCount", 0)),
            "backlogAge": seconds_text(stats.get("approximateBacklogAge")),
        })
    return out


@app.command()
def diagnose(wid: str, run: Optional[str] = RUN, width: int = WIDTH) -> None:
    """Read (chain: describe → recent failures → task-queue pollers). Why a run is stuck, slow or failed."""
    def go() -> None:
        ui = UI()
        d = summarize(ui.describe(wid, run), width)
        names: dict[str, str] = {}
        events = [compact(e, names, False, width) for e in ui.history(wid, d.get("run"))]
        fails = [e for e in events if e["e"] in FAILURE_EVENTS][-5:]
        tq = d.get("taskQueue")
        queue = queue_view(ui, tq) if tq and d.get("status") == "RUNNING" else None
        hints = []
        if d.get("status") == "RUNNING":
            if queue and queue["workflow"].get("pollers") == "none":
                hints.append(f"no worker polls task queue {tq}: start one on that queue, or this run waits forever")
            if any("Nondeterminism" in json.dumps(e.get("failure", {})) for e in fails):
                hints.append("nondeterminism: the worker's code no longer replays this history; it retries forever. "
                             "Cancel or terminate the run, or reset it, or run the old code")
            stuck = [a for a in d.get("pendingActivities", []) if a.get("attempt", 1) > 1]
            if stuck:
                hints.append(f"activity {stuck[0].get('activity')} is retrying (attempt {stuck[0].get('attempt')}): "
                             "see its lastFailure")
            if d.get("pendingWorkflowTask", {}).get("attempt", 1) > 1:
                hints.append("the workflow task keeps failing: see the WORKFLOW_TASK_FAILED events")
        emit(drop_none({"run": d, "recentFailures": fails, "queue": queue, "hints": hints}))
    run_cmd(go)


# --- workflow writes ------------------------------------------------------


@app.command()
def start(
    wtype: str = typer.Option(..., "--type", help="Workflow type."),
    task_queue: str = typer.Option(..., "--task-queue", "--tq"),
    wid: str = typer.Option(..., "--id", help="Workflow id."),
    inputs: list[str] = typer.Option([], "--input", help="One JSON argument; repeat for more."),
    run_timeout: str = typer.Option("600s", "--run-timeout", help="Run timeout, e.g. 600s; the run times out after it."),
) -> None:
    """Write. Start a workflow: {id, run, started}. An app's own runs start through the app instead."""
    def go() -> None:
        ui = UI()
        got = ui.post(ui.wf(wid), drop_none({
            "workflowId": wid, "workflowType": {"name": wtype}, "taskQueue": {"name": task_queue},
            "input": encode_inputs(inputs), "workflowRunTimeout": run_timeout, "identity": IDENTITY,
        }))
        emit({"id": wid, "run": got.get("runId"), "started": got.get("started")})
    run_cmd(go)


@app.command()
def signal(
    wid: str, name: str, run: Optional[str] = RUN,
    inputs: list[str] = typer.Option([], "--input", help="One JSON argument; repeat for more."),
) -> None:
    """Write. Send a signal: {signaled}. Read-back: `history --only signals`."""
    def go() -> None:
        ui = UI()
        ui.post(f"{ui.wf(wid)}/signal/{quote(name, safe='')}", drop_none({
            "workflowExecution": drop_none({"workflowId": wid, "runId": run}), "input": encode_inputs(inputs),
            "identity": IDENTITY,
        }))
        emit({"signaled": name, "id": wid})
    run_cmd(go)


@app.command()
def query(
    wid: str, name: str, run: Optional[str] = RUN,
    inputs: list[str] = typer.Option([], "--input", help="One JSON argument; repeat for more."),
    width: int = typer.Option(4000, "--width"),
) -> None:
    """Read. Ask a live worker a query: {result}. `__stack_trace` shows where a running workflow is blocked."""
    def go() -> None:
        ui = UI()
        got = ui.post(f"{ui.wf(wid)}/query/{quote(name, safe='')}", {
            "execution": drop_none({"workflowId": wid, "runId": run}),
            "query": drop_none({"queryType": name, "queryArgs": encode_inputs(inputs)}),
        }, timeout=40, request_id=False)
        if got.get("queryRejected"):
            emit({"rejected": short(got["queryRejected"].get("status"), PREFIX_STATUS)})
        else:
            emit({"result": decode_all(got.get("queryResult"), width)})
    run_cmd(go)


@app.command()
def cancel(wid: str, run: Optional[str] = RUN, reason: str = typer.Option("", "--reason")) -> None:
    """Write. Request cancellation; the workflow code decides how it closes. Read-back: `describe` / `result`."""
    def go() -> None:
        ui = UI()
        ui.post(f"{ui.wf(wid)}/cancel", drop_none({
            "workflowExecution": drop_none({"workflowId": wid, "runId": run}), "reason": reason, "identity": IDENTITY,
        }))
        emit({"cancelRequested": wid})
    run_cmd(go)


def gate(preview: dict, confirm: Optional[str], tok: str) -> bool:
    """True once --confirm matches; otherwise print the preview and the token and change nothing."""
    if confirm == tok:
        return True
    if confirm:
        raise Fail("the confirm token does not match: the target changed since the preview. Rerun without "
                   "--confirm, show the new preview, and ask again")
    emit({**preview, "confirm": tok, "note": "nothing changed; rerun with --confirm <token> after the user's yes"})
    return False


@app.command()
def terminate(
    wid: str, run: Optional[str] = RUN, reason: str = typer.Option(..., "--reason"),
    confirm: Optional[str] = typer.Option(None, "--confirm"),
) -> None:
    """Destructive. Kill a run at once; no cleanup code runs. Preview + token first."""
    def go() -> None:
        ui = UI()
        d = summarize(ui.describe(wid, run), 200)
        if d.get("status") != "RUNNING":
            raise Fail(f"{wid} is {d.get('status')}, not running; nothing to terminate")
        preview = {"terminate": {k: d.get(k) for k in ("id", "run", "type", "status", "taskQueue", "age", "events")},
                   "pendingActivities": [a.get("activity") for a in d.get("pendingActivities", [])], "reason": reason}
        if gate(preview, confirm, token("terminate", d["id"], d["run"], d.get("events"))):
            ui.post(f"{ui.wf(wid)}/terminate", {
                "workflowExecution": {"workflowId": wid, "runId": d["run"]}, "reason": reason, "identity": IDENTITY,
            }, request_id=False)
            emit({"terminated": wid, "run": d["run"]})
    run_cmd(go)


@app.command()
def reset(
    wid: str, run: Optional[str] = RUN, reason: str = typer.Option(..., "--reason"),
    to: str = typer.Option("last", "--to", help="first | last (completed workflow task) | an event id."),
    confirm: Optional[str] = typer.Option(None, "--confirm"),
) -> None:
    """Destructive. End the run and start a new one replaying history up to a workflow task. Preview + token first."""
    def go() -> None:
        ui = UI()
        d = summarize(ui.describe(wid, run), 200)
        events = ui.history(wid, d["run"])
        done = [int(e["eventId"]) for e in events if e["eventType"] == "EVENT_TYPE_WORKFLOW_TASK_COMPLETED"]
        if to in ("first", "last"):
            if not done:
                raise Fail("no completed workflow task to reset to: a worker never finished one")
            point = done[0] if to == "first" else done[-1]
        elif to.isdigit():
            point = int(to)
            if point not in done:
                raise Fail(f"event {point} is not a WORKFLOW_TASK_COMPLETED; candidates: {done[-10:]}")
        else:
            raise Fail("--to is first, last or an event id")
        preview = {"reset": {k: d.get(k) for k in ("id", "run", "type", "status", "events")}, "toEvent": point,
                   "discards": f"events {point + 1}-{len(events)} of this run" if point < len(events) else "nothing", "reason": reason}
        if gate(preview, confirm, token("reset", d["id"], d["run"], d.get("events"), point)):
            got = ui.post(f"{ui.wf(wid)}/reset", {
                "workflowExecution": {"workflowId": wid, "runId": d["run"]}, "reason": reason,
                "workflowTaskFinishEventId": str(point), "identity": IDENTITY,
            })
            emit({"reset": wid, "oldRun": d["run"], "newRun": got.get("runId")})
    run_cmd(go)


# --- task queues & workers ------------------------------------------------


@app.command("task-queue")
def task_queue(tq: str) -> None:
    """Read. Who polls a task queue and its backlog: {taskQueue, workflow: {pollers, backlog}, activity: {…}}."""
    run_cmd(lambda: emit(queue_view(UI(), tq)))


@app.command()
def workers(
    task_queue: Optional[str] = TQ,
    limit: int = typer.Option(50, "--limit"),
) -> None:
    """Read. Running worker processes (SDK heartbeats): [{taskQueue, identity, host, sdk, status, started, seen}]."""
    def go() -> None:
        ui = UI()
        q = f"TaskQueue='{task_queue}'" if task_queue else None
        got = ui.get(f"namespaces/{ui.ns}/workers", query=q, pageSize=limit)
        out = []
        for w in got.get("workersInfo") or []:
            h = w.get("workerHeartbeat") or {}
            if (h.get("taskQueue") or "").startswith("temporal-sys-"):
                continue  # the server's own internal workers
            out.append(drop_none({
                "taskQueue": h.get("taskQueue"), "identity": h.get("workerIdentity"),
                "host": (h.get("hostInfo") or {}).get("hostName"), "sdk": f"{h.get('sdkName')} {h.get('sdkVersion')}",
                "buildId": (h.get("deploymentVersion") or {}).get("buildId"),
                "status": short(h.get("status"), "WORKER_STATUS_"), "started": stamp(h.get("startTime")),
                "seen": age(h.get("heartbeatTime")),
            }))
        emit(sorted(out, key=lambda r: r.get("taskQueue", "")))
    run_cmd(go)


# --- schedules ------------------------------------------------------------


def sched_path(ui: UI, sid: str) -> str:
    return f"namespaces/{ui.ns}/schedules/{quote(sid, safe='')}"


FULL = {"minute": (0, 59), "hour": (0, 23), "dayOfMonth": (1, 31), "month": (1, 12), "dayOfWeek": (0, 6)}


def as_cron(cal: dict) -> str:
    """A structuredCalendar entry back as a 5-field cron string (the server stores cron that way)."""
    fields = []
    for name, (lo, hi) in FULL.items():
        parts = []
        for r in cal.get(name) or [{}]:
            start = r.get("start", 0)
            end, step = r.get("end", start) or start, r.get("step", 1)
            if (start, end) == (lo, hi) or (name == "dayOfWeek" and (start, end) == (0, 6)):
                parts.append("*" if step == 1 else f"*/{step}")
            elif start == end:
                parts.append(str(start))
            else:
                parts.append(f"{start}-{end}" + (f"/{step}" if step != 1 else ""))
        fields.append(",".join(parts))
    return " ".join(fields)


def sched_view(sid: str, got: dict, width: int = 300) -> dict:
    s = got.get("schedule") or {}
    spec, state = s.get("spec") or {}, s.get("state") or {}
    action = (s.get("action") or {}).get("startWorkflow") or {}
    info = got.get("info") or {}
    return drop_none({
        "id": sid, "paused": state.get("paused", False), "notes": state.get("notes"),
        "cron": spec.get("cronString") or [as_cron(c) for c in spec.get("structuredCalendar") or []],
        "intervals": [i.get("interval") for i in spec.get("interval") or []],
        "workflow": drop_none({"type": (action.get("workflowType") or {}).get("name"), "id": action.get("workflowId"),
                               "taskQueue": (action.get("taskQueue") or {}).get("name"),
                               "runTimeout": action.get("workflowRunTimeout"),
                               "input": decode_all(action.get("input"), width)}),
        "actions": int(info.get("actionCount", 0)),
        "running": [r.get("workflowId") for r in info.get("runningWorkflows") or []],
        "recent": [drop_none({"at": stamp(a.get("actualTime")), "id": (a.get("startWorkflowResult") or {}).get("workflowId"),
                              "status": short(a.get("startWorkflowStatus"), PREFIX_STATUS)})
                   for a in (info.get("recentActions") or [])[-5:]],
        "next": [stamp(t) for t in (info.get("futureActionTimes") or [])[:3]],
        "updated": stamp(info.get("updateTime")),
    })


@schedule_app.command("list")
def schedule_list(limit: int = typer.Option(50, "--limit")) -> None:
    """Read. [{id, paused, workflowType, recent, next}]."""
    def go() -> None:
        ui = UI()
        got = ui.get(f"namespaces/{ui.ns}/schedules", maximumPageSize=limit)
        out = []
        for s in got.get("schedules") or []:
            i = s.get("info") or {}
            out.append(drop_none({
                "id": s.get("scheduleId"), "paused": i.get("paused", False),
                "workflowType": (i.get("workflowType") or {}).get("name"), "notes": i.get("notes"),
                "recent": [stamp(a.get("actualTime")) for a in (i.get("recentActions") or [])[-3:]],
                "next": [stamp(t) for t in (i.get("futureActionTimes") or [])[:2]],
            }))
        emit(out)
    run_cmd(go)


@schedule_app.command("show")
def schedule_show(sid: str) -> None:
    """Read. One schedule: spec, action, state, recent and next actions."""
    def go() -> None:
        ui = UI()
        emit(sched_view(sid, ui.get(sched_path(ui, sid))))
    run_cmd(go)


@schedule_app.command("create")
def schedule_create(
    sid: str,
    cron: str = typer.Option(..., "--cron", help="Cron string in UTC, e.g. '0 2 * * *'."),
    wtype: str = typer.Option(..., "--type"),
    task_queue: str = typer.Option(..., "--task-queue", "--tq"),
    workflow_id: Optional[str] = typer.Option(None, "--workflow-id", help="Default: <schedule id>-wf."),
    inputs: list[str] = typer.Option([], "--input", help="One JSON argument; repeat for more."),
    run_timeout: str = typer.Option("600s", "--run-timeout", help="Each started run times out after this."),
    active: bool = typer.Option(False, "--active", help="Start unpaused. Default: paused."),
    notes: str = typer.Option("", "--notes"),
) -> None:
    """Write. Create a schedule, paused unless --active. Read-back: `schedule show`."""
    def go() -> None:
        ui = UI()
        ui.post(sched_path(ui, sid), {
            "schedule": {
                "spec": {"cronString": [cron]},
                "action": {"startWorkflow": drop_none({
                    "workflowId": workflow_id or f"{sid}-wf", "workflowType": {"name": wtype},
                    "taskQueue": {"name": task_queue}, "input": encode_inputs(inputs),
                    "workflowRunTimeout": run_timeout,
                })},
                "state": drop_none({"paused": not active, "notes": notes or f"created by {IDENTITY}"}),
            },
            "identity": IDENTITY,
        })
        emit({"created": sid, "paused": not active})
    run_cmd(go)


def patch(sid: str, body: dict, label: str) -> None:
    def go() -> None:
        ui = UI()
        ui.post(f"{sched_path(ui, sid)}/patch", {"patch": body, "identity": IDENTITY})
        emit({label: sid})
    run_cmd(go)


@schedule_app.command("pause")
def schedule_pause(sid: str, note: str = typer.Option("paused by control-temporal", "--note")) -> None:
    """Write. Stop a schedule from starting workflows. Read-back: `schedule show` → paused: true."""
    patch(sid, {"pause": note}, "paused")


@schedule_app.command("unpause")
def schedule_unpause(sid: str, note: str = typer.Option("unpaused by control-temporal", "--note")) -> None:
    """Write. Resume a paused schedule. Read-back: `schedule show` → paused absent, next filled."""
    patch(sid, {"unpause": note}, "unpaused")


@schedule_app.command("trigger")
def schedule_trigger(sid: str) -> None:
    """Write. Start the schedule's workflow once, now (even when paused). Read-back: `schedule show` → recent."""
    patch(sid, {"triggerImmediately": {"overlapPolicy": "SCHEDULE_OVERLAP_POLICY_ALLOW_ALL"}}, "triggered")


@schedule_app.command("delete")
def schedule_delete(sid: str, confirm: Optional[str] = typer.Option(None, "--confirm")) -> None:
    """Destructive. Delete a schedule (its started workflows keep running). Preview + token first."""
    def go() -> None:
        ui = UI()
        view = sched_view(sid, ui.get(sched_path(ui, sid)))
        preview = {"delete": {k: view.get(k) for k in ("id", "paused", "cron", "workflow", "actions", "running")}}
        if gate(preview, confirm, token("schedule-delete", sid, view.get("updated"), view.get("actions"))):
            ui.call("DELETE", sched_path(ui, sid), params={"identity": IDENTITY})
            emit({"deleted": sid})
    run_cmd(go)


if __name__ == "__main__":
    app()
