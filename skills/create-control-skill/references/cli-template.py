# /// script
# requires-python = ">=3.11"
# dependencies = ["typer>=0.12", "python-dotenv>=1.0"]
# ///
"""Template for a control skill's scripts/<svc>.py. Copy it, rename SERVICE, keep the helpers, replace the example commands.

Run as: uv run ~/.agents/skills/control-<svc>/scripts/<svc>.py <command>
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Optional

import typer
from dotenv import dotenv_values

SERVICE = "example"
# Versions the last proof ran against. The proof step sets these; doctor warns when the installed ones differ.
PROVEN = {"cli": "0.0.0", "service": "0.0.0"}
# Credential variables this CLI needs. Names only, never values.
CREDENTIALS = ["EXAMPLE_URL", "EXAMPLE_TOKEN"]  # the URL has no default: the instance is the user's setting

app = typer.Typer(no_args_is_help=True, add_completion=False)


# --- helpers --------------------------------------------------------------


def repo_env() -> dict[str, str]:
    """The current repo's .env (git root of the working directory), or {} outside a repo."""
    try:
        root = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True, check=True
        ).stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return {}
    path = Path(root) / ".env"
    return {k: v for k, v in dotenv_values(path).items() if v} if path.exists() else {}


def credential(name: str) -> Optional[str]:
    """Repo .env first, then the shell environment."""
    return repo_env().get(name) or os.environ.get(name)


def require_credentials() -> dict[str, str]:
    values = {n: credential(n) for n in CREDENTIALS}
    missing = [n for n, v in values.items() if not v]
    if missing:
        typer.echo(
            f"missing credentials: {', '.join(missing)}. Set them in the current repo's .env or the shell environment; "
            "see the skill's Setup section.",
            err=True,
        )
        raise typer.Exit(2)
    return values  # type: ignore[return-value]


def emit(data: Any, fields: Optional[str] = None) -> None:
    """Compact JSON on stdout. --fields a,b keeps only those keys (on a dict or on each dict in a list)."""
    if fields:
        keep = [f.strip() for f in fields.split(",")]
        pick = lambda d: {k: d.get(k) for k in keep} if isinstance(d, dict) else d  # noqa: E731
        data = [pick(d) for d in data] if isinstance(data, list) else pick(data)
    typer.echo(json.dumps(data, separators=(",", ":"), default=str))


def run_json(*argv: str) -> Any:
    """Run an established CLI that prints JSON (for chains over e.g. glab) and parse its output."""
    proc = subprocess.run(argv, capture_output=True, text=True)
    if proc.returncode != 0:
        typer.echo(f"{argv[0]} failed ({proc.returncode}): {proc.stderr.strip()[-500:]}", err=True)
        raise typer.Exit(proc.returncode)
    return json.loads(proc.stdout) if proc.stdout.strip() else None


def line(status: str, check: str, detail: str = "") -> bool:
    typer.echo(f"{status:<4} {check}" + (f"  {detail}" if detail else ""))
    return status != "FAIL"


def fix(text: str) -> None:
    """The step that clears the FAIL above, printed under it: an exact command, or what the user must do."""
    typer.echo(f"     fix: {text}")


# --- doctor ---------------------------------------------------------------


@app.command()
def doctor() -> None:
    """Read-only: one ok/WARN/FAIL line per check, a `fix:` line under each FAIL. Exit 1 on any FAIL."""
    ok = True
    # 1. Prerequisites, in the Setup order: runtime, CLI + version, credentials, TLS trust, helpers.
    cli = shutil.which("example-cli")
    ok &= line("ok" if cli else "FAIL", "cli", cli or "example-cli not on PATH")
    if not cli:
        fix("npm install -g example-cli@" + PROVEN["cli"])  # the real install command
    else:
        cli_version = "0.0.0"  # e.g. parse `example-cli --version`
        line("ok" if cli_version == PROVEN["cli"] else "WARN", "cli version", f"{cli_version} (proven {PROVEN['cli']})")
    for name in CREDENTIALS:
        value = credential(name)
        ok &= line("ok" if value else "FAIL", name, "set" if value else "unset")
        if not value:
            # Name the file and where the value comes from; the user writes it there, never into the chat.
            fix(f"the user adds `{name}=…` to the current repo's .env themselves (from <where the service issues it>)")
    # 2. Checks that need the prerequisites: skip them, rather than fail confusingly, until those are fixed.
    if not ok:
        typer.echo("skip host, auth and version checks until the FAILs above are fixed; then rerun doctor")
        sys.exit(1)
    # Replace with real checks, each with its fix: host reachable and trusted, auth valid, service version vs PROVEN.
    sys.exit(0 if ok else 1)


# --- example commands -----------------------------------------------------


@app.command("list-things")
def list_things(
    limit: int = typer.Option(20, help="Maximum results."),
    fields: Optional[str] = typer.Option(None, help="Comma-separated keys to keep."),
) -> None:
    """Read. Example of an SDK-backed command."""
    creds = require_credentials()
    _ = creds  # client = Sdk(url=creds["EXAMPLE_URL"], token=creds["EXAMPLE_TOKEN"])
    emit([{"id": i, "name": f"thing-{i}"} for i in range(limit)], fields)


if __name__ == "__main__":
    app()
