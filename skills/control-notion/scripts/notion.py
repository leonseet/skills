# /// script
# requires-python = ">=3.11"
# dependencies = ["typer>=0.12"]
# ///
"""control-notion helpers: doctor, and the chains over the ntn CLI that plain commands make clumsy. ntn stays the main interface.

Run as: uv run ~/.agents/skills/control-notion/scripts/notion.py <command>
"""

from __future__ import annotations

import json
import mimetypes
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path
from typing import Any, Optional

import typer

SERVICE = "notion"
# Versions the last proof ran against: ntn, and the Notion-Version header it sends. doctor warns when they differ.
PROVEN = {"cli": "0.23.28", "service": "2026-03-11"}
JQ_FIX = "`brew install jq` (macOS) or `sudo apt install jq` (Debian/Ubuntu; other Linux: your package manager)"
STARTUP = "the shell's startup file (~/.bashrc, ~/.zshrc)"
AUTH_FILE = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config") / "notion" / "auth.json"

# Errors after which the request certainly did not apply, so even a write may be resent.
RETRY_ALWAYS = ("rate_limited", "conflict_error")
# Errors after which a read is safe to resend; a write may or may not have landed.
RETRY_READS = ("Failed to execute public API request", "service_unavailable", "gateway_timeout",
               "internal_server_error", "service_overload", "Request timed out")
MEDIA = {"image", "file", "pdf", "video", "audio"}
# Blocks the append endpoint cannot create: copy-blocks skips them and says so.
UNCOPYABLE = {"child_page", "child_database", "unsupported", "link_preview", "meeting_notes", "transcription", "ai_block"}

app = typer.Typer(no_args_is_help=True, add_completion=False)


# --- helpers --------------------------------------------------------------


def die(msg: str, code: int = 1) -> None:
    typer.echo(msg, err=True)
    raise typer.Exit(code)


def emit(data: Any) -> None:
    typer.echo(json.dumps(data, separators=(",", ":"), ensure_ascii=False, default=str))


def nid(ref: str) -> str:
    """A Notion id from an id (dashed or not) or a notion.so / app.notion.com URL."""
    m = re.search(r"[?&]p=([0-9a-f]{32})", ref)
    if m:
        return m.group(1)
    hexes = re.findall(r"[0-9a-f]{32}", ref.split("?")[0].replace("-", ""))
    if not hexes:
        die(f"not a Notion id or URL: {ref}", 2)
    return hexes[-1]


def ntn(*args: str, body: Any = None, write: bool = False, tries: int = 5) -> Any:
    """Run ntn with stdin closed (an open stdin makes `ntn api` wait for a body) and parse its JSON."""
    argv = ["ntn", *args]
    tmp = None
    if body is not None:
        tmp = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False)
        json.dump(body, tmp)
        tmp.close()
        argv += ["-d", f"@{tmp.name}"]
    try:
        for attempt in range(tries):
            proc = subprocess.run(argv, stdin=subprocess.DEVNULL, capture_output=True, text=True)
            if proc.returncode == 0:
                return json.loads(proc.stdout) if proc.stdout.strip() else None
            err = proc.stderr.strip()
            retry = any(t in err for t in RETRY_ALWAYS) or (not write and any(t in err for t in RETRY_READS))
            if retry and attempt < tries - 1:
                time.sleep(2 ** attempt)
                continue
            if write and any(t in err for t in RETRY_READS):
                err += "\nthe write may or may not have landed: list the parent's children before rerunning."
            die(f"ntn {' '.join(args[:2])} failed: {err[-800:]}")
    finally:
        if tmp:
            os.unlink(tmp.name)


def list_children(block_id: str) -> list[dict]:
    out: list[dict] = []
    cursor = None
    while True:
        args = ["api", f"v1/blocks/{block_id}/children", "page_size==100"]
        if cursor:
            args.append(f"start_cursor=={cursor}")
        page = ntn(*args)
        out += page["results"]
        if not page.get("has_more"):
            return out
        cursor = page["next_cursor"]


def block_text(b: dict) -> str:
    t = b["type"]
    body = b.get(t) or {}
    if t in ("child_page", "child_database"):
        return body.get("title", "")
    if t == "table_row":
        return " | ".join("".join(x["plain_text"] for x in cell) for cell in body.get("cells", []))
    rich = body.get("rich_text") or body.get("caption") or []
    return "".join(x.get("plain_text", "") for x in rich)


def strip(value: Any) -> Any:
    """Drop nulls recursively: the API rejects e.g. `icon: null` that it returns on read."""
    if isinstance(value, dict):
        return {k: strip(v) for k, v in value.items() if v is not None}
    if isinstance(value, list):
        return [strip(v) for v in value]
    return value


def upload_bytes(path: Path, content_type: Optional[str] = None) -> str:
    ctype = content_type or mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    with path.open("rb") as fh:
        proc = subprocess.run(
            ["ntn", "files", "create", "--filename", path.name, "--content-type", ctype, "--json"],
            stdin=fh, capture_output=True, text=True,
        )
    if proc.returncode != 0:
        die(f"upload of {path.name} failed: {proc.stderr.strip()[-500:]}")
    up = json.loads(proc.stdout)
    if up.get("status") != "uploaded":
        die(f"upload of {path.name} ended in status {up.get('status')}")
    return up["id"]


def reupload(url: str, name: str) -> str:
    """Notion-hosted files come back as signed S3 URLs that cannot be sent back: fetch the bytes, upload them anew."""
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / name
        with urllib.request.urlopen(url) as r:
            path.write_bytes(r.read())
        return upload_bytes(path)


def position(after: Optional[str], start: bool) -> dict:
    if after:
        return {"type": "after_block", "after_block": {"id": nid(after)}}
    return {"type": "start"} if start else {"type": "end"}


def append(parent: str, blocks: list[dict], pos: dict) -> list[str]:
    """Append blocks in chunks of 100 at pos; return the new ids in order."""
    ids: list[str] = []
    for i in range(0, len(blocks), 100):
        chunk = blocks[i:i + 100]
        res = ntn("api", f"v1/blocks/{parent}/children", "-X", "PATCH",
                  body={"position": pos, "children": chunk}, write=True)
        results = res["results"]
        # The response lists the parent's children from the first new block on, except for an
        # end append, where it lists the whole (first page of the) parent: the new ones are last.
        new = results[-len(chunk):] if pos["type"] == "end" else results[:len(chunk)]
        ids += [b["id"] for b in new]
        pos = {"type": "after_block", "after_block": {"id": ids[-1]}}
    return ids


def to_input(b: dict, skipped: list[str]) -> Optional[dict]:
    """A read block as append input, without its children (copy_tree appends those level by level)."""
    t = b["type"]
    if t in UNCOPYABLE:
        skipped.append(f"{t} {b['id']} {block_text(b)[:60]}")
        return None
    body = dict(b.get(t) or {})
    if t in MEDIA and body.get("type") == "file":
        name = Path(body["file"]["url"].split("?")[0]).name or f"{t}.bin"
        body = {"type": "file_upload", "file_upload": {"id": reupload(body["file"]["url"], name)},
                "caption": body.get("caption", [])}
    if t == "embed" and body.get("url", "").startswith("https://prod-files-secure."):
        name = Path(body["url"].split("?")[0]).name or "embed.html"
        body = {"type": "file_upload", "file_upload": {"id": reupload(body["url"], name)}}
    if t == "table":
        # A table is created together with its rows.
        body["children"] = [{"type": "table_row", "table_row": r["table_row"]} for r in list_children(b["id"])]
    if t == "column_list":
        # Columns are created together with their content; content nested deeper than that is dropped.
        cols = []
        for c in list_children(b["id"]):
            kids = [x for x in (to_input(k, skipped) for k in list_children(c["id"])) if x]
            cols.append({"type": "column", "column": {"children": kids}})
        body["children"] = cols
    if t == "synced_block" and body.get("synced_from"):
        skipped.append(f"synced_block {b['id']} (a reference to another synced block)")
        return None
    return {"type": t, t: strip(body)}


def copy_tree(src_blocks: list[dict], dest: str, pos: dict, skipped: list[str]) -> int:
    pairs = [(b, x) for b in src_blocks if (x := to_input(b, skipped))]
    if not pairs:
        return 0
    new_ids = append(dest, [x for _, x in pairs], pos)
    count = len(new_ids)
    for (b, _), new_id in zip(pairs, new_ids):
        if b.get("has_children") and b["type"] not in ("table", "column_list"):
            count += copy_tree(list_children(b["id"]), new_id, {"type": "end"}, skipped)
    return count


def line(status: str, check: str, detail: str = "") -> bool:
    typer.echo(f"{status:<4} {check}" + (f"  {detail}" if detail else ""))
    return status != "FAIL"


def fix(text: str) -> None:
    typer.echo(f"     fix: {text}")


# --- doctor ---------------------------------------------------------------


@app.command()
def doctor() -> None:
    """Read-only: one ok/WARN/FAIL line per check, a `fix:` line under each FAIL. Exit 1 on any FAIL."""
    ok = True
    line("ok", "uv", f"python {sys.version.split()[0]}")
    cli = shutil.which("ntn")
    ok &= line("ok" if cli else "FAIL", "ntn", cli or "not on PATH")
    if not cli:
        fix("the user installs it in their own terminal: `curl -fsSL https://ntn.dev | bash` (puts ntn in ~/.local/bin, which must be on PATH)")
    else:
        v = subprocess.run(["ntn", "--version"], stdin=subprocess.DEVNULL, capture_output=True, text=True).stdout.split()
        version = v[-1] if v else "?"
        line("ok" if version == PROVEN["cli"] else "WARN", "ntn version", f"{version} (proven {PROVEN['cli']})"
             + ("" if version == PROVEN["cli"] else "; recipes may have drifted, check `ntn <command> --help`"))
    jq = shutil.which("jq")
    ok &= line("ok" if jq else "FAIL", "jq", jq or "not on PATH")
    if not jq:
        fix(JQ_FIX)

    if os.environ.get("NOTION_API_TOKEN"):
        line("ok", "credentials", "NOTION_API_TOKEN from the shell environment (overrides the saved login)")
    elif os.environ.get("NOTION_KEYRING") != "0":
        line("ok", "credentials", "ntn login in the OS keychain (NOTION_KEYRING is not 0); the auth check below proves it")
    elif not AUTH_FILE.exists():
        ok &= line("FAIL", "credentials", f"no saved login at {AUTH_FILE}")
        fix("the user runs `ntn login` in their own terminal (it opens a browser) and picks the workspace")
    else:
        line("ok", "credentials", f"saved ntn login in {AUTH_FILE}")

    if not ok:
        typer.echo("skip auth, workspace and API version checks until the FAILs above are fixed; then rerun doctor")
        sys.exit(1)

    proc = subprocess.run(["ntn", "api", "v1/users/me", "-v"], stdin=subprocess.DEVNULL, capture_output=True, text=True)
    if proc.returncode != 0:
        err = proc.stderr.strip().splitlines()
        line("FAIL", "auth", next((e for e in err if e.startswith("error")), err[-1] if err else "ntn api v1/users/me failed"))
        if "keychain" in proc.stderr.lower() or ("No auth token" in proc.stderr and os.environ.get("NOTION_KEYRING") != "0"):
            fix("the user runs `ntn login` in their own terminal (it opens a browser). If that fails with `Failed to create keychain entry`, "
                f"this machine has no OS keychain: add `export NOTION_KEYRING=0` to {STARTUP}, open a new shell, then `ntn login` "
                "(ntn then keeps its login in ~/.config/notion/auth.json)")
        elif any(s in proc.stderr for s in ("token is invalid", "No auth token", "unauthorized")):
            fix("the user runs `ntn login` in their own terminal (it opens a browser), or replaces NOTION_API_TOKEN in their shell")
        else:
            fix("check the network to api.notion.com (`curl -sI https://api.notion.com/v1/users/me`), then rerun doctor")
        sys.exit(1)
    me = json.loads(proc.stdout)
    ws = (me.get("bot") or {}).get("workspace_name", "?")
    line("ok", "auth", f"{me.get('name')} ({me.get('type')}) in {ws}")
    wmap = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config") / "control-notion" / "workspace.md"
    line("ok", "workspace", ws + (f"; map at {wmap}" if wmap.exists() else f"; no workspace map at {wmap} yet (SKILL.md says what goes in it)"))
    m = re.search(r"notion-version:\s*(\S+)", proc.stderr + proc.stdout, re.I)
    api = m.group(1) if m else "?"
    line("ok" if api == PROVEN["service"] else "WARN", "API version", f"{api} (proven {PROVEN['service']})"
         + ("" if api == PROVEN["service"] else "; request shapes may have drifted, check `ntn api <path> --spec`"))
    sys.exit(0)


# --- chains ---------------------------------------------------------------


@app.command()
def children(
    ref: str = typer.Argument(..., help="Page or block id or URL."),
    deep: bool = typer.Option(False, help="Recurse into blocks with children (not into child pages)."),
    width: int = typer.Option(100, help="Truncate each block's text to this many characters."),
    limit: int = typer.Option(500, help="Stop after this many blocks."),
) -> None:
    """Read. Every child block, all pages followed: [{depth, id, type, has_children, text}]."""
    out: list[dict] = []

    def walk(bid: str, depth: int) -> None:
        for b in list_children(bid):
            if len(out) >= limit:
                return
            out.append({"depth": depth, "id": b["id"], "type": b["type"], "has_children": b["has_children"],
                        "text": block_text(b)[:width]})
            if deep and b["has_children"] and b["type"] not in ("child_page", "child_database"):
                walk(b["id"], depth + 1)

    walk(nid(ref), 0)
    emit(out)


@app.command()
def images(
    ref: str = typer.Argument(..., help="Page or block id or URL."),
    deep: bool = typer.Option(True, help="Recurse into blocks with children (not into child pages)."),
) -> None:
    """Read. Every image block, in page order: [{id, caption, links, source}]. `links` are the caption's hrefs."""
    out: list[dict] = []

    def walk(bid: str) -> None:
        for b in list_children(bid):
            if b["type"] == "image":
                cap = b["image"].get("caption") or []
                out.append({"id": b["id"], "caption": "".join(x.get("plain_text", "") for x in cap),
                            "links": [x["href"] for x in cap if x.get("href")], "source": b["image"].get("type")})
            elif deep and b["has_children"] and b["type"] not in ("child_page", "child_database"):
                walk(b["id"])

    walk(nid(ref))
    emit(out)


@app.command()
def attach(
    file: Path = typer.Argument(..., exists=True, dir_okay=False, help="Local file to upload."),
    to: str = typer.Option(..., "--to", help="Page or block id or URL to append under."),
    as_: Optional[str] = typer.Option(None, "--as", help="image | embed | file | pdf | video | audio. Default from the MIME type."),
    after: Optional[str] = typer.Option(None, help="Insert after this child block id."),
    start: bool = typer.Option(False, help="Insert as the first child."),
    caption: Optional[str] = typer.Option(None, help="Plain-text caption."),
    content_type: Optional[str] = typer.Option(None, help="MIME type override."),
) -> None:
    """Write. Upload a file and append it as one block: {block_id, type, upload_id}."""
    ctype = content_type or mimetypes.guess_type(file.name)[0] or "application/octet-stream"
    kind = as_ or ("image" if ctype.startswith("image/") else "embed" if ctype == "text/html"
                   else "pdf" if ctype == "application/pdf" else "video" if ctype.startswith("video/")
                   else "audio" if ctype.startswith("audio/") else "file")
    if kind not in MEDIA | {"embed"}:
        die(f"--as must be one of image, embed, file, pdf, video, audio; got {kind}", 2)
    up = upload_bytes(file, ctype)
    body: dict = {"type": "file_upload", "file_upload": {"id": up}}
    if caption:
        body["caption"] = [{"type": "text", "text": {"content": caption}}]
    [block_id] = append(nid(to), [{"type": kind, kind: body}], position(after, start))
    emit({"block_id": block_id, "type": kind, "upload_id": up})


@app.command("copy-blocks")
def copy_blocks(
    src: str = typer.Argument(..., help="Block or page id or URL to copy from."),
    to: str = typer.Option(..., "--to", help="Page or block id or URL to copy into."),
    children_only: bool = typer.Option(False, "--children-only", help="Copy SRC's children, not SRC itself (always so for a page)."),
    after: Optional[str] = typer.Option(None, help="Insert after this child block id of the destination."),
    start: bool = typer.Option(False, help="Insert as the first children of the destination."),
) -> None:
    """Write. Copy a block (or a page's content) with all nested children; Notion-hosted files are uploaded anew.

    The API cannot move a block: copy it, read the copy back, then delete the original (destructive)."""
    sid = nid(src)
    src_block = ntn("api", f"v1/blocks/{sid}")
    blocks = list_children(sid) if (children_only or src_block["type"] == "child_page") else [src_block]
    skipped: list[str] = []
    count = copy_tree(blocks, nid(to), position(after, start), skipped)
    emit({"copied": count, "skipped": skipped})


if __name__ == "__main__":
    app()
