"""Code accordions + Cursor links for walkthrough.html.

Copy to <lab>/tools/code_links.py, fill SNIPPETS, and re-run after ANY source edit
so line numbers never drift:

    python3 tools/code_links.py

1. Rebuilds every <!-- code:labN --><!-- /code:labN --> block from SNIPPETS.
2. Sets href on every <a data-code="path::text"> to the first line of path containing text
   (API explorer handler links, links in prose).
"""

import html
import re
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parent.parent
WALK = ROOT / "walkthrough.html"
COMMENT = {".py": "#", ".conf": "#", ".sh": "#", ".yml": "#", ".js": "//", ".jsx": "//", ".sql": "--"}

# One dict per accordion. start and notes are TEXT anchors, not line numbers.
#   lab    which <!-- code:labN --> block      file   path from the lab root
#   start  text on the first line shown         lines  how many lines to show
#   title  symbol in the summary                gist   one line in the summary
#   lead   one sentence above the code (HTML)
#   notes  [(text on a line to highlight, note HTML), ...]  -> numbered markers
SNIPPETS = [
    dict(lab=1, file="services/api/main.py", start="def create_short_url", lines=20,
         title="create_short_url", gist="validate, mint a code, insert",
         lead="The whole write path in one function.",
         notes=[("INSERT INTO", "One row per short code. The unique index is the collision check.")]),
]


def source(file: str) -> list[str]:
    return (ROOT / file).read_text().splitlines()


def find(lines: list[str], text: str, file: str, begin: int = 1, end: int | None = None) -> int:
    for n in range(begin, (end or len(lines)) + 1):
        if text in lines[n - 1]:
            return n
    raise SystemExit(f"{file}: no line {begin}-{end or len(lines)} contains {text!r}")


def cursor(file: str, line: int) -> str:
    return f"cursor://file{quote(str(ROOT / file))}:{line}"


def render_line(text: str, marker: str) -> str:
    """Escape one line; dim a full-line or trailing (2+ spaces) comment."""
    m = re.match(rf"^(\s*)({re.escape(marker)}.*)$", text) or re.match(rf"^(.*?\S)(\s{{2,}}{re.escape(marker)} .*)$", text)
    if m:
        return html.escape(m.group(1)) + f'<span class="c">{html.escape(m.group(2))}</span>'
    return html.escape(text)


def render(s: dict) -> str:
    src = source(s["file"])
    start = find(src, s["start"], s["file"])
    end = min(start + s["lines"] - 1, len(src))
    marks = {}
    for i, (text, note) in enumerate(s["notes"]):
        n = find(src, text, s["file"], start, end)
        if n in marks:
            raise SystemExit(f"{s['file']}: two notes land on line {n}; make {text!r} more specific")
        marks[n] = (i + 1, note)
    comment = COMMENT.get(Path(s["file"]).suffix, "#")

    rows = "".join(
        f'<span class="ln{" hl" if n in marks else ""}"><span class="no">{n}</span>'
        f'<span class="mk">{marks[n][0] if n in marks else ""}</span>{render_line(src[n - 1], comment)}\n</span>'
        for n in range(start, end + 1)
    )
    notes = "\n".join(
        f'            <li><span class="mk">{k}</span><a class="at" title="Open in Cursor" href="{cursor(s["file"], n)}">L{n}</a><span>{note}</span></li>'
        for n, (k, note) in sorted(marks.items(), key=lambda kv: kv[1][0])
    )
    return f"""          <details class="code">
            <summary><span class="sym"><code>{html.escape(s["title"])}</code></span><span class="where">{s["file"]}:{start}–{end}</span><span class="gist">{s["gist"]}</span></summary>
            <div class="code-body">
              <p class="lead">{s["lead"]} <a class="file" title="Open in Cursor" href="{cursor(s["file"], start)}">Open in Cursor ↗</a></p>
              <pre class="src"><span class="lines">{rows}</span></pre>
              <ol class="notes">
{notes}
              </ol>
            </div>
          </details>"""


def block(lab: int) -> str:
    items = "\n".join(render(s) for s in SNIPPETS if s["lab"] == lab)
    return (
        f"<!-- code:lab{lab} -->\n"
        f'        <div class="code-list">\n'
        f'          <p class="code-title"><strong>Code</strong> <span class="muted">· click to expand · numbers match the highlighted lines · <code>L…</code> opens Cursor there</span></p>\n'
        f"{items}\n        </div>\n        <!-- /code:lab{lab} -->"
    )


def link(m: re.Match) -> str:
    file, _, text = html.unescape(m.group(1)).partition("::")
    line = find(source(file), text, file) if text else 1
    tag = re.sub(r'\shref="[^"]*"', "", m.group(0))
    return tag.replace("<a ", f'<a href="{cursor(file, line)}" ', 1)


page = WALK.read_text()
for lab in sorted({s["lab"] for s in SNIPPETS}):
    pattern = re.compile(rf"<!-- code:lab{lab} -->.*?<!-- /code:lab{lab} -->", re.S)
    if not pattern.search(page):
        raise SystemExit(f"walkthrough.html has no <!-- code:lab{lab} --><!-- /code:lab{lab} --> markers")
    page = pattern.sub(lambda _: block(lab), page, count=1)
page, links = re.subn(r'<a [^>]*data-code="([^"]+)"[^>]*>', link, page)
WALK.write_text(page)
print(f"{len(SNIPPETS)} accordions, {links} data-code links")
