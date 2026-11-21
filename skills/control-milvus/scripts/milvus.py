# /// script
# requires-python = ">=3.11"
# dependencies = ["typer>=0.12", "python-dotenv>=1.0", "pymilvus>=3.0.2,<4"]
# ///
"""control-milvus CLI: the Milvus that MILVUS_URI names, over pymilvus, JSON out.

Run as: uv run ~/.agents/skills/control-milvus/scripts/milvus.py <command>
"""

from __future__ import annotations

import ast
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Optional

import typer
from dotenv import dotenv_values

SERVICE = "milvus"
# Versions the last proof ran against. doctor warns when the installed ones differ.
PROVEN = {"cli": "3.0.2", "service": "2.5.13"}
# Where the instance lives: a setting, read from the current repo's .env first, then the shell. No default.
URI_VAR = "MILVUS_URI"
# Optional: a PEM file holding a private CA, for an https URI. Shared by every control skill.
CA_VAR = "CONTROL_CA_FILE"
# Databases safe to write to without --live: control_sandbox* and the ones MILVUS_SCRATCH_DBS lists. Every other
# database is treated as holding live app data.
def scratch(db: str) -> bool:
    listed = {d.strip() for d in (setting("MILVUS_SCRATCH_DBS")[0] or "").split(",")}
    return db.startswith("control_sandbox") or db in listed

DENSE = {100, 101, 102, 103, 105}  # BINARY, FLOAT, FLOAT16, BFLOAT16, INT8 vectors
SPARSE = 104
VECTORS = DENSE | {SPARSE}

app = typer.Typer(no_args_is_help=True, add_completion=False, pretty_exceptions_enable=False)

DbOpt = typer.Option(..., "--db", help="Database name.")
ColOpt = typer.Option(..., "--col", help="Collection name (or alias).")
LiveOpt = typer.Option(False, "--live", help="Allow writing to a live database. Only when the user named it for this change.")
YesOpt = typer.Option(False, "--yes", help="Execute. Without it, print the preview and exit 3.")


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
    """(value, source): repo .env first, then the shell environment."""
    env = repo_env()
    if env.get(name):
        return env[name], ".env"
    if os.environ.get(name):
        return os.environ[name], "shell"
    return None, "unset"


def client(db: str = "default"):
    import logging

    from pymilvus import MilvusClient

    logging.getLogger("pymilvus").setLevel(logging.CRITICAL)  # errors surface once, via main()

    uri = setting(URI_VAR)[0]
    if not uri:
        fail(f"{URI_VAR} is not in the current repo's .env or the shell; run `doctor` for the fix", 2)
    ca = setting(CA_VAR)[0]
    if ca and uri.startswith("https"):  # gRPC reads its roots from this variable
        os.environ.setdefault("GRPC_DEFAULT_SSL_ROOTS_FILE_PATH", str(Path(ca).expanduser()))
    token = setting("MILVUS_TOKEN")[0] or ""
    return MilvusClient(uri=uri, token=token, db_name=db, timeout=15)


def emit(data: Any) -> None:
    typer.echo(json.dumps(data, separators=(",", ":"), default=str, ensure_ascii=False))


def fail(msg: str, code: int = 1) -> None:
    typer.echo(msg, err=True)
    raise typer.Exit(code)


def guard(db: str, live: bool) -> None:
    if not scratch(db) and not live:
        fail(f"'{db}' holds live app data. Add --live only if the user named this database for this change.", 4)


def preview(data: Any, yes: bool) -> bool:
    """Destructive gate: without --yes, print what would go and exit 3."""
    if yes:
        return True
    emit({"preview": data, "confirm": "show this to the user; rerun with --yes only after their explicit yes"})
    raise typer.Exit(3)


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


def reach(uri: str) -> Optional[str]:
    """None when the URI's host resolves and its port accepts TCP, else the error."""
    import socket
    from urllib.parse import urlparse

    u = urlparse(uri)
    try:
        socket.create_connection((u.hostname or "", u.port or 19530), timeout=5).close()
        return None
    except Exception as e:  # noqa: BLE001
        return f"{type(e).__name__}: {str(e)[:200]}"


def describe(c, col: str) -> dict:
    return c.describe_collection(col)


def fields_of(desc: dict) -> list[dict]:
    return desc["fields"]


def pk_field(desc: dict) -> dict:
    return next(f for f in fields_of(desc) if f.get("is_primary"))


def parse_ids(desc: dict, ids: str) -> list:
    raw = [s.strip() for s in ids.split(",") if s.strip()]
    return [int(s) for s in raw] if int(pk_field(desc)["type"]) == 5 else raw


def function_outputs(desc: dict) -> set[str]:
    return {f["name"] for f in fields_of(desc) if f.get("is_function_output")}


def scalar_fields(desc: dict) -> list[str]:
    return [f["name"] for f in fields_of(desc) if int(f["type"]) not in VECTORS]


def dense_field(desc: dict, name: Optional[str]) -> str:
    if name:
        return name
    dense = [f["name"] for f in fields_of(desc) if int(f["type"]) in DENSE]
    if not dense:
        fail("collection has no dense vector field")
    return dense[0]


def bm25_field(desc: dict, name: Optional[str]) -> str:
    if name:
        return name
    for fn in desc.get("functions", []):
        if int(fn.get("type", 0)) == 1:  # FunctionType.BM25
            return as_list(fn["output_field_names"])[0]
    fail("collection has no BM25 function; pass --field")
    return ""


def as_list(v: Any) -> list[str]:
    return ast.literal_eval(v) if isinstance(v, str) else list(v)


def clip(row: dict, max_chars: int) -> dict:
    if max_chars <= 0:
        return row
    out = {}
    for k, v in row.items():
        if isinstance(v, str) and len(v) > max_chars:
            v = v[:max_chars] + f"…(+{len(v) - max_chars})"
        elif isinstance(v, list) and len(v) > 8 and all(isinstance(x, (int, float)) for x in v[:8]):
            v = f"<vector dim={len(v)}>"
        out[k] = v
    return out


def pick_fields(desc: dict, fields: Optional[str]) -> list[str]:
    return [f.strip() for f in fields.split(",")] if fields else scalar_fields(desc)


def hits(result: list, desc: dict, max_chars: int) -> list[dict]:
    pk = pk_field(desc)["name"]
    return [clip({pk: h[pk], "distance": round(float(h["distance"]), 5), **dict(h.get("entity", {}))}, max_chars)
            for h in result[0]]


def read_rows(path: Path) -> list[dict]:
    text = path.read_text()
    if text.lstrip().startswith("["):
        return json.loads(text)
    return [json.loads(ln) for ln in text.splitlines() if ln.strip()]


def load_state(c, col: str) -> str:
    s = c.get_load_state(col)["state"]
    return getattr(s, "name", str(s))


# --- spec: one JSON shape for describing and creating collections ---------


STAT_KEYS = {"field_name", "index_name", "index_type", "metric_type", "total_rows", "indexed_rows",
             "pending_index_rows", "state", "index_state_fail_reason"}


def plain(v: Any) -> Any:
    if isinstance(v, str):
        if v in ("true", "false"):
            return v == "true"
        if v.lstrip("-").isdigit():
            return int(v)
        if v.startswith("{") or v.startswith("["):
            try:
                return json.loads(v)
            except json.JSONDecodeError:
                return v
    return v


def spec_of(c, col: str) -> dict:
    from pymilvus import DataType

    d = describe(c, col)
    fields = []
    for f in fields_of(d):
        out: dict[str, Any] = {"name": f["name"], "type": DataType(int(f["type"])).name}
        for k in ("is_primary", "auto_id", "nullable", "is_partition_key", "is_clustering_key", "default_value"):
            if f.get(k):
                out[k] = f[k]
        if f.get("element_type") is not None:
            out["element_type"] = DataType(int(f["element_type"])).name
        if f.get("description"):
            out["description"] = f["description"]
        out.update({k: plain(v) for k, v in (f.get("params") or {}).items()})
        fields.append(out)
    functions = [{"name": fn["name"], "type": "BM25" if int(fn["type"]) == 1 else str(fn["type"]),
                  "input": as_list(fn["input_field_names"]), "output": as_list(fn["output_field_names"])}
                 for fn in d.get("functions", [])]
    indexes = []
    for name in c.list_indexes(col):
        ix = c.describe_index(col, name)
        indexes.append({"field": ix["field_name"], "index_name": ix["index_name"], "index_type": ix.get("index_type", ""),
                        **({"metric_type": ix["metric_type"]} if ix.get("metric_type") else {}),
                        "params": {k: plain(v) for k, v in ix.items() if k not in STAT_KEYS}})
    return {"description": d.get("description", ""), "auto_id": d.get("auto_id", False),
            "enable_dynamic_field": d.get("enable_dynamic_field", False),
            "consistency_level": d.get("consistency_level_name", "Bounded"),
            "fields": fields, "functions": functions, "indexes": indexes}


def build(c, spec: dict):
    from pymilvus import DataType, Function, FunctionType

    schema = c.create_schema(auto_id=spec.get("auto_id", False),
                             enable_dynamic_field=spec.get("enable_dynamic_field", False),
                             description=spec.get("description", ""))
    for f in spec["fields"]:
        f = dict(f)
        name, dtype = f.pop("name"), DataType[f.pop("type")]
        if "element_type" in f:
            f["element_type"] = DataType[f["element_type"]]
        schema.add_field(name, dtype, **f)
    for fn in spec.get("functions", []):
        schema.add_function(Function(name=fn["name"], function_type=FunctionType[fn["type"]],
                                     input_field_names=fn["input"], output_field_names=fn["output"]))
    ip = c.prepare_index_params()
    for ix in spec.get("indexes", []):
        ip.add_index(field_name=ix["field"], index_name=ix.get("index_name", ""), index_type=ix.get("index_type", ""),
                     metric_type=ix.get("metric_type", ""), params=ix.get("params", {}))
    return schema, ip


# --- doctor ---------------------------------------------------------------


@app.command()
def doctor() -> None:
    """Read-only: one ok/WARN/FAIL line per check, a `fix:` line under each FAIL. Exit 1 on any FAIL."""
    import pymilvus

    ok = True
    sdk = pymilvus.__version__
    line("ok" if sdk == PROVEN["cli"] else "WARN", "pymilvus", f"{sdk} (proven {PROVEN['cli']})")
    uri, src = setting(URI_VAR)
    ok &= line("ok" if uri else "FAIL", URI_VAR, f"{uri} (from {src})" if uri else "not in the current repo's .env or the shell")
    if not uri:
        fix(f"ask the user for their Milvus address (http://<host>:19530). They add {URI_VAR}=… to the current repo's "
            f".env when it belongs to this project, or `export {URI_VAR}=…` to {STARTUP} for every repo")
    tok, tsrc = setting("MILVUS_TOKEN")
    line("ok", "MILVUS_TOKEN", f"set (from {tsrc})" if tok else "empty (right when the server has authentication off)")
    jq = shutil.which("jq")
    ok &= line("ok" if jq else "FAIL", "jq", jq or "not on PATH (recipes pipe through jq)")
    if not jq:
        fix(JQ_FIX)
    if uri:
        err = reach(uri)
        ok &= line("ok" if not err else "FAIL", "reachable", uri if not err else err)
        if err:
            from urllib.parse import urlparse

            fix(NET_FIX.format(host=urlparse(uri).hostname, source=f"{URI_VAR} (from {src})")
                + ". If it still fails, tell the user: the server may be down")
    if not ok:
        typer.echo("skip server version and database checks until the FAILs above are fixed; then rerun doctor")
        sys.exit(1)
    try:
        c = client()
        svc = c.get_server_version().lstrip("v")
        line("ok" if svc == PROVEN["service"] else "WARN", "server version", f"{svc} (proven {PROVEN['service']})")
        dbs = c.list_databases()
        line("ok", "list databases", f"{len(dbs)} databases")
    except Exception as e:  # noqa: BLE001
        ok &= line("FAIL", "connect", f"{type(e).__name__}: {str(e)[:200]}")
        fix("the port answers but Milvus does not: tell the user. A token error means authentication is on: the user "
            "puts MILVUS_TOKEN in the current repo's .env or their shell themselves. A certificate error on an https "
            f"URI means a private CA: the user points {CA_VAR} at that CA's PEM file, in .env or {STARTUP}")
    sys.exit(0 if ok else 1)


# --- databases ------------------------------------------------------------


@app.command("dbs")
def dbs() -> None:
    """Read. Every database with its collection count and whether it is scratch or live."""
    c = client()
    out = []
    for db in c.list_databases():
        c.use_database(db)
        out.append({"db": db, "collections": len(c.list_collections()), "scratch": scratch(db)})
    emit(out)


@app.command("db-create")
def db_create(name: str = typer.Argument(..., help="New database name.")) -> None:
    """Write. Create an empty database."""
    c = client()
    if name in c.list_databases():
        fail(f"database '{name}' already exists")
    c.create_database(name)
    emit({"created": name})


@app.command("db-drop")
def db_drop(name: str = typer.Argument(...), live: bool = LiveOpt, yes: bool = YesOpt) -> None:
    """Destructive. Drop a database. Milvus refuses while it still has collections."""
    guard(name, live)
    c = client(name)
    cols = c.list_collections()
    if cols:
        fail(f"'{name}' still has {len(cols)} collections: {cols[:20]}. Drop them first (col-drop).")
    preview({"drop_database": name, "collections": cols}, yes)
    c.drop_database(name)
    emit({"dropped": name})


# --- collections ----------------------------------------------------------


@app.command("cols")
def cols(db: str = DbOpt) -> None:
    """Read. Collections in a database: stored rows, load state, vector fields."""
    c = client(db)
    out = []
    for col in sorted(c.list_collections()):
        d = describe(c, col)
        out.append({"col": col, "stored_rows": int(c.get_collection_stats(col)["row_count"]),
                    "load": load_state(c, col), "aliases": d.get("aliases", []),
                    "vectors": {f["name"]: f.get("params", {}).get("dim", "sparse")
                                for f in fields_of(d) if int(f["type"]) in VECTORS}})
    emit(out)


@app.command("col-show")
def col_show(db: str = DbOpt, col: str = ColOpt) -> None:
    """Read. One collection: fields, functions, indexes, aliases, load state, live row count."""
    c = client(db)
    spec = spec_of(c, col)
    d = describe(c, col)
    state = load_state(c, col)
    live = c.query(col, filter="", output_fields=["count(*)"])[0]["count(*)"] if state == "Loaded" else None
    idx = []
    for name in c.list_indexes(col):
        ix = c.describe_index(col, name)
        idx.append({"field": ix["field_name"], "type": ix.get("index_type", "default"), "metric": ix.get("metric_type"),
                    "state": ix.get("state"), "pending": ix.get("pending_index_rows")})
    emit({"col": d["collection_name"], "load": state, "rows": live,
          "stored_rows": int(c.get_collection_stats(col)["row_count"]), "aliases": d.get("aliases", []),
          "consistency": spec["consistency_level"], "dynamic": spec["enable_dynamic_field"],
          "partitions": c.list_partitions(col),
          "fields": [{k: v for k, v in f.items() if k in ("name", "type", "is_primary", "dim", "max_length", "nullable")}
                     for f in spec["fields"]],
          "functions": spec["functions"], "indexes": idx})


@app.command("col-spec")
def col_spec(db: str = DbOpt, col: str = ColOpt) -> None:
    """Read. The collection's schema + functions + indexes as a spec that col-create accepts."""
    emit(spec_of(client(db), col))


@app.command("col-create")
def col_create(
    db: str = DbOpt,
    col: str = ColOpt,
    spec: Optional[Path] = typer.Option(None, help="Spec JSON file (the col-spec shape)."),
    like: Optional[str] = typer.Option(None, help="Copy the spec of an existing collection: <db>/<col>."),
    live: bool = LiveOpt,
) -> None:
    """Write. Create a collection from a spec file or like an existing one. It is indexed and loaded."""
    guard(db, live)
    if bool(spec) == bool(like):
        fail("pass exactly one of --spec or --like")
    if like:
        src_db, _, src_col = like.partition("/")
        s = spec_of(client(src_db), src_col)
    else:
        s = json.loads(spec.read_text())  # type: ignore[union-attr]
    c = client(db)
    if c.has_collection(col):
        fail(f"'{db}/{col}' already exists")
    schema, ip = build(c, s)
    c.create_collection(col, schema=schema, index_params=ip, consistency_level=s.get("consistency_level", "Bounded"))
    emit({"created": f"{db}/{col}", "load": load_state(c, col)})


@app.command("col-load")
def col_load(db: str = DbOpt, col: str = ColOpt, live: bool = LiveOpt) -> None:
    """Write. Load a collection into memory so it can be searched and queried."""
    guard(db, live)
    c = client(db)
    c.load_collection(col)
    emit({"col": col, "load": load_state(c, col)})


@app.command("col-release")
def col_release(db: str = DbOpt, col: str = ColOpt, live: bool = LiveOpt) -> None:
    """Write. Release a collection from memory. Searches and queries on it fail until it is loaded again."""
    guard(db, live)
    c = client(db)
    c.release_collection(col)
    emit({"col": col, "load": load_state(c, col)})


@app.command("alias-set")
def alias_set(db: str = DbOpt, col: str = ColOpt, alias: str = typer.Option(...), live: bool = LiveOpt) -> None:
    """Write. Point an alias at a collection: creates it, or moves it from the collection it named before."""
    guard(db, live)
    c = client(db)
    before = c.describe_alias(alias)["collection_name"] if alias in c.list_aliases()["aliases"] else None
    (c.alter_alias if before else c.create_alias)(col, alias)
    emit({"alias": alias, "before": before, "now": c.describe_alias(alias)["collection_name"]})


@app.command("alias-drop")
def alias_drop(db: str = DbOpt, alias: str = typer.Option(...), live: bool = LiveOpt, yes: bool = YesOpt) -> None:
    """Destructive. Remove an alias; apps addressing the alias start failing."""
    guard(db, live)
    c = client(db)
    preview({"drop_alias": alias, "points_at": c.describe_alias(alias)["collection_name"], "db": db}, yes)
    c.drop_alias(alias)
    emit({"dropped_alias": alias})


@app.command("col-drop")
def col_drop(db: str = DbOpt, col: str = ColOpt, live: bool = LiveOpt, yes: bool = YesOpt) -> None:
    """Destructive. Drop a collection and all its data."""
    guard(db, live)
    c = client(db)
    d = describe(c, col)
    if d.get("aliases"):
        fail(f"'{col}' still has aliases {d['aliases']}: move them (alias-set) or drop them (alias-drop) first.")
    preview({"drop_collection": f"{db}/{col}", "stored_rows": int(c.get_collection_stats(col)["row_count"]),
             "load": load_state(c, col)}, yes)
    c.drop_collection(col)
    emit({"dropped": f"{db}/{col}"})


# --- entities -------------------------------------------------------------


@app.command("count")
def count(db: str = DbOpt, col: str = ColOpt, filter: str = typer.Option("", "--filter", help="Boolean expression.")) -> None:
    """Read. Live entities matching a filter (all when empty)."""
    c = client(db)
    emit({"count": c.query(col, filter=filter, output_fields=["count(*)"])[0]["count(*)"]})


@app.command("query")
def query(
    db: str = DbOpt,
    col: str = ColOpt,
    filter: str = typer.Option("", "--filter", help="Boolean expression; empty needs --limit."),
    fields: Optional[str] = typer.Option(None, help="Comma-separated output fields. Default: every scalar field."),
    limit: int = typer.Option(10, help="Maximum rows."),
    max_chars: int = typer.Option(300, help="Cut strings longer than this; 0 keeps them whole."),
    with_vectors: bool = typer.Option(False, help="Whole rows, vectors included, ready for insert/upsert. Redirect to a file."),
) -> None:
    """Read. Entities matching a filter. Vectors are left out unless named in --fields or --with-vectors."""
    c = client(db)
    d = describe(c, col)
    if with_vectors:
        skip = function_outputs(d)
        out = [f["name"] for f in fields_of(d) if f["name"] not in skip]
        emit([dict(r) for r in c.query(col, filter=filter, output_fields=out, limit=limit)])
        return
    rows = c.query(col, filter=filter, output_fields=pick_fields(d, fields), limit=limit)
    emit([clip(dict(r), max_chars) for r in rows])


@app.command("get")
def get(
    db: str = DbOpt,
    col: str = ColOpt,
    ids: str = typer.Option(..., help="Comma-separated primary keys."),
    fields: Optional[str] = typer.Option(None, help="Comma-separated output fields. Default: every scalar field."),
    max_chars: int = typer.Option(300, help="Cut strings longer than this; 0 keeps them whole."),
) -> None:
    """Read. Entities by primary key."""
    c = client(db)
    d = describe(c, col)
    emit([clip(dict(r), max_chars) for r in c.get(col, ids=parse_ids(d, ids), output_fields=pick_fields(d, fields))])


def _write(op: str, db: str, col: str, file: Path, batch: int) -> None:
    c = client(db)
    rows = read_rows(file)
    n, ids = 0, []
    for i in range(0, len(rows), batch):
        r = getattr(c, op)(col, rows[i:i + batch])
        n += int(r.get("insert_count", r.get("upsert_count", 0)))
        ids += list(r.get("ids", []))[:20 - len(ids)]
    emit({op: n, "first_ids": ids})


@app.command("insert")
def insert(db: str = DbOpt, col: str = ColOpt, file: Path = typer.Option(..., help="JSONL or JSON array of rows."),
           batch: int = typer.Option(500), live: bool = LiveOpt) -> None:
    """Write. Insert rows. Leave function-output fields (bm25_vector) out; Milvus computes them."""
    guard(db, live)
    _write("insert", db, col, file, batch)


@app.command("upsert")
def upsert(db: str = DbOpt, col: str = ColOpt, file: Path = typer.Option(..., help="JSONL or JSON array of rows."),
           batch: int = typer.Option(500), live: bool = LiveOpt) -> None:
    """Write. Insert rows, replacing whole rows whose primary key exists."""
    guard(db, live)
    _write("upsert", db, col, file, batch)


@app.command("patch")
def patch(
    db: str = DbOpt,
    col: str = ColOpt,
    ids: str = typer.Option(..., help="Comma-separated primary keys."),
    set_: str = typer.Option(..., "--set", help='JSON object of scalar fields to change, e.g. {"doc_title":"x"}.'),
    live: bool = LiveOpt,
) -> None:
    """Write. Change some fields of existing rows: reads each whole row, merges, upserts. Vectors are kept."""
    guard(db, live)
    c = client(db)
    d = describe(c, col)
    if d.get("auto_id"):
        fail("auto_id collection: upsert would not keep the primary key; re-insert instead")
    changes = json.loads(set_)
    pk, skip = pk_field(d)["name"], function_outputs(d)
    if bad := set(changes) & (skip | {pk}):
        fail(f"cannot patch {sorted(bad)}: primary key or function output")
    rows = c.get(col, ids=parse_ids(d, ids), output_fields=["*"])
    if not rows:
        fail(f"no entity with ids {ids}")
    c.upsert(col, [{**{k: v for k, v in dict(r).items() if k not in skip}, **changes} for r in rows])
    emit({"patched": [r[pk] for r in rows], "fields": sorted(changes)})


@app.command("delete")
def delete(
    db: str = DbOpt,
    col: str = ColOpt,
    ids: Optional[str] = typer.Option(None, help="Comma-separated primary keys."),
    filter: Optional[str] = typer.Option(None, "--filter", help="Boolean expression."),
    live: bool = LiveOpt,
    yes: bool = YesOpt,
) -> None:
    """Destructive. Delete entities by primary key or filter."""
    guard(db, live)
    if bool(ids) == bool(filter):
        fail("pass exactly one of --ids or --filter")
    c = client(db)
    d = describe(c, col)
    pk = pk_field(d)["name"]
    if ids:
        id_list = parse_ids(d, ids)
        expr = f"{pk} in {json.dumps(id_list)}"
    else:
        expr = filter  # type: ignore[assignment]
    n = c.query(col, filter=expr, output_fields=["count(*)"])[0]["count(*)"]
    sample = [r[pk] for r in c.query(col, filter=expr, output_fields=[pk], limit=5)]
    preview({"delete_from": f"{db}/{col}", "filter": expr, "matching": n, "sample_ids": sample}, yes)
    r = c.delete(col, filter=expr)
    emit({"deleted": r.get("delete_count", n) if isinstance(r, dict) else n})


@app.command("copy-rows")
def copy_rows(
    src: str = typer.Option(..., "--from", help="<db>/<col> to read."),
    dst: str = typer.Option(..., "--to", help="<db>/<col> to insert into; same schema."),
    filter: str = typer.Option("", "--filter", help="Copy only matching rows."),
    batch: int = typer.Option(500),
    live: bool = LiveOpt,
) -> None:
    """Write. Copy rows between collections with the same schema (e.g. into a new _vN), vectors included."""
    sdb, _, scol = src.partition("/")
    ddb, _, dcol = dst.partition("/")
    guard(ddb, live)
    s, t = client(sdb), client(ddb)
    skip = function_outputs(describe(s, scol))
    it = s.query_iterator(scol, batch_size=batch, filter=filter, output_fields=["*"])
    n = 0
    try:
        while rows := it.next():
            t.insert(dcol, [{k: v for k, v in dict(r).items() if k not in skip} for r in rows])
            n += len(rows)
    finally:
        it.close()
    emit({"copied": n, "from": src, "to": dst})


# --- search ---------------------------------------------------------------


SearchLimit = typer.Option(10, help="Maximum hits.")
SearchFields = typer.Option(None, help="Comma-separated output fields. Default: every scalar field.")
SearchChars = typer.Option(200, help="Cut strings longer than this; 0 keeps them whole.")
SearchFilter = typer.Option("", "--filter", help="Boolean pre-filter.")


@app.command("similar")
def similar(
    db: str = DbOpt, col: str = ColOpt,
    id: str = typer.Option(..., "--id", help="Primary key of the stored entity whose vector is the query."),
    field: Optional[str] = typer.Option(None, help="Dense vector field. Default: the first one."),
    filter: str = SearchFilter, limit: int = SearchLimit, fields: Optional[str] = SearchFields, max_chars: int = SearchChars,
) -> None:
    """Read. Nearest neighbours of a stored entity's vector. The entity itself is the first hit."""
    c = client(db)
    d = describe(c, col)
    vf = dense_field(d, field)
    got = c.get(col, ids=parse_ids(d, id), output_fields=[vf])
    if not got:
        fail(f"no entity with id {id}")
    r = c.search(col, data=[got[0][vf]], anns_field=vf, filter=filter, limit=limit, output_fields=pick_fields(d, fields))
    emit(hits(r, d, max_chars))


@app.command("bm25")
def bm25(
    db: str = DbOpt, col: str = ColOpt,
    text: str = typer.Option(..., help="Keyword query."),
    field: Optional[str] = typer.Option(None, help="Sparse BM25 output field. Default: the BM25 function's output."),
    filter: str = SearchFilter, limit: int = SearchLimit, fields: Optional[str] = SearchFields, max_chars: int = SearchChars,
) -> None:
    """Read. Full-text (BM25) search on a collection with a BM25 function."""
    c = client(db)
    d = describe(c, col)
    r = c.search(col, data=[text], anns_field=bm25_field(d, field), filter=filter, limit=limit,
                 search_params={"metric_type": "BM25"}, output_fields=pick_fields(d, fields))
    emit(hits(r, d, max_chars))


@app.command("hybrid")
def hybrid(
    db: str = DbOpt, col: str = ColOpt,
    id: str = typer.Option(..., "--id", help="Stored entity whose dense vector is the semantic half."),
    text: str = typer.Option(..., help="Keyword query for the BM25 half."),
    k: int = typer.Option(60, help="RRF k."),
    filter: str = SearchFilter, limit: int = SearchLimit, fields: Optional[str] = SearchFields, max_chars: int = SearchChars,
) -> None:
    """Read. Dense (stored entity's vector) + BM25 (text), fused with RRF."""
    from pymilvus import AnnSearchRequest, RRFRanker

    c = client(db)
    d = describe(c, col)
    vf, sf = dense_field(d, None), bm25_field(d, None)
    got = c.get(col, ids=parse_ids(d, id), output_fields=[vf])
    if not got:
        fail(f"no entity with id {id}")
    reqs = [AnnSearchRequest(data=[got[0][vf]], anns_field=vf, param={}, limit=limit, filter=filter or None),
            AnnSearchRequest(data=[text], anns_field=sf, param={"metric_type": "BM25"}, limit=limit, filter=filter or None)]
    r = c.hybrid_search(col, reqs=reqs, ranker=RRFRanker(k), limit=limit, output_fields=pick_fields(d, fields))
    emit(hits(r, d, max_chars))


def main() -> None:
    from pymilvus.exceptions import MilvusException

    try:
        app()
    except MilvusException as e:
        typer.echo(f"milvus error {e.code}: {e.message}", err=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
