# Scene content

A scene's content is its canvas: `elements` (rectangle, diamond, ellipse, arrow, line, text, frame, image, …), `files` (embedded images) and a small `appState`. It is the same JSON as a `.excalidraw` file. A label inside a shape is a separate `text` element whose `containerId` points at the shape.

Commands: `excalidraw scenes content get|patch|put`, `excalidraw scenes render`, `scripts/excalidraw.py edit-element`.

## Operations

- `get` (read): the whole content, into a file.
- `list elements` (read): a compact view of what is on the canvas.
- `find text` (read): text elements matching a string.
- `render` (read): the scene as a PNG or SVG file.
- `patch` (write): merge elements, files or background into the scene.
- `edit element` (write): change fields of one element.
- `list animations` (read): a slide's reveal steps.
- `animate` (write): set the step at which elements appear on a slide.
- `replace` (destructive): overwrite the whole content.
- `delete element` (destructive): remove one element.

## Finding things

- `N`, the scene id: [scenes](./scenes.md) `find by name`.
- `OUT`: where the file goes. Content: `OUT=$(mktemp).json`. Images: a `.png` or `.svg` path; the extension picks the format.
- `E`, an element id: `find text` for labels, `list elements` for shapes. A shape's label is the text element whose `container` is the shape's id.
- `FILE`: a local file holding `{"elements": [...]}` or a full `.excalidraw` export. Build one with [files](./files.md) `mermaid to scene file`.
- `STEPS`: a JSON object from element id to reveal step, `{"<id>": 1, "<id>": 2}`. Build it from `list elements`; every member of a group, and each arrow that belongs with it, gets the group's step.

## Recipes with excalidraw

### get

```bash
excalidraw scenes content get "$N" --out "$OUT" \
  && jq '.elements |= map(select(.isDeleted | not)) | {elements: (.elements | length), types: ([.elements[].type] | group_by(.) | map({(.[0]): length}) | add), files: (.files | length), background: .appState.viewBackgroundColor}' "$OUT"
```

Returns `{elements, types: {<type>: <count>}, files, background}`, counting live elements; the full JSON, deleted elements included, is in `$OUT`.

### list elements

```bash
excalidraw scenes content get "$N" \
  | jq -c '[.elements[] | select(.isDeleted | not)][:200][] | {id, type, x: (.x | round), y: (.y | round), w: (.width | round), h: (.height | round), text: (.text // null), container: (.containerId // null), frame: .frameId}'
```

One line per live element, first 200. Arrows carry `startBinding.elementId` and `endBinding.elementId`; add them to the projection to read the graph.

### find text

```bash
excalidraw scenes content get "$N" \
  | jq --arg q "$Q" '[.elements[] | select(.type == "text" and (.isDeleted | not) and (.text | ascii_downcase | contains($q | ascii_downcase))) | {id, text, version, container: .containerId}]'
```

Returns `[{id, text, version, container}]`; `[]` means no match.

### render

```bash
excalidraw scenes render "$N" --out "$OUT" | jq '{path, width, height}'
```

Returns `{path, width, height}`. Open the PNG to see the drawing. `--scale 2` sharpens small text, `--theme dark`, `--transparent`. One frame: `--frame-id "$E"`. Every frame as its own file: `--all-frames --out <directory>`.

### patch

```bash
jq '{elements, files}' "$FILE" \
  | excalidraw scenes content patch "$N" --file - | jq '{elements: (.elements | length), sceneVersion}'
```

Returns the new element count. The `jq` step keeps the two keys `patch` takes from a file: a full `.excalidraw` export also carries `type`, `version` and `source`, which `patch` rejects with `HTTP 400: Unrecognized keys`. Elements in the file are added, or merged by id when the id already exists; everything else in the scene stays. Read-back: `list elements` or `find text` shows the new elements. Background only:

```bash
echo '{"appState":{"viewBackgroundColor":"#f8f9fa"}}' \
  | excalidraw scenes content patch "$N" --file - | jq '.appState.viewBackgroundColor'
```

### edit element

```bash
uv run ~/.agents/skills/control-excalidraw/scripts/excalidraw.py edit-element "$N" "$E" --set '{"text":"New label"}'
```

Returns `{id, type, version, <changed fields>}`, read back from the scene after the patch. `--set` takes any element fields (`strokeColor`, `backgroundColor`, `x`, `y`, `width`, `locked`, …). Setting `text` also sets `originalText`.

### replace

Destructive: elements absent from the file are removed, and open editors are forced to reload. Back the scene up first with `get`, show the user its summary, and only after their explicit yes:

```bash
excalidraw scenes content put "$N" --file "$FILE" | jq '{elements: (.elements | length), sceneVersion}'
```

Read-back: `get`; the element count equals the file's. For a drawing made from a spec, [files](./files.md) `draw from spec` with `--scene` does the backup and the replace in one command.

### delete element

Destructive. Preview: `list elements` filtered to the id. Only after the user's explicit yes:

```bash
uv run ~/.agents/skills/control-excalidraw/scripts/excalidraw.py edit-element "$N" "$E" --set '{"isDeleted":true}'
```

Returns `{id, type, version, isDeleted: true}`. Read-back: `find text` or `list elements` no longer shows the id. Deleting a shape leaves its label: delete the bound text element too.

### list animations

```bash
excalidraw scenes content get "$N" \
  | jq -c '[.elements[] | select((.isDeleted | not) and .customData.presentationAnimation)] | group_by(.customData.presentationAnimation.step)[] | {step: .[0].customData.presentationAnimation.step, elements: length, texts: [.[] | .text // empty | split("\n")[0]]}'
```

Returns one `{step, elements, texts}` per reveal step, across every slide; prints nothing for a scene without animations.

### animate

Each frame is one slide of a presentation. An element with `customData.presentationAnimation` stays hidden until its `step` (1-based, per frame); elements sharing a step appear together, and elements without one are visible from the start.

```bash
excalidraw scenes content get "$N" \
  | jq --argjson steps "$STEPS" '{elements: [.elements[] | select((.isDeleted | not) and $steps[.id]) | .customData = ((.customData // {}) + {presentationAnimation: {type: "fade", duration: 500, frameId: .frameId, step: $steps[.id]}}) | .version += 1]}' \
  | excalidraw scenes content patch "$N" --file - | jq '{elements: (.elements | length), sceneVersion}'
```

Read-back: `list animations`. `type` is `fade`, or `fly` with `from` set to `left`, `right`, `top` or `bottom`; `withPrevious: true` plays a step on the same click as the one before. The elements must already be inside a frame. This is the same data the presentation editor's animation tool writes. Schema: <https://plus.excalidraw.com/docs/api/scene-content-schema>, "Presentation metadata".

## Gotchas

- A deleted element stays in the content as a tombstone with `isDeleted: true`, and `patch` output and `scenes show`'s `elements` count it. The read recipes here filter tombstones out; a hand-written `jq` over `.elements` must do the same. `replace` drops them.
- The service replaces element ids that are not in Excalidraw's own form of 21 characters from `A-Za-z0-9_-`: `el000` became `XSAx6TQGj0qi0fUjxDz3h` on upload. A later patch built from the local file's ids then adds a second copy of everything instead of updating. Files from `mermaid` and `draw` carry proper ids, which are kept. For any other file, read the ids back with `list elements` before patching, or redo the whole drawing with `replace`.
- Colours are stored as light-theme values and Excalidraw's dark mode inverts them on display. To match a dark-mode screenshot, store the light-theme colours and leave the canvas `#ffffff`; check with `render --theme dark`.
- A patched element only wins when its `version` is higher than the stored one. A patch with the same version exits 0 and changes nothing. `edit element` does the bump; a hand-built patch must add 1 itself.
- `patch` and `put` print the scene's entire content. Without the `jq` projection that is hundreds of kilobytes.
- A text edit keeps the old `width` and `height`: a much longer label overflows its box until someone opens the scene in the editor. Render to check, and widen the container with a second `edit element` when needed.
- From `appState`, only `viewBackgroundColor` and `lockedMultiSelections` are stored; zoom, scroll and the rest are dropped.
- `patch` validates every element in full: one missing base field (`strokeColor`, `seed`, `version`, `index`, `groupIds`, …) fails the whole patch with an `HTTP 400` listing each gap. Build new elements with `mermaid`, or copy an existing element of the scene and change its `id`, geometry and `type`, rather than writing one by hand.
- Rendering needs a local browser and takes a few seconds; `--timeout` (default 30000 ms) covers large scenes.
- A request to animate a diagram means reveal steps on one slide (`animate`), which is what the presentation editor's animation tool sets. One frame per step is a different thing, a deck of slides.
- `animate` is proven to store and read back; `fly` and `withPrevious` are taken from the schema page and unproven here.
