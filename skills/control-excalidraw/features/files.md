# Local files

A `.excalidraw` file is a scene's content as JSON on disk. The CLI converts Mermaid into one and renders one to an image, all locally in a headless browser: no API key, nothing uploaded. To draw: for a flow, write Mermaid and convert it; for a layout (boxes in rows and columns, an architecture diagram, a redraw of a screenshot), write a spec and run `draw`. Run `lint`, look at the PNG, then push the file into the workspace with [scenes](./scenes.md) `create`.

Commands: `excalidraw mermaid`, `excalidraw render`, `scripts/excalidraw.py draw`, `scripts/excalidraw.py lint`.

## Operations

- `mermaid to scene file` (write, local file): Mermaid to an editable `.excalidraw` file.
- `mermaid to image` (write, local file): Mermaid straight to PNG or SVG.
- `draw from spec` (write, local file): boxes, grids of boxes, texts, arrows and frames at given coordinates to a `.excalidraw` file.
- `lint` (read, local file): layout faults in a `.excalidraw` file.
- `render file` (write, local file): a `.excalidraw` file to PNG or SVG.
- `render frames` (write, local files): each frame of a file as its own image.

## Finding things

- `FILE`: the input, a `.mmd` Mermaid file or a `.excalidraw` file. `-` reads stdin.
- `OUT`: the output path; it is overwritten. Its extension picks the format: `.excalidraw`, `.png` or `.svg`. For `render frames` it is a directory.
- `SPEC`: a JSON file in the format under `draw from spec`. `-` reads stdin.
- A frame's id, for `--frame-id`: `jq -c '.elements[] | select(.type == "frame") | {id, name}' "$FILE"`.

## Recipes with excalidraw

### mermaid to scene file

```bash
excalidraw mermaid "$FILE" --out "$OUT" | jq '{path, elements}'
```

Returns `{path, elements}` with `$OUT` ending `.excalidraw`. `--elbow` draws right-angled arrows, `--font-size <px>` sets the text size (default 20).

### mermaid to image

```bash
excalidraw mermaid "$FILE" --out "$OUT" --scale 2 | jq '{path, width, height}'
```

Returns `{path, width, height}` with `$OUT` ending `.png` or `.svg`.

### draw from spec

```bash
uv run ~/.agents/skills/control-excalidraw/scripts/excalidraw.py draw "$SPEC" --out "$OUT"
```

Returns `{path, elements}` with `$OUT` ending `.excalidraw`. Then `lint`, and `render file` to look at the PNG before uploading. The spec is one object: `items` drawn in order, later ones on top, coordinates in pixels with y downwards.

```json
{
  "color": "#1e1e1e",
  "items": [
    {"text": "Title", "x": 0, "y": 0, "size": 32},
    {"box": [0, 60, 600, 120], "stroke": "#1971c2", "fill": "#a5d8ff", "strokeWidth": 4},
    {"text": "Row\nlabel", "x": 16, "y": 90, "color": "#1971c2"},
    {"grid": [160, 80, 420, 80], "labels": ["A", "B", "C"], "gap": 14, "stroke": "#1971c2", "fill": "#ffffff"},
    {"arrow": [300, 190, 300, 280], "label": "feeds", "stroke": "#868e96"},
    {"box": [0, 290, 600, 80], "label": "Foundation", "rounded": false, "group": "base"},
    {"arrow": [600, 120, 600, 330], "via": [[660, 120], [660, 330]], "group": "base"},
    {"frame": [-40, -40, 740, 450], "name": "Slide 1"}
  ]
}
```

- `box`: `[x, y, width, height]`, with an optional centred `label`.
- `grid`: equal boxes filling `[x, y, width, height]`, one per entry of `labels`, side by side; `"direction": "column"` stacks them.
- `text`: free text with its top-left at `x`, `y`; `\n` breaks lines.
- `arrow`: `[x1, y1, x2, y2]`, head at the end, optional `label` on the line. `via` lists the corner points between start and end, in order, and makes the arrow a sharp polyline: use it for right-angled arrows and to route round a block.
- `frame`: `[x, y, width, height]` with a `name`. Every item lying wholly inside becomes its child. A frame is one slide of a presentation.
- `group` on any item: items sharing a name select and move as one in the editor. Give each block of a diagram its own group.
- Styling on any item: `stroke`, `fill`, `color` (text), `size` (font px, default 24), `strokeWidth` (default 2), `strokeStyle`, `rounded` (default true). `color` and `size` at the top level are the defaults. `background` at the top level sets the canvas; leave it out.

Redrawing a dark-mode screenshot: put the colours as they look in the screenshot and add `--from-dark`. The file then holds their light-theme equivalents, and `render file` with `--theme dark` shows the screenshot's colours.

To redo a drawing that is already a scene, add `--scene "$N"`. This is destructive (the scene's whole content is replaced): show the user [scene-content](./scene-content.md) `get` first and run it only after their explicit yes. It saves the old content beside `$OUT` as `<name>.backup-<scene>.json` and returns `{path, elements, scene, backup, sceneElements}`.

Each push also records the scene's state beside `$OUT` as `<name>.pushed-<scene>.json`. A later push is refused with exit 3 when the scene changed since: it returns `{refused, edits}`, each edit `{change, id, type, was, now}`. Those are the user's edits in the editor: carry them into the spec and push again. Keep `$OUT` at one path across pushes, since the record is found by its name. `--overwrite-edits` pushes regardless, only after the user's yes to losing the listed edits.

### lint

```bash
uv run ~/.agents/skills/control-excalidraw/scripts/excalidraw.py lint "$FILE" | jq -c '.findings[] | [.kind, .what, .other, .detail]'
```

Returns `{elements, findings}` and exits 1 with findings; a clean file prints nothing through this projection. Kinds: `label-overflows` (a label wider or taller than its box; `detail` gives the pixels to add), `text-crosses-edge` (free text half in, half out of a box), `texts-overlap`, `boxes-overlap` (two boxes that intersect, neither containing the other), `arrow-crosses` (an arrow passing through a box or text it does not start or end in). Fix the spec until it is clean, then render once. For a scene, lint the file from [scene-content](./scene-content.md) `get`.

### render file

```bash
excalidraw render "$FILE" --out "$OUT" | jq '{path, width, height}'
```

Returns `{path, width, height}`. `--scale 2` for sharper text, `--theme dark`, `--transparent`, `--padding <px>` (default 20), `--frame-id <id>` for one frame.

### render frames

```bash
excalidraw render "$FILE" --all-frames --out "$OUT"
```

Writes one image per frame into the directory `$OUT`, numbered in presentation order (`01-intro.png`).

## Gotchas

- Flowcharts, sequence, class, ER and state diagrams, Gantt charts, quadrant charts and timelines become editable shapes. Other Mermaid types, such as pie charts, become one embedded image.
- `draw` and `lint` measure text from a table of Excalifont character widths, exact for ASCII and `• · — – … ’ “ ”`. Other characters count as 0.6 of the font size, so CJK text or another font family is an estimate: render to check those.
- A deliberate overlap, such as an outline drawn across several blocks, is reported by `lint` like any other: read each finding rather than requiring zero.
- `--from-dark` cannot reach every colour: a saturated yellow such as `#fab005` has no light-theme equivalent and comes out amber. Dark mode shows nothing blacker than `#121212`.
- A Mermaid syntax error exits 1 and names the line to fix.
- With `--out -` stdout carries only the scene or image, without the JSON summary.
- PNGs are capped at 16384 px a side and `--scale` at 16; SVGs embed their fonts and have no size limit.
- CJK text downloads its fonts from a CDN on first use; offline, pass `--fonts-url none` or a local folder.
