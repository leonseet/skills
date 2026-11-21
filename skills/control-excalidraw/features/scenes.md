# Scenes

A scene is one drawing: metadata (name, collection, pinned, sharing) plus its canvas content. This file covers the metadata; the canvas is in [scene-content](./scene-content.md). Every scene sits in exactly one collection, and scenes in `private` are visible only to their owner.

Commands: `excalidraw scenes list|get|create|update|delete|share|share-slides`.

## Operations

- `list` (read): scenes in the workspace or one collection.
- `find by name` (read): scenes whose name contains a text.
- `show` (read): one scene's metadata and sharing state.
- `create` (write): a new scene, empty or from a file.
- `rename, move, pin` (write): change name, collection or pinned.
- `share` (write): turn the public link on (view or edit) or off.
- `share slides` (write): turn the public presentation link on or off.
- `trash` (destructive): move a scene to trash.

## Finding things

- `N`, the scene id: from `find by name` or `list`. From a share URL `https://link.excalidraw.com/l/<workspace>/<scene>` it is the last path segment.
- `C`, the collection id: the literal `private`, or from [collections](./collections.md) `list` by name.
- `Q` search text, `NAME` the scene name, `FILE` a local `.excalidraw` file (see [files](./files.md)).

## Recipes with excalidraw

### list

```bash
excalidraw scenes list --limit 50 \
  | jq '{hasNextPage, scenes: [.data[].metadata | {id, name, collection, updated, elements: .totalElements}]}'
```

Returns `{hasNextPage, scenes: [{id, name, collection, updated, elements}]}`. One collection only: add `--collection-id "$C"`. Past 100 scenes, add `--all`; the envelope becomes `{count, data}`, so drop `hasNextPage` from the projection.

### find by name

```bash
excalidraw scenes list --all --limit 100 \
  | jq --arg q "$Q" '[.data[].metadata | select(.name | ascii_downcase | contains($q | ascii_downcase)) | {id, name, collection, updated}]'
```

Returns `[{id, name, collection, updated}]`; `[]` means no match. The API has no search, so this lists everything and filters locally.

### show

```bash
excalidraw scenes get "$N" \
  | jq '.metadata | {id, name, collection, pinned, isPrivate, linkSharing, slides: .isSlidesSharingEnabled, frames: .hasNonDeletedFrames, elements: .totalElements, updated}'
```

Returns one object. `linkSharing` is `0` off, `1` view, `3` edit.

### create

```bash
excalidraw scenes create --name "$NAME" --collection-id "$C" --file "$FILE" \
  | jq '.metadata | {id, name, collection}'
```

Returns `{id, name, collection}`. Drop `--file` for an empty scene. Read-back: `show` on the returned id; `name` and `collection` match and `elements` equals the file's element count.

### rename, move, pin

```bash
excalidraw scenes update "$N" --name "$NAME" \
  | jq '.metadata | {id, name, collection, pinned}'
```

Returns the changed scene. Move with `--collection-id "$C"`, pin with `--pinned`, unpin with `--no-pinned`; the flags combine. Read-back: `show`.

### share

```bash
excalidraw scenes share "$N" --access view
```

Returns `{"access":"view","url":"https://link.excalidraw.com/l/<workspace>/<scene>"}`. `--access edit` lets link holders edit; `--access none` turns the link off and returns `"url": null`. Read-back: `show`; `linkSharing` is `1` for view, `3` for edit, `0` for none.

### share slides

```bash
excalidraw scenes share-slides "$N"
```

Returns `{"enabled":true,"url":"https://link.excalidraw.com/p/readonly/<token>"}`; each frame is one slide. `--off` turns it off and returns `{"enabled":false,"url":null}`. Read-back: `show`; `slides` is `true` or `false`.

### trash

Destructive. Preview first and show it to the user: `show` on the scene. Only after their explicit yes:

```bash
excalidraw scenes delete "$N"
```

Prints `{}`. Read-back: `excalidraw scenes get "$N"` exits 1 with `HTTP 404: Scene not found`, and `list` no longer shows the scene. The CLI cannot restore from trash; the user restores in the web app.

## Gotchas

- `create --file` returns the metadata from before the content is written: `totalElements` reads `0` in its output. Trust `show` afterwards.
- `share-slides` on a scene without frames fails with `HTTP 400: The scene has no frames to share as slides`. Check `frames` in `show` first.
- A share link with view or edit access also lets link holders read and write comments.
- `scenes update` with no field flag fails; omitted fields stay unchanged.
