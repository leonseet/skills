# Collections

A collection is a folder of scenes. The workspace has the built-in `private` collection (its id is the literal `private`; it cannot be renamed or trashed) and its shared collections, one of them the default. New collections are always shared with the whole workspace.

Commands: `excalidraw collections list|get|create|update|delete`, `excalidraw collections scenes list`.

## Operations

- `list` (read): every collection.
- `show` (read): one collection.
- `scenes in` (read): the scenes of one collection.
- `create` (write): a new shared collection.
- `rename` (write): change a collection's name.
- `trash` (destructive): move a collection and all its scenes to trash.

## Finding things

- `C`, the collection id: the literal `private`, or from `list` by name.
- `NAME`: the collection's name.

## Recipes with excalidraw

### list

```bash
excalidraw collections list --limit 100 | jq '{hasNextPage, collections: [.data[] | {id, name, default: (.isDefault // false)}]}'
```

Returns `{hasNextPage, collections: [{id, name, default}]}`.

### show

```bash
excalidraw collections get "$C" | jq '{id, name, created, updated}'
```

### scenes in

```bash
excalidraw collections scenes list "$C" --limit 50 \
  | jq '{hasNextPage, scenes: [.data[].metadata | {id, name, updated, elements: .totalElements}]}'
```

Returns `{hasNextPage, scenes: [{id, name, updated, elements}]}`.

### create

```bash
excalidraw collections create --name "$NAME" | jq '{id, name}'
```

Returns `{id, name}`. Read-back: `show` on the returned id.

### rename

```bash
excalidraw collections update "$C" --name "$NAME" | jq '{id, name}'
```

Read-back: `show`; `name` matches.

### trash

Destructive: every scene in the collection goes to trash with it. Preview first and show it to the user: `scenes in`. Only after their explicit yes:

```bash
excalidraw collections delete "$C"
```

Prints `{}`. Read-back: `list` no longer shows the id, and `show` on it, like `scenes get` on each of its scenes, exits 1 with `HTTP 404`. The CLI cannot restore from trash; the user restores in the web app.

## Gotchas

- Names are not unique: `create` with an existing name makes a second collection. Run `list` first.
- A scene is created in a collection through [scenes](./scenes.md) `create`; moving one is `rename, move, pin` there.
- Only the name can be changed; a collection cannot be made private.
