# /// script
# requires-python = ">=3.11"
# dependencies = ["typer>=0.12"]
# ///
"""Doctor and chains for the control-excalidraw skill. The `excalidraw` CLI stays the main interface.

Run as: uv run ~/.agents/skills/control-excalidraw/scripts/excalidraw.py <command>
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Optional

import typer

SERVICE = "excalidraw"
CLI = "excalidraw"
# Versions the last proof ran against. The API carries no version number beyond its path.
PROVEN = {"cli": "0.3.0", "service": "api/v1 (public beta)"}
NODE_MIN = 22
API_KEY_VAR = "EXCALIDRAW_API_KEY"
BROWSERS = ["google-chrome", "google-chrome-stable", "chromium", "chromium-browser", "microsoft-edge", "firefox"]
MAC_BROWSERS = [
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
    "/Applications/Firefox.app/Contents/MacOS/firefox",
]
JQ_FIX = "`brew install jq` (macOS) or `sudo apt install -y jq` (Debian/Ubuntu; other Linux: your package manager)"

app = typer.Typer(no_args_is_help=True, add_completion=False)


@app.callback()
def main() -> None:
    """Doctor and chains over the excalidraw CLI."""


# --- helpers --------------------------------------------------------------


def api_origin() -> str:
    return os.environ.get("EXCALIDRAW_API_URL", "https://api.excalidraw.com").rstrip("/")


def credentials_file() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / "excalidraw-cli" / "credentials.json"


def emit(data: Any) -> None:
    typer.echo(json.dumps(data, separators=(",", ":"), default=str))


def run(*argv: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(argv, capture_output=True, text=True)


def run_json(*argv: str) -> Any:
    """Run the excalidraw CLI (JSON on stdout) and parse its output; exit with its error otherwise."""
    proc = run(*argv)
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

    # 1. Node runtime.
    node = shutil.which("node")
    node_ok = False
    if not node:
        ok &= line("FAIL", "node", "not on PATH")
        fix(f"install Node {NODE_MIN}+: `fnm install {NODE_MIN} && fnm default {NODE_MIN}` (or nvm / your package manager)")
    else:
        version = run("node", "--version").stdout.strip()
        major = int(version.lstrip("v").split(".")[0] or 0)
        node_ok = major >= NODE_MIN
        ok &= line("ok" if node_ok else "FAIL", "node", f"{version} (needs >= {NODE_MIN})")
        if not node_ok:
            fix(f"`fnm install {NODE_MIN} && fnm use {NODE_MIN}`, then reinstall the CLI under it")

    # 2. The CLI and its version.
    cli = shutil.which(CLI)
    if not cli:
        ok &= line("FAIL", "cli", f"{CLI} not on PATH")
        fix(f"npm install -g @excalidraw/cli@{PROVEN['cli']}  (global installs are per Node version under fnm/nvm)")
    elif node_ok:
        cli_version = run(CLI, "--version").stdout.strip()
        line("ok", "cli", cli)
        line(
            "ok" if cli_version == PROVEN["cli"] else "WARN",
            "cli version",
            f"{cli_version} (proven {PROVEN['cli']})" + ("" if cli_version == PROVEN["cli"] else "; recipes may have drifted"),
        )

    # 3. jq, used by every recipe's projection.
    jq = shutil.which("jq")
    ok &= line("ok" if jq else "FAIL", "jq", jq or "not on PATH")
    if not jq:
        fix(JQ_FIX)

    # 4. A browser, for render and mermaid.
    browser = (
        os.environ.get("EXCALIDRAW_BROWSER_PATH")
        or next((p for b in BROWSERS if (p := shutil.which(b))), None)
        or next((p for p in MAC_BROWSERS if Path(p).exists()), None)
    )
    ok &= line("ok" if browser else "FAIL", "browser", browser or "no Chrome, Chromium, Edge or Firefox found")
    if not browser:
        fix("install Chrome or Firefox, or set EXCALIDRAW_BROWSER_PATH to an existing browser binary")

    # 5. API key: the CLI takes EXCALIDRAW_API_KEY first, then the key `excalidraw login` saved.
    saved = credentials_file()
    if os.environ.get(API_KEY_VAR):
        line("ok", "api key", f"from env {API_KEY_VAR}" + (f" (overrides the saved key in {saved})" if saved.exists() else ""))
        have_key = True
    elif saved.exists():
        line("ok", "api key", f"saved by login in {saved}")
        have_key = True
    else:
        have_key = False
        ok &= line("FAIL", "api key", f"{API_KEY_VAR} unset and no {saved}")
        fix(
            "the user creates a key at app.excalidraw.com (Account settings -> MCP/API key) and runs `excalidraw login` "
            f"in their own terminal, or exports {API_KEY_VAR} in their shell's startup file (~/.bashrc, ~/.zshrc); never pasted into the chat. "
            "Local `render` and `mermaid` work without a key."
        )

    if not (cli and node_ok):
        typer.echo("skip host, auth and API checks until the FAILs above are fixed; then rerun doctor")
        sys.exit(1)

    # 6. Host reachable and trusted. Without a key the API answers 401, which still proves reachability.
    url = f"{api_origin()}/api/v1/workspaces"
    reachable = True
    try:
        urllib.request.urlopen(urllib.request.Request(url, method="GET"), timeout=15)
        line("ok", "host", api_origin())
    except urllib.error.HTTPError as exc:
        line("ok", "host", f"{api_origin()} (HTTP {exc.code} without a key, as expected)")
    except Exception as exc:  # DNS, proxy, TLS
        reachable = False
        ok &= line("FAIL", "host", f"{api_origin()}: {exc}")
        fix("check the network connection and HTTPS_PROXY; for a TLS error behind an intercepting proxy set NODE_EXTRA_CA_CERTS to the CA bundle")

    # 7. Auth valid: whoami fetches the key's workspace.
    if not have_key or not reachable:
        typer.echo("skip auth check until the FAILs above are fixed; then rerun doctor")
        sys.exit(1)
    proc = run(CLI, "whoami")
    if proc.returncode != 0:
        ok &= line("FAIL", "auth", proc.stderr.strip().splitlines()[-1][:200] if proc.stderr.strip() else "whoami failed")
        fix(
            "the key is rejected, expired or lacks read access to the workspace: the user creates a new key in Excalidraw+ "
            "and runs `excalidraw login` again (or updates the export)"
        )
    else:
        who = json.loads(proc.stdout)
        line("ok", "auth", json.dumps(who, separators=(",", ":"))[:300])
    line("ok", "service version", PROVEN["service"])
    sys.exit(0 if ok else 1)


# --- chains ---------------------------------------------------------------


@app.command("edit-element")
def edit_element(
    scene: str = typer.Argument(..., help="Scene ID."),
    element: str = typer.Argument(..., help="Element ID inside the scene."),
    set_: str = typer.Option(..., "--set", help='JSON object of fields to change, e.g. \'{"text":"New label"}\'.'),
) -> None:
    """Write. Change fields of one element: read it, merge --set, raise its version, patch, read back.

    A patch only wins with a higher `version`; this command does the bump. Setting `text` also sets
    `originalText` unless --set gives one. `{"isDeleted": true}` removes the element (destructive).
    """
    try:
        changes = json.loads(set_)
        assert isinstance(changes, dict) and changes
    except (ValueError, AssertionError):
        typer.echo("--set must be a non-empty JSON object", err=True)
        raise typer.Exit(2)
    content = run_json(CLI, "scenes", "content", "get", scene)
    current = next((e for e in content["elements"] if e["id"] == element), None)
    if current is None:
        typer.echo(f"element {element} not in scene {scene}", err=True)
        raise typer.Exit(1)
    if "text" in changes and "originalText" not in changes:
        changes["originalText"] = changes["text"]
    patched = {**current, **changes, "version": current["version"] + 1}
    proc = subprocess.run(
        [CLI, "scenes", "content", "patch", scene, "--file", "-"],
        input=json.dumps({"elements": [patched]}),
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        typer.echo(f"patch failed ({proc.returncode}): {proc.stderr.strip()[-500:]}", err=True)
        raise typer.Exit(proc.returncode)
    # A deleted element stays in the content as a tombstone, so it is always found here.
    after = next(e for e in json.loads(proc.stdout)["elements"] if e["id"] == element)
    emit({"id": element, "type": after["type"], "version": after["version"], **{k: after.get(k) for k in changes}})


# --- draw -----------------------------------------------------------------

_ID_ALPHABET = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz_-"
_INDEX_DIGITS = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
_HUE_180 = [[-0.574, 1.430, 0.144], [0.426, 0.430, 0.144], [0.426, 1.430, -0.856]]  # hue-rotate(180deg), its own inverse
# Excalifont advance widths per font pixel, read from the font file the CLI ships (dist/fonts, hmtx / unitsPerEm).
_ADVANCE = {
    " ": 0.4, "!": 0.314, '"': 0.371, "#": 0.783, "$": 0.721, "%": 0.928, "&": 0.718, "'": 0.218, "(": 0.441,
    ")": 0.402, "*": 0.525, "+": 0.55, ",": 0.257, "-": 0.411, ".": 0.274, "/": 0.561, "0": 0.664, "1": 0.427,
    "2": 0.7, "3": 0.608, "4": 0.585, "5": 0.618, "6": 0.64, "7": 0.558, "8": 0.636, "9": 0.629, ":": 0.264,
    ";": 0.298, "<": 0.55, "=": 0.55, ">": 0.55, "?": 0.466, "@": 0.829, "A": 0.676, "B": 0.761, "C": 0.629,
    "D": 0.78, "E": 0.707, "F": 0.661, "G": 0.78, "H": 0.573, "I": 0.545, "J": 0.569, "K": 0.613, "L": 0.543,
    "M": 0.766, "N": 0.632, "O": 0.767, "P": 0.698, "Q": 0.768, "R": 0.736, "S": 0.622, "T": 0.857, "U": 0.73,
    "V": 0.592, "W": 0.786, "X": 0.628, "Y": 0.564, "Z": 0.832, "[": 0.472, "\\": 0.589, "]": 0.497, "^": 0.51,
    "_": 0.67, "`": 0.6, "a": 0.576, "b": 0.555, "c": 0.504, "d": 0.605, "e": 0.537, "f": 0.497, "g": 0.555,
    "h": 0.567, "i": 0.244, "j": 0.328, "k": 0.533, "l": 0.225, "m": 0.663, "n": 0.526, "o": 0.6, "p": 0.537,
    "q": 0.539, "r": 0.412, "s": 0.543, "t": 0.553, "u": 0.548, "v": 0.525, "w": 0.693, "x": 0.591, "y": 0.53,
    "z": 0.572, "{": 0.504, "|": 0.299, "}": 0.544, "~": 0.669, "•": 0.522, "·": 0.2, "—": 0.935, "–": 0.702,
    "’": 0.304, "“": 0.412, "”": 0.428, "…": 0.709,
}  # fmt: skip
_ADVANCE_OTHER = 0.6  # a character outside the table
_LABEL_PADDING = 5  # the editor keeps a bound label this far inside its container
_LINE_HEIGHT = 1.25


def light_of(dark_hex: str) -> str:
    """The light-theme colour that Excalidraw's dark mode, invert(93%) hue-rotate(180deg), displays as `dark_hex`."""
    if not (dark_hex.startswith("#") and len(dark_hex) == 7):
        return dark_hex
    seen = [int(dark_hex[i : i + 2], 16) / 255 for i in (1, 3, 5)]
    rotated = [sum(_HUE_180[i][j] * seen[j] for j in range(3)) for i in range(3)]
    stored = [min(1.0, max(0.0, (0.93 - v) / 0.86)) for v in rotated]
    return "#" + "".join(f"{round(v * 255):02x}" for v in stored)


class Drawing:
    """Builds complete Excalidraw elements from a small spec: every base field, ordered indices, bound labels."""

    def __init__(self, spec: dict, from_dark: bool) -> None:
        import random
        import time

        self.rng = random.Random()
        self.now = int(time.time() * 1000)
        self.spec = spec
        self.from_dark = from_dark
        self.elements: list[dict] = []
        self.groups: dict[str, str] = {}
        self.group: list[str] = []  # groupIds of the item being built

    def new_id(self) -> str:
        return "".join(self.rng.choice(_ID_ALPHABET) for _ in range(21))

    def colour(self, item: dict, key: str, default: str) -> str:
        value = item.get(key, self.spec.get(key))
        if value is None:
            return default
        return light_of(value) if self.from_dark else value

    def base(self, kind: str, x: float, y: float, w: float, h: float, **fields: Any) -> dict:
        n = len(self.elements)
        index = "a" + _INDEX_DIGITS[n] if n < 62 else "b" + _INDEX_DIGITS[(n - 62) // 62] + _INDEX_DIGITS[(n - 62) % 62]
        element = {
            "id": self.new_id(),
            "type": kind, "x": x, "y": y, "width": w, "height": h, "angle": 0,
            "strokeColor": "#1e1e1e", "backgroundColor": "transparent", "fillStyle": "solid", "strokeWidth": 2,
            "strokeStyle": "solid", "roughness": 1, "opacity": 100, "groupIds": list(self.group), "frameId": None, "index": index,
            "roundness": None, "seed": self.rng.randint(1, 2**31), "version": 1,
            "versionNonce": self.rng.randint(1, 2**31), "isDeleted": False, "boundElements": [],
            "updated": self.now, "link": None, "locked": False,
        }  # fmt: skip
        element.update(fields)
        self.elements.append(element)
        return element

    @staticmethod
    def measure(text: str, size: float) -> tuple[float, float]:
        lines = text.split("\n")
        widest = max(sum(_ADVANCE.get(ch, _ADVANCE_OTHER) for ch in line) for line in lines)
        return widest * size, len(lines) * size * _LINE_HEIGHT

    def text(self, item: dict, text: str, x: float, y: float, container: Optional[dict] = None, centre: bool = False) -> dict:
        size = item.get("size", self.spec.get("size", 24))
        w, h = self.measure(text, size)
        if centre:  # x, y name the centre point
            x, y = x - w / 2, y - h / 2
        element = self.base(
            "text", x, y, w, h, strokeColor=self.colour(item, "color", "#1e1e1e"), text=text, originalText=text,
            fontSize=size, fontFamily=5, textAlign="center" if centre else item.get("align", "left"),
            verticalAlign="middle" if centre else "top", containerId=container["id"] if container else None,
            lineHeight=_LINE_HEIGHT, autoResize=True,
        )  # fmt: skip
        if container:
            container["boundElements"] = [{"type": "text", "id": element["id"]}]
        return element

    def box(self, item: dict, x: float, y: float, w: float, h: float, label: Optional[str]) -> None:
        rect = self.base(
            "rectangle", x, y, w, h, strokeColor=self.colour(item, "stroke", "#1e1e1e"),
            backgroundColor=self.colour(item, "fill", "transparent"), strokeWidth=item.get("strokeWidth", 2),
            strokeStyle=item.get("strokeStyle", "solid"), roundness={"type": 3} if item.get("rounded", True) else None,
        )  # fmt: skip
        if label:
            self.text(item, label, x + w / 2, y + h / 2, container=rect, centre=True)

    def build(self) -> list[dict]:
        frames = []
        for n, item in enumerate(self.spec.get("items", [])):
            name = item.get("group")
            self.group = [self.groups.setdefault(name, self.new_id())] if name else []
            if "frame" in item:
                frames.append(item)
            elif "box" in item:
                self.box(item, *item["box"], item.get("label"))
            elif "grid" in item:
                x, y, w, h = item["grid"]
                labels, gap = item["labels"], item.get("gap", 14)
                down = item.get("direction", "row") == "column"
                cell = ((h if down else w) - gap * (len(labels) - 1)) / len(labels)
                for i, label in enumerate(labels):
                    offset = i * (cell + gap)
                    self.box(item, x, y + offset, w, cell, label) if down else self.box(item, x + offset, y, cell, h, label)
            elif "text" in item:
                self.text(item, item["text"], item["x"], item["y"])
            elif "arrow" in item:
                x1, y1, x2, y2 = item["arrow"]
                via = item.get("via", [])  # corner points make a sharp polyline
                points = [[px - x1, py - y1] for px, py in [[x1, y1], *via, [x2, y2]]]
                xs, ys = [p[0] for p in points], [p[1] for p in points]
                arrow = self.base(
                    "arrow", x1, y1, max(xs) - min(xs), max(ys) - min(ys), strokeColor=self.colour(item, "stroke", "#1e1e1e"),
                    strokeWidth=item.get("strokeWidth", 2), points=points, lastCommittedPoint=None,
                    startBinding=None, endBinding=None, startArrowhead=item.get("startArrowhead"),
                    endArrowhead=item.get("endArrowhead", "arrow"), elbowed=False, roundness=None if via else {"type": 2},
                )  # fmt: skip
                if item.get("label"):
                    label_item = {"size": 20, **item}
                    self.text(label_item, item["label"], (x1 + x2) / 2, (y1 + y2) / 2, container=arrow, centre=True)
            else:
                typer.echo(f"items[{n}] needs one of: box, grid, text, arrow, frame", err=True)
                raise typer.Exit(2)
        self.group = []
        for item in frames:  # last, so a frame sits above its children in the element order, as the editor keeps it
            fx, fy, fw, fh = item["frame"]
            frame = self.base("frame", fx, fy, fw, fh, strokeColor="#bbb", name=item.get("name"))
            for element in self.elements:
                x1, y1, x2, y2 = bbox(element)
                if element["type"] != "frame" and fx <= x1 and fy <= y1 and x2 <= fx + fw and y2 <= fy + fh:
                    element["frameId"] = frame["id"]
        return self.elements


# --- geometry, shared by draw and lint --------------------------------------


def bbox(element: dict) -> tuple[float, float, float, float]:
    """x1, y1, x2, y2. An arrow's x, y is its first point, and its other points may lie on either side of it."""
    x, y = element["x"], element["y"]
    if element.get("points"):
        xs, ys = [x + p[0] for p in element["points"]], [y + p[1] for p in element["points"]]
        return min(xs), min(ys), max(xs), max(ys)
    return x, y, x + element["width"], y + element["height"]


def text_box(element: dict, by_id: dict[str, dict]) -> tuple[float, float, float, float]:
    """A text's box from the font table: the stored width is an estimate until the editor re-measures it."""
    w, h = Drawing.measure(element["text"], element["fontSize"])
    container = by_id.get(element.get("containerId") or "")
    if container:
        x1, y1, x2, y2 = bbox(container)
        cx, cy = (x1 + x2) / 2, (y1 + y2) / 2
        return cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2
    x = element["x"] + {"center": (element["width"] - w) / 2, "right": element["width"] - w}.get(element.get("textAlign"), 0)
    return x, element["y"], x + w, element["y"] + h


def inside(inner: tuple, outer: tuple, slack: float = 0) -> bool:
    return outer[0] - slack <= inner[0] and outer[1] - slack <= inner[1] and inner[2] <= outer[2] + slack and inner[3] <= outer[3] + slack


def overlap(a: tuple, b: tuple) -> bool:
    return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]


def segment_hits(p: tuple, q: tuple, box: tuple) -> bool:
    """Whether the segment p-q passes through the box (Liang-Barsky clip)."""
    t0, t1 = 0.0, 1.0
    dx, dy = q[0] - p[0], q[1] - p[1]
    for d, lo, hi, start in ((dx, box[0], box[2], p[0]), (dy, box[1], box[3], p[1])):
        if d == 0:
            if not lo < start < hi:
                return False
            continue
        a, b = sorted(((lo - start) / d, (hi - start) / d))
        t0, t1 = max(t0, a), min(t1, b)
        if t0 >= t1:
            return False
    return True


def label_of(element: dict, by_id: dict[str, dict]) -> str:
    text = element.get("text")
    if text is None:
        bound = next((by_id[b["id"]] for b in element.get("boundElements") or [] if b["type"] == "text" and b["id"] in by_id), None)
        text = bound["text"] if bound else ""
    first = text.split("\n")[0][:40]
    return f'{element["type"]} "{first}"' if first else f'{element["type"]} at {round(element["x"])},{round(element["y"])}'


# --- lint -------------------------------------------------------------------


@app.command()
def lint(file: Path = typer.Argument(..., help="A .excalidraw file, or a scene's content saved with `scenes content get --out`.")) -> None:
    """Read (local file). Report layout faults: text wider than its box, boxes that half-overlap, arrows through a box or text.

    Prints {elements, findings} and exits 1 when there are findings.
    """
    elements = [e for e in json.loads(file.read_text())["elements"] if not e.get("isDeleted")]
    by_id = {e["id"]: e for e in elements}
    boxes = [e for e in elements if e["type"] in ("rectangle", "diamond", "ellipse")]
    texts = [e for e in elements if e["type"] == "text"]
    findings: list[dict] = []

    def add(kind: str, element: dict, other: Optional[dict], detail: str) -> None:
        finding = {"kind": kind, "id": element["id"], "what": label_of(element, by_id), "detail": detail}
        if other:
            finding["other"] = label_of(other, by_id)
        findings.append(finding)

    for text in texts:
        tb = text_box(text, by_id)
        container = by_id.get(text.get("containerId") or "")
        if container and container["type"] != "arrow":
            cb = bbox(container)
            over_w = (tb[2] - tb[0]) - (cb[2] - cb[0] - 2 * _LABEL_PADDING)
            over_h = (tb[3] - tb[1]) - (cb[3] - cb[1] - 2 * _LABEL_PADDING)
            if over_w > 0 or over_h > 0:
                add("label-overflows", text, container, f"needs {max(0, round(over_w))} px more width, {max(0, round(over_h))} px more height")
        if container:
            continue
        for box in boxes:  # free text must sit wholly inside or wholly outside every box
            bb = bbox(box)
            if overlap(tb, bb) and not inside(tb, bb) and not inside(bb, tb):
                add("text-crosses-edge", text, box, f"text spans x {round(tb[0])}..{round(tb[2])}, box x {round(bb[0])}..{round(bb[2])}")
        for other in texts:
            if other["id"] > text["id"] and not other.get("containerId") and overlap(tb, text_box(other, by_id)):
                add("texts-overlap", text, other, "two free texts share space")
    for i, a in enumerate(boxes):
        for b in boxes[i + 1 :]:
            ab, bb = bbox(a), bbox(b)
            if overlap(ab, bb) and not inside(ab, bb, 1) and not inside(bb, ab, 1):
                add("boxes-overlap", a, b, "neither box contains the other")
    for arrow in (e for e in elements if e["type"] in ("arrow", "line")):
        pts = [(arrow["x"] + p[0], arrow["y"] + p[1]) for p in arrow["points"]]
        for target in [*boxes, *(t for t in texts if not t.get("containerId"))]:  # a bound label is covered by its box
            tb = text_box(target, by_id) if target["type"] == "text" else bbox(target)
            core = (tb[0] + 3, tb[1] + 3, tb[2] - 3, tb[3] - 3)
            if core[0] >= core[2] or core[1] >= core[3]:
                continue
            # A segment that starts or ends inside is an arrow leaving or entering the box, which is fine.
            through = any(
                segment_hits(p, q, core) and not any(core[0] < e[0] < core[2] and core[1] < e[1] < core[3] for e in (p, q))
                for p, q in zip(pts, pts[1:])
            )
            if through:
                add("arrow-crosses", arrow, target, f"arrow from {round(pts[0][0])},{round(pts[0][1])} to {round(pts[-1][0])},{round(pts[-1][1])}")
    emit({"elements": len(elements), "findings": findings})
    if findings:
        raise typer.Exit(1)


# --- draw command -----------------------------------------------------------


def fingerprint(elements: list[dict]) -> dict[str, dict]:
    return {e["id"]: {"version": e["version"], "type": e["type"], "text": e.get("text")} for e in elements if not e.get("isDeleted")}


def edits_since(pushed: dict[str, dict], live: dict[str, dict]) -> list[dict]:
    """What changed in the scene since the last push: elements someone edited, added or removed in the editor."""
    changes = []
    for key in sorted(set(pushed) | set(live)):
        before, after = pushed.get(key), live.get(key)
        if before and after and before["version"] == after["version"]:
            continue
        change = "edited" if before and after else "added" if after else "removed"
        entry = {"change": change, "id": key, "type": (after or before)["type"]}
        if (before or {}).get("text") != (after or {}).get("text"):
            entry.update(was=(before or {}).get("text"), now=(after or {}).get("text"))
        changes.append(entry)
    return changes


@app.command()
def draw(
    spec: Path = typer.Argument(..., help="JSON spec file, or - for stdin. See features/files.md `draw from spec`."),
    out: Path = typer.Option(..., "--out", help="The .excalidraw file to write (overwrites)."),
    from_dark: bool = typer.Option(False, "--from-dark", help="The spec's colours were read off a dark-mode screenshot: store their light-theme equivalents."),
    scene: Optional[str] = typer.Option(None, "--scene", help="Destructive: also replace this scene's whole content with the drawing, after backing it up."),
    overwrite_edits: bool = typer.Option(False, "--overwrite-edits", help="With --scene: replace the scene even though it was edited since the last push."),
) -> None:
    """Write (local file); destructive with --scene. Turn a spec of boxes, grids, texts, arrows and frames into a .excalidraw file.

    With --scene the push is refused (exit 3) when the scene changed since this file was last pushed: the changes
    are printed, to be carried into the spec first. --overwrite-edits pushes anyway.
    """
    try:
        data = json.loads(sys.stdin.read() if str(spec) == "-" else spec.read_text())
        assert isinstance(data, dict) and isinstance(data.get("items"), list) and data["items"]
    except (OSError, ValueError, AssertionError) as exc:
        typer.echo(f"spec must be a JSON object with a non-empty `items` list: {exc}", err=True)
        raise typer.Exit(2)
    elements = Drawing(data, from_dark).build()
    document = {
        "type": "excalidraw", "version": 2, "source": "control-excalidraw", "elements": elements,
        "appState": {"viewBackgroundColor": data.get("background", "#ffffff"), "gridSize": None}, "files": {},
    }  # fmt: skip
    out.write_text(json.dumps(document, indent=1))
    result: dict[str, Any] = {"path": str(out.resolve()), "elements": len(elements)}
    if scene:
        backup = out.with_name(f"{out.stem}.backup-{scene}.json")
        pushed = out.with_name(f"{out.stem}.pushed-{scene}.json")
        run_json(CLI, "scenes", "content", "get", scene, "--out", str(backup))
        if pushed.exists() and not overwrite_edits:
            edits = edits_since(json.loads(pushed.read_text()), fingerprint(json.loads(backup.read_text())["elements"]))
            if edits:
                emit({**result, "scene": scene, "refused": "scene edited since the last push", "backup": str(backup.resolve()), "edits": edits})
                raise typer.Exit(3)
        after = run_json(CLI, "scenes", "content", "put", scene, "--file", str(out))
        pushed.write_text(json.dumps(fingerprint(after["elements"])))
        result.update(scene=scene, backup=str(backup.resolve()), sceneElements=len(after["elements"]))
    emit(result)


if __name__ == "__main__":
    app()
