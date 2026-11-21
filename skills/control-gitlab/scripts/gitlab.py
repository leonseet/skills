# /// script
# requires-python = ">=3.11"
# dependencies = ["typer>=0.12", "python-dotenv>=1.0", "truststore>=0.10"]
# ///
"""control-gitlab helpers: doctor and chains over glab. glab stays the main interface.

Run as: uv run ~/.agents/skills/control-gitlab/scripts/gitlab.py <command>
"""

from __future__ import annotations

import json
import os
import re
import shutil
import ssl
import subprocess
import sys
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlsplit

import truststore
import typer
from dotenv import dotenv_values

# Where the instance lives: a setting, read from the current repo's .env first, then the shell. No default.
HOST_VAR = "GITLAB_HOST"
# Versions the last proof ran against. doctor warns when the installed ones differ.
PROVEN = {"cli": "1.108.0", "service": "18.11.13"}

app = typer.Typer(no_args_is_help=True, add_completion=False)

ANSI = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")
# Runner log lines: "<RFC3339 timestamp> <stream id><O|E><+?> text"
STAMP = re.compile(r"^\d{4}-\d\d-\d\dT[\d:.]+Z \d+[OE]\+? ?")


def glab(*argv: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["glab", *argv], capture_output=True, text=True)


def glab_json(*argv: str) -> Any:
    proc = glab(*argv)
    if proc.returncode != 0:
        typer.echo(f"glab {' '.join(argv[:3])} failed: {proc.stderr.strip()[-400:]}", err=True)
        raise typer.Exit(proc.returncode or 1)
    return json.loads(proc.stdout) if proc.stdout.strip() else None


def repo_env() -> dict[str, str]:
    try:
        root = subprocess.run(["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True, check=True).stdout.strip()
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
    return (value, "shell environment") if value else (None, "not in the current repo's .env or the shell")


def bare_host(value: str) -> str:
    """`https://host/`, `host:port` or `host` -> what glab takes as a hostname."""
    return (urlsplit(value).netloc if "://" in value else value).strip("/")


def host() -> str:
    value, source = setting(HOST_VAR)
    if not value:
        typer.echo(f"{HOST_VAR} {source}; run `doctor` for the fix", err=True)
        raise typer.Exit(1)
    return bare_host(value)


def project_id(project: str) -> int:
    """`group/project`, `<host>/group/project` or a numeric id."""
    if project.isdigit():
        return int(project)
    h = host()
    path = project.removeprefix(f"https://{h}/").removeprefix(f"{h}/")
    return glab_json("repo", "view", f"{h}/{path}", "-F", "json")["id"]


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
    "that already trusts it, then does one of: (a) `glab config set ca_cert /path/to/ca.pem --host {host}`, "
    "so only glab trusts it; (b) add it to the OS trust store, so every tool does: "
    "Debian/Ubuntu `sudo cp ca.pem /usr/local/share/ca-certificates/<name>.crt && sudo update-ca-certificates`, "
    "macOS `sudo security add-trusted-cert -d -r trustRoot -k /Library/Keychains/System.keychain ca.pem`. "
    "Certificate verification stays on"
)


def token_url(h: str) -> str:
    return f"https://{h}/-/user_settings/personal_access_tokens"


def login(h: str) -> str:
    return f"the user runs `glab auth login --hostname {h}` in their own terminal and pastes the token at its prompt, never into the chat"


def host_check(h: str) -> tuple[str, str]:
    """('ok' | 'tls' | 'net', detail): connect to the host and verify its certificate the way glab will:
    the OS trust store, plus the `ca_cert` glab holds for this host."""
    import socket

    name, _, port = h.partition(":")
    try:
        with socket.create_connection((name, int(port or 443)), timeout=10) as sock:
            ctx = truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
            ca = glab("config", "get", "ca_cert", "--host", h).stdout.strip() if shutil.which("glab") else ""
            if ca and Path(ca).expanduser().is_file():
                ctx.load_verify_locations(cafile=str(Path(ca).expanduser()))
            with ctx.wrap_socket(sock, server_hostname=name):
                return "ok", f"{h} reachable, certificate trusted"
    except ssl.SSLCertVerificationError as e:
        return "tls", f"{h}: {str(e)[:200]}"
    except Exception as e:  # noqa: BLE001  DNS, refused, timeout
        return "net", f"{h}: {type(e).__name__}: {str(e)[:200]}"


def host_candidates() -> str:
    """Hosts this machine already points at, to put before the user when GITLAB_HOST is unset."""
    found: list[str] = []
    remote = subprocess.run(["git", "remote", "get-url", "origin"], capture_output=True, text=True).stdout.strip()
    m = re.match(r"(?:\w+://)?(?:[^@/]+@)?([^:/]+)", remote)
    if m and m.group(1):
        found.append(f"{m.group(1)} (this repo's origin)")
    if shutil.which("glab"):
        status = glab("auth", "status")
        for h in re.findall(r"^(\S+\.\S+)$", status.stdout + status.stderr, re.M):
            if h not in " ".join(found) and h != "gitlab.com":
                found.append(f"{h} (a glab login)")
    return "; candidates seen on this machine: " + ", ".join(found) if found else ""


@app.command("host")
def host_cmd() -> None:
    """Read. Print the GitLab host recipes use as `H` (GITLAB_HOST: repo .env first, then the shell)."""
    typer.echo(host())


@app.command()
def doctor() -> None:
    """Read-only: one ok/WARN/FAIL line per check, a `fix:` line under each FAIL. Exit 1 on any FAIL."""
    ok = True
    exe = shutil.which("glab")
    ok &= line("ok" if exe else "FAIL", "glab", exe or "not on PATH")
    if not exe:
        fix("`brew install glab` when Homebrew is present; otherwise a release from https://gitlab.com/gitlab-org/cli/-/releases")
    else:
        m = re.search(r"(\d+\.\d+\.\d+)", glab("--version").stdout)
        cli = m.group(1) if m else "unknown"
        line("ok" if cli == PROVEN["cli"] else "WARN", "glab version", f"{cli} (proven {PROVEN['cli']})")
    jq = shutil.which("jq")
    ok &= line("ok" if jq else "FAIL", "jq", jq or "not on PATH (glab api recipes pipe through jq)")
    if not jq:
        fix(JQ_FIX)

    value, source = setting(HOST_VAR)
    ok &= line("ok" if value else "FAIL", HOST_VAR, f"{bare_host(value)} ({source})" if value else source)
    if not value:
        fix(f"ask the user which GitLab host to operate{host_candidates()}. They add {HOST_VAR}=<host> to the current "
            f"repo's .env when it belongs to this project, or `export {HOST_VAR}=<host>` to {STARTUP} for every repo")
        typer.echo("skip host, auth and version checks until the FAILs above are fixed; then rerun doctor")
        sys.exit(1)
    h = bare_host(value)
    kind, detail = host_check(h)
    ok &= line("ok" if kind == "ok" else "FAIL", "host", detail)
    if kind == "tls":
        fix(TLS_FIX.format(host=h))
    elif kind == "net":
        fix(NET_FIX.format(host=h, source=f"{HOST_VAR} ({source})"))
    if exe and kind == "ok":
        auth = glab("auth", "status", "--hostname", h)
        ok &= line("ok" if auth.returncode == 0 else "FAIL", "auth", h if auth.returncode == 0 else f"no valid login for {h}")
        if auth.returncode != 0:
            fix(f"the user creates a personal access token with scope `api` at {token_url(h)}; then {login(h)}")
    if not ok:
        typer.echo("skip api user and gitlab version checks until the FAILs above are fixed; then rerun doctor")
        sys.exit(1)

    who = glab("api", "user", "--hostname", h)
    if who.returncode == 0:
        line("ok", "api user", json.loads(who.stdout).get("username", "?"))
    else:
        ok &= line("FAIL", "api user", who.stderr.strip()[-200:])
        fix(f"401: the token expired or was revoked. The user makes a new one at {token_url(h)}; then {login(h)}")

    ver = glab("api", "version", "--hostname", h)
    if ver.returncode == 0:
        svc = json.loads(ver.stdout).get("version", "unknown")
        line("ok" if svc == PROVEN["service"] else "WARN", "gitlab version", f"{svc} (proven {PROVEN['service']})")
    else:
        ok &= line("FAIL", "gitlab version", ver.stderr.strip()[-200:])
    sys.exit(0 if ok else 1)


def clean(log: str) -> list[str]:
    out = []
    for raw in log.splitlines():
        s = STAMP.sub("", ANSI.sub("", raw)).strip()
        if s and not s.startswith(("section_start:", "section_end:")):
            out.append(s)
    return out


@app.command("failed-job-log")
def failed_job_log(
    project: str = typer.Option(..., "--project", "-p", help="group/project, <host>/group/project, or numeric id."),
    pipeline: Optional[int] = typer.Option(None, help="Pipeline id. Default: latest pipeline on --ref."),
    ref: Optional[str] = typer.Option(None, help="Branch or tag for the latest pipeline. Default: the project's default branch."),
    lines: int = typer.Option(60, help="Log lines to keep per failed job, from the end."),
) -> None:
    """Read. Each failed job of a pipeline with the cleaned tail of its log, as JSON."""
    pid = project_id(project)
    if pipeline is None:
        q = f"projects/{pid}/pipelines?per_page=1" + (f"&ref={ref}" if ref else "")
        if not ref:
            q += "&ref=" + glab_json("api", "--hostname", host(), f"projects/{pid}")["default_branch"]
        found = glab_json("api", "--hostname", host(), q)
        if not found:
            typer.echo("no pipeline found", err=True)
            raise typer.Exit(1)
        pipeline = found[0]["id"]
    pl = glab_json("api", "--hostname", host(), f"projects/{pid}/pipelines/{pipeline}")
    jobs = glab_json("api", "--hostname", host(), f"projects/{pid}/pipelines/{pipeline}/jobs?scope[]=failed&per_page=50")
    result = {"pipeline": pipeline, "status": pl["status"], "ref": pl["ref"], "web_url": pl["web_url"], "failed": []}
    for j in jobs:
        trace = glab("api", "--hostname", host(), f"projects/{pid}/jobs/{j['id']}/trace").stdout
        result["failed"].append({
            "id": j["id"], "name": j["name"], "stage": j["stage"],
            "failure_reason": j.get("failure_reason"), "allow_failure": j.get("allow_failure"),
            "log_tail": clean(trace)[-lines:],
        })
    typer.echo(json.dumps(result, indent=1))


BLOCKED_BY = re.compile(r"^\s*\**Blocked by\**:?\**\s*(.*)$", re.I | re.M)


def blockers(description: str) -> list[int]:
    """Issue iids named on the description's `Blocked by:` line(s). CE has no native blocking links."""
    return [int(n) for m in BLOCKED_BY.finditer(description or "") for n in re.findall(r"#(\d+)", m.group(1))]


@app.command("linked-issues")
def linked_issues(
    project: str = typer.Option(..., "--project", "-p", help="group/project, <host>/group/project, or numeric id."),
    issue: int = typer.Option(..., "--issue", "-i", help="The issue whose linked issues to list (e.g. a map)."),
    label_prefix: Optional[str] = typer.Option(None, help="Keep only linked issues with a label starting with this, e.g. wayfinder:"),
) -> None:
    """Read. Linked issues with state, labels, assignees, `Blocked by:` blockers and whether each is takeable."""
    pid = project_id(project)
    links = glab_json("api", "--hostname", host(), f"projects/{pid}/issues/{issue}/links")
    state: dict[int, str] = {}

    def state_of(iid: int) -> str:
        if iid not in state:
            state[iid] = glab_json("api", "--hostname", host(), f"projects/{pid}/issues/{iid}")["state"]
        return state[iid]

    out = []
    for li in links:
        if li.get("project_id") != pid:
            continue
        labels = li.get("labels", [])
        if label_prefix and not any(lb.startswith(label_prefix) for lb in labels):
            continue
        state[li["iid"]] = li["state"]
        bl = [{"iid": b, "state": state_of(b)} for b in blockers(li.get("description", ""))]
        assignees = [a["username"] for a in li.get("assignees", [])]
        out.append({
            "iid": li["iid"], "title": li["title"], "state": li["state"], "labels": labels,
            "assignees": assignees, "blocked_by": bl,
            "takeable": li["state"] == "opened" and not assignees and all(b["state"] == "closed" for b in bl),
        })
    out.sort(key=lambda x: x["iid"])
    typer.echo(json.dumps(out, separators=(",", ":")))


@app.command("append-to-section")
def append_to_section(
    project: str = typer.Option(..., "--project", "-p", help="group/project, <host>/group/project, or numeric id."),
    issue: int = typer.Option(..., "--issue", "-i", help="The issue whose description to change."),
    section: str = typer.Option(..., help='The `## ` heading text, e.g. "Decisions so far".'),
    text: str = typer.Option(..., help="Markdown to add as the section's last line(s)."),
) -> None:
    """Write. Add text at the end of one `## <section>` of an issue's description; the rest is kept as is."""
    pid = project_id(project)
    desc = glab_json("api", "--hostname", host(), f"projects/{pid}/issues/{issue}")["description"] or ""
    lines = desc.split("\n")
    head = re.compile(rf"^##\s+{re.escape(section)}\s*$", re.I)
    start = next((i for i, s in enumerate(lines) if head.match(s)), None)
    if start is None:
        typer.echo(f"no '## {section}' heading in #{issue}", err=True)
        raise typer.Exit(1)
    end = next((i for i in range(start + 1, len(lines)) if lines[i].startswith("## ")), len(lines))
    last = end
    while last > start + 1 and not lines[last - 1].strip():
        last -= 1
    lines[last:last] = text.split("\n")
    body = json.dumps({"description": "\n".join(lines)})
    proc = subprocess.run(["glab", "api", "-X", "PUT", "--hostname", host(), f"projects/{pid}/issues/{issue}",
                           "-H", "Content-Type: application/json", "--input", "-"],
                          input=body, capture_output=True, text=True)
    if proc.returncode != 0:
        typer.echo(f"update failed: {proc.stderr.strip()[-400:]}", err=True)
        raise typer.Exit(proc.returncode or 1)
    typer.echo(json.dumps({"iid": issue, "section": section, "added_after_line": last}))


if __name__ == "__main__":
    app()
