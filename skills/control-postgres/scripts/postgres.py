# /// script
# requires-python = ">=3.11"
# dependencies = ["typer>=0.12", "python-dotenv>=1.0"]
# ///
"""control-postgres: doctor, the psql session environment, and chains over psql.

Run as: uv run ~/.agents/skills/control-postgres/scripts/postgres.py <command>
"""

from __future__ import annotations

import json
import os
import re
import shlex
import shutil
import socket
import subprocess
import sys
from pathlib import Path
from typing import Any, Optional
from urllib.parse import parse_qs, unquote, urlsplit

import typer
from dotenv import dotenv_values

SERVICE = "postgres"
# Versions the last proof ran against. doctor warns when the installed ones differ.
PROVEN = {"cli": "14.24", "service": "14.24"}
# Where the connection comes from. Names only, never values.
DSN_VARS = ["POSTGRES_DSN", "DATABASE_URL"]
PART_VARS = ["POSTGRES_HOST", "POSTGRES_PORT", "POSTGRES_DB", "POSTGRES_USER", "POSTGRES_PASSWORD"]
CLIENT_FIX = "`brew install libpq && brew link --force libpq` (macOS) or `sudo apt install postgresql-client` (Debian/Ubuntu)"
JQ_FIX = "`brew install jq` (macOS) or `sudo apt install jq` (Debian/Ubuntu; other Linux: your package manager)"

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


def parse_dsn(dsn: str) -> dict[str, str]:
    """postgresql://, postgres:// and SQLAlchemy postgresql+driver:// URLs."""
    u = urlsplit(dsn)
    if not u.scheme.split("+")[0] in ("postgresql", "postgres") or not u.hostname:
        raise ValueError("not a postgresql:// URL")
    return {
        "host": u.hostname,
        "port": str(u.port or 5432),
        "dbname": unquote(u.path.lstrip("/")) or "postgres",
        "user": unquote(u.username or ""),
        "password": unquote(u.password or ""),
        **{k: v[-1] for k, v in parse_qs(u.query).items() if k in ("sslmode", "sslrootcert")},
    }


def from_mapping(values: dict[str, Any], where: str) -> Optional[tuple[dict[str, str], str]]:
    for name in DSN_VARS:
        if values.get(name):
            try:
                return parse_dsn(values[name]), f"{name} in {where}"
            except ValueError as exc:
                raise ValueError(f"{name} in {where}: {exc}") from exc
    if values.get("POSTGRES_HOST") and values.get("POSTGRES_USER"):
        return {
            "host": values["POSTGRES_HOST"],
            "port": str(values.get("POSTGRES_PORT") or 5432),
            "dbname": values.get("POSTGRES_DB") or "postgres",
            "user": values["POSTGRES_USER"],
            "password": values.get("POSTGRES_PASSWORD") or "",
        }, f"POSTGRES_HOST/_PORT/_DB/_USER/_PASSWORD in {where}"
    return None


def resolve() -> Optional[tuple[dict[str, str], str]]:
    """The connection and where it came from: the current repo's .env first, then the shell."""
    path = repo_env_path()
    if path:
        found = from_mapping(dict(dotenv_values(path)), str(path))
        if found:
            return found
    return from_mapping(dict(os.environ), "the shell environment")


def session_env(conn: dict[str, str], write: bool = False, db: Optional[str] = None, timeout: int = 60) -> dict[str, str]:
    """The PG* variables of one psql session. Read sessions cannot change anything."""
    if write:
        options = "-c lock_timeout=10s -c idle_in_transaction_session_timeout=60s"
    else:
        options = (
            f"-c default_transaction_read_only=on -c statement_timeout={timeout}s "
            "-c idle_in_transaction_session_timeout=60s"
        )
    local = conn["host"] in ("localhost", "127.0.0.1", "::1")
    return {
        **({"PGSSLROOTCERT": str(Path(conn["sslrootcert"]).expanduser())} if conn.get("sslrootcert") else {}),
        "PGHOST": conn["host"],
        "PGPORT": conn["port"],
        "PGDATABASE": db or conn["dbname"],
        "PGUSER": conn["user"],
        "PGPASSWORD": conn["password"],
        "PGSSLMODE": conn.get("sslmode") or ("prefer" if local else "require"),
        "PGCONNECT_TIMEOUT": "10",
        "PGAPPNAME": "control-postgres",
        "PGOPTIONS": options,
    }


def require_connection() -> dict[str, str]:
    try:
        found = resolve()
    except ValueError as exc:
        typer.echo(f"control-postgres: {exc}", err=True)
        raise typer.Exit(2)
    if not found:
        typer.echo(
            f"control-postgres: no connection. Set {DSN_VARS[0]} (or {DSN_VARS[1]}) in the current repo's .env "
            "or the shell; see the skill's Setup section.",
            err=True,
        )
        raise typer.Exit(2)
    return found[0]


def psql(sql: str, env: dict[str, str], *args: str) -> subprocess.CompletedProcess[str]:
    child_env = {k: v for k, v in os.environ.items() if k not in ("PGSERVICE", "PGSERVICEFILE")}
    return subprocess.run(
        ["psql", "-XAt", "-v", "ON_ERROR_STOP=1", *args],
        input=sql, capture_output=True, text=True, env={**child_env, **env},
    )


def emit(data: Any, fields: Optional[str] = None) -> None:
    """Compact JSON on stdout. --fields a,b keeps only those keys (on a dict or on each dict in a list)."""
    if fields:
        keep = [f.strip() for f in fields.split(",")]
        pick = lambda d: {k: d.get(k) for k in keep} if isinstance(d, dict) else d  # noqa: E731
        data = [pick(d) for d in data] if isinstance(data, list) else pick(data)
    typer.echo(json.dumps(data, separators=(",", ":"), default=str))


def line(status: str, check: str, detail: str = "") -> bool:
    typer.echo(f"{status:<4} {check}" + (f"  {detail}" if detail else ""))
    return status != "FAIL"


def fix(text: str) -> None:
    """The step that clears the FAIL above, printed under it: an exact command, or what the user must do."""
    typer.echo(f"     fix: {text}")


def version_of(binary: str) -> str:
    out = subprocess.run([binary, "--version"], capture_output=True, text=True).stdout
    match = re.search(r"(\d+\.\d+(?:\.\d+)?)", out)
    return match.group(1) if match else "unknown"


# --- doctor ---------------------------------------------------------------


@app.command()
def doctor() -> None:
    """Read-only: one ok/WARN/FAIL line per check, a `fix:` line under each FAIL. Exit 1 on any FAIL."""
    ok = True
    uv = shutil.which("uv")
    line("ok" if uv else "WARN", "uv", f"{version_of('uv')} at {uv}" if uv else "not on PATH (this run found it some other way)")

    psql_path = shutil.which("psql")
    ok &= line("ok" if psql_path else "FAIL", "psql", psql_path or "not on PATH")
    cli_version = ""
    if not psql_path:
        fix(f"{CLIENT_FIX}; ask the user before running it")
    else:
        cli_version = version_of("psql")
        same = cli_version == PROVEN["cli"]
        line("ok" if same else "WARN", "psql version", f"{cli_version} (proven {PROVEN['cli']})" + ("" if same else "; a recipe may have drifted"))
    for helper in ("pg_dump", "jq"):
        path = shutil.which(helper)
        ok &= line("ok" if path else "FAIL", helper, path or "not on PATH")
        if not path:
            fix(CLIENT_FIX if helper == "pg_dump" else JQ_FIX)

    conn: Optional[dict[str, str]] = None
    try:
        found = resolve()
    except ValueError as exc:
        found = None
        ok &= line("FAIL", "connection", str(exc))
        fix("the user corrects that value themselves: postgresql://<user>:<password>@<host>:5432/<database>")
    else:
        if found:
            conn, source = found
            line("ok", "connection", f"{conn['user']}@{conn['host']}:{conn['port']}/{conn['dbname']} from {source}")
            if not conn["password"]:
                ok &= line("FAIL", "password", f"empty in {source}")
                fix("the user adds the password to that value themselves, never into the chat")
        else:
            ok &= line("FAIL", "connection", f"none of {', '.join(DSN_VARS)} or POSTGRES_HOST+POSTGRES_USER in the repo .env or the shell")
            fix(
                f"cd into the repo whose .env holds {DSN_VARS[0]}; or ask the user which server and database, and they add "
                f"`{DSN_VARS[0]}=postgresql://<user>:<password>@<host>:5432/<database>` to the current repo's .env, or "
                "export it in their shell's startup file (~/.bashrc, ~/.zshrc), themselves (the database's owner issues the role)"
            )

    if not ok or conn is None:
        typer.echo("skip host, auth and version checks until the FAILs above are fixed; then rerun doctor")
        sys.exit(1)

    try:
        socket.create_connection((conn["host"], int(conn["port"])), timeout=5).close()
        line("ok", "host", f"{conn['host']}:{conn['port']} reachable")
    except OSError as exc:
        line("FAIL", "host", f"{conn['host']}:{conn['port']}: {exc}")
        fix(f"this machine cannot reach {conn['host']}. When the server is internal, the user connects to the network or VPN "
            "that serves it, then rerun doctor; if the host name is wrong, the user corrects the DSN")
        typer.echo("skip auth and version checks until the host is reachable; then rerun doctor")
        sys.exit(1)

    probe = psql(
        "select current_user, current_database(), split_part(current_setting('server_version'), ' ', 1), "
        "(select ssl from pg_stat_ssl where pid = pg_backend_pid()), current_setting('default_transaction_read_only'), "
        "(select rolsuper from pg_roles where rolname = current_user);",
        session_env(conn), "-F", "|",
    )
    if probe.returncode != 0:
        err = probe.stderr.strip().splitlines()[-1] if probe.stderr.strip() else "psql failed"
        line("FAIL", "auth", err.replace(conn["password"], "***") if conn["password"] else err)
        if "password authentication failed" in err:
            fix("the user corrects the password in the DSN themselves; the database's owner holds it")
        elif "does not exist" in err:
            fix("the user corrects the database or role name in the DSN; list the server's databases from a working DSN with the `list databases` recipe")
        elif "pg_hba.conf" in err:
            fix("this role may not log in from this machine; the user asks whoever runs the server to allow it")
        else:
            fix("read the psql error above; a failure with no clear cause goes to the user, not around it")
        sys.exit(1)
    user, dbname, server_version, ssl, read_only, superuser = probe.stdout.strip().split("|")
    line("ok", "auth", f"role {user} on database {dbname}")
    line("ok" if ssl == "t" else "WARN", "tls", f"encrypted (sslmode={session_env(conn)['PGSSLMODE']}" + ("" if conn.get("sslrootcert") else "; certificate not verified") + ")" if ssl == "t" else "session is not encrypted")
    line("ok" if read_only == "on" else "WARN", "read session", "read-only guard on" if read_only == "on" else "PGOPTIONS did not reach the server (a pooler?); read sessions can write")
    if superuser == "t":
        line("WARN", "role", f"{user} is a superuser: every write reaches every database on the server")
    same = server_version == PROVEN["service"]
    line("ok" if same else "WARN", "server version", f"{server_version} (proven {PROVEN['service']})" + ("" if same else "; a recipe may have drifted"))
    if cli_version and int(cli_version.split(".")[0]) < int(server_version.split(".")[0]):
        line("WARN", "client older than server", f"pg_dump {cli_version} refuses a {server_version} server; install postgresql-client-{server_version.split('.')[0]}")
    sys.exit(0)


# --- session --------------------------------------------------------------


@app.command()
def env(
    write: bool = typer.Option(False, "--write", help="A session that may change data. Default: read-only."),
    db: Optional[str] = typer.Option(None, help="Another database on the same server, same role."),
    timeout: int = typer.Option(60, help="statement_timeout of a read session, in seconds."),
) -> None:
    """Print `export PG…` lines for eval, so plain psql and pg_dump reach the database. Changes nothing itself."""
    try:
        found = resolve()
    except ValueError as exc:
        found, reason = None, str(exc)
    else:
        reason = f"no {DSN_VARS[0]} or {DSN_VARS[1]} in the current repo's .env or the shell"
    if not found:
        typer.echo(f"control-postgres: {reason}. Run doctor.", err=True)
        # Makes the psql that follows fail loudly instead of trying a local socket.
        typer.echo("export PGSERVICE=control-postgres-env-failed")
        raise typer.Exit(2)
    typer.echo("unset PGSERVICE PGSERVICEFILE")
    for name, value in session_env(found[0], write=write, db=db, timeout=timeout).items():
        typer.echo(f"export {name}={shlex.quote(value)}")


# --- chains ---------------------------------------------------------------

DESCRIBE_SQL = """
select json_build_object(
  'table', c.oid::regclass::text,
  'kind', case c.relkind when 'r' then 'table' when 'v' then 'view' when 'm' then 'materialized view' when 'p' then 'partitioned table' else c.relkind::text end,
  'owner', pg_get_userbyid(c.relowner),
  'est_rows', c.reltuples::bigint,
  'size', pg_size_pretty(pg_total_relation_size(c.oid)),
  'columns', (select json_agg(json_build_object('name', a.attname, 'type', format_type(a.atttypid, a.atttypmod),
      'nullable', not a.attnotnull, 'default', coalesce(pg_get_expr(d.adbin, d.adrelid),
      case a.attidentity when 'a' then 'generated always as identity' when 'd' then 'generated by default as identity' end)) order by a.attnum)
    from pg_attribute a left join pg_attrdef d on d.adrelid = a.attrelid and d.adnum = a.attnum
    where a.attrelid = c.oid and a.attnum > 0 and not a.attisdropped),
  'constraints', coalesce((select json_agg(json_build_object('name', conname,
      'type', case contype when 'p' then 'primary key' when 'f' then 'foreign key' when 'u' then 'unique' when 'c' then 'check' else contype::text end,
      'def', pg_get_constraintdef(oid)) order by contype, conname)
    from pg_constraint where conrelid = c.oid), '[]'),
  'indexes', coalesce((select json_agg(json_build_object('name', i.indexrelid::regclass::text, 'def', pg_get_indexdef(i.indexrelid),
      'size', pg_size_pretty(pg_relation_size(i.indexrelid)), 'valid', i.indisvalid) order by i.indexrelid::regclass::text)
    from pg_index i where i.indrelid = c.oid), '[]'),
  'referenced_by', coalesce((select json_agg(json_build_object('table', conrelid::regclass::text, 'name', conname,
      'def', pg_get_constraintdef(oid)) order by conrelid::regclass::text)
    from pg_constraint where confrelid = c.oid and contype = 'f'), '[]')
) from pg_class c where c.oid = :'rel'::regclass;
"""


@app.command()
def describe(
    table: str = typer.Argument(..., help="schema.table, e.g. public.orders. The schema is required."),
    db: Optional[str] = typer.Option(None, help="Another database on the same server."),
    fields: Optional[str] = typer.Option(None, help="Comma-separated keys to keep, e.g. columns,constraints."),
) -> None:
    """Read. One table as JSON: columns, constraints, indexes, incoming foreign keys, size, estimated rows."""
    conn = require_connection()
    session = session_env(conn, db=db)
    session["PGOPTIONS"] += " -c search_path=pg_catalog"  # so every name comes back schema-qualified
    proc = psql(DESCRIBE_SQL, session, "-v", f"rel={table}")
    if proc.returncode != 0:
        typer.echo(proc.stderr.strip()[-500:], err=True)
        raise typer.Exit(1)
    emit(json.loads(proc.stdout), fields)


if __name__ == "__main__":
    app()
