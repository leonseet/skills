# Excalidraw control map

Read this index, then use the matching feature file as the recipe book. Setup, doctor, safety and output shaping live in [`../SKILL.md`](../SKILL.md).

## Baseline

- `uv run ~/.agents/skills/control-excalidraw/scripts/excalidraw.py doctor` all `ok`.
- One workspace, the key's: `excalidraw whoami | jq '{workspace, keyType}'`. Collections: `private`, plus the ones [collections](./collections.md) `list` shows.
- Sandbox: a collection `control-sandbox`; [`../SKILL.md`](../SKILL.md) says how to find or make it.

## Common tasks

Chains across features. Each step names the recipe that does it.

- **Draw a diagram into the workspace**: write Mermaid to a file → [files](./files.md) `mermaid to scene file` → `render file` and look at the PNG → [scenes](./scenes.md) `create` with `--file` → its read-back.
- **Draw a layout or redraw a screenshot**: write a spec → [files](./files.md) `draw from spec` (`--from-dark` for a dark-mode screenshot) → `lint` until clean → `render file` and compare the PNG → [scenes](./scenes.md) `create` with `--file`.
- **Look at a scene**: [scenes](./scenes.md) `find by name` → [scene-content](./scene-content.md) `render`, then open the PNG.
- **Change a label in a scene**: [scenes](./scenes.md) `find by name` → [scene-content](./scene-content.md) `find text` → `edit element` → `render` to check the result.
- **Add shapes to a scene**: build the new elements as a local file ([files](./files.md) `mermaid to scene file` or `draw from spec`) → [scene-content](./scene-content.md) `patch` with that file. Patch keeps every element already in the scene.
- **Animate a diagram for presenting**: put it in one frame and give each block a group ([files](./files.md) `draw from spec`: `frame`, `group`) → [scene-content](./scene-content.md) `list elements` to build `STEPS` → `animate` → `list animations`.
- **Give someone a link**: [scenes](./scenes.md) `find by name` → `share` (only when the user asked for a public link).
- **Back up a scene before a risky edit**: [scene-content](./scene-content.md) `get` into a file. `replace` with that file restores it.

## Feature entry contract

Each feature file has an H1, one paragraph saying what the resource is in this workspace, and a `Commands:` line naming the CLI groups it covers, then exactly four H2s in this order:

1. `Operations`: one line each, tagged `read` / `write` / `destructive`.
2. `Finding things`: how to resolve the identifiers the recipes need.
3. `Recipes with excalidraw`: one H3 per operation: the command with its `jq` projection, the output shape, and for writes, the read-back.
4. `Gotchas`.

A feature is one resource area. An operation shared between areas has one owner and the others link to it. To find the recipes a CLI upgrade touches, grep the `Commands:` lines.

## Features

Treat a recipe that fails as possible drift: check `--help` for the installed version, fix the recipe, and re-prove it.

| File | Covers | Proven | CLI | Service | Unproven |
| --- | --- | --- | --- | --- | --- |
| [scenes](./scenes.md) | list, find by name, show, create, rename/move/pin, share, share slides, trash | 2026-11-21 | excalidraw 0.3.0 | api/v1 beta | none |
| [scene-content](./scene-content.md) | get, list elements, find text, render, list animations, animate, patch, edit element, replace | 2026-11-21 | excalidraw 0.3.0 | api/v1 beta | animate with `fly` or `withPrevious`; playback in the presenter |
| [collections](./collections.md) | list, show, scenes in, create, rename, trash | 2026-11-21 | excalidraw 0.3.0 | api/v1 beta | none |
| [files](./files.md) | mermaid to scene file, mermaid to image, draw from spec, lint, render file, render frames | 2026-11-21 | excalidraw 0.3.0 | api/v1 beta | none |
| [workspace](./workspace.md) | whoami, workspace, members, invites, audit logs | 2026-11-21 | excalidraw 0.3.0 | api/v1 beta | none (reads only; member and invite changes are not mapped) |
