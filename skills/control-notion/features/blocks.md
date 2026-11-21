# Blocks

A block is one piece of a page's body: paragraph, heading, toggle, table, image, embed, child page, and so on. A block can hold child blocks; a toggle heading's children are what it folds. Work at block level for structure markdown cannot express, such as toggle headings with tables, embeds and inserts at an exact position. Plain text edits go through [pages](./pages.md). Images and files go through [files](./files.md).

Commands: `ntn api v1/blocks/{id}`, `ntn api v1/blocks/{id}/children`, script `children`, `copy-blocks`.

## Operations

- `list children` (read): one level of a page's or block's children.
- `list all` (read): every child, all result pages followed, optionally nested.
- `get` (read): one block's full JSON.
- `insert` (write): new blocks at the end, the start, or after a sibling.
- `update` (write): change one block's text or settings.
- `copy` (write): duplicate blocks with all their children, here or under another parent.
- `move` (write + destructive): `copy`, then `delete` the original. The API has no move.
- `delete` (destructive): trash a block and its children.

## Finding things

- `PARENT` is a page id (its body) or a block id (that block's children).
- `B` and `AFTER`: from `list children` or `list all`, matched on `type` and `text`.
- A link copied from a block in the Notion app ends `#<32 hex>`: that suffix is the block id.

## Recipes with ntn

### list children (read)

```bash
ntn api v1/blocks/"$PARENT"/children page_size==100 </dev/null \
  | jq $NJQ 'include "notion"; [.results[] | {id, type, has_children, text: (btext | .[:80])}], {has_more, next_cursor}'
```

Returns one page of up to 100 children, then `{has_more, next_cursor}`. For the next page, add `start_cursor=="$CURSOR"`, or use `list all`.

### list all (read)

```bash
uv run ~/.agents/skills/control-notion/scripts/notion.py children "$PARENT" --deep --width 80 | jq -c '.[]'
```

Prints one JSON line per block, `{depth, id, type, has_children, text}`, in page order. Children follow their parent at `depth + 1`, and table rows read `cell | cell`. Leave out `--deep` for one level, all pages followed. The listing does not descend into child pages and stops at `--limit` blocks (default 500).

### get (read)

```bash
ntn api v1/blocks/"$B" </dev/null | jq 'del(.created_by, .last_edited_by, .request_id)'
```

This is the block's input shape for `update`, and the live signed URL of an image, file or embed (valid for an hour).

### insert (write)

Write the blocks to `BODY`, then append. This example is a toggle heading holding a bold-label paragraph and a two-column table, inserted as the parent's first child:

```bash
BODY=$(mktemp).json
cat > "$BODY" <<'EOF'
{"position": {"type": "start"},
 "children": [
  {"type": "heading_3", "heading_3": {"is_toggleable": true, "rich_text": [{"text": {"content": "2026-11-11 16:30 What the fix does"}}],
   "children": [
     {"type": "paragraph", "paragraph": {"rich_text": [{"text": {"content": "Verdict: "}, "annotations": {"bold": true}}, {"text": {"content": "fixed"}}]}},
     {"type": "table", "table": {"table_width": 2, "has_column_header": true, "children": [
        {"type": "table_row", "table_row": {"cells": [[{"text": {"content": "metric"}}], [{"text": {"content": "value"}}]]}},
        {"type": "table_row", "table_row": {"cells": [[{"text": {"content": "recall"}}], [{"text": {"content": "0.65"}}]]}}]}}
   ]}}
 ]}
EOF
ntn api v1/blocks/"$PARENT"/children -X PATCH -d @"$BODY" </dev/null | jq '[.results[:1][] | {id, type, has_children}]'
```

`position` is `{"type": "start"}`, `{"type": "end"}` (the default), or `{"type": "after_block", "after_block": {"id": "<AFTER>"}}`. The response lists the parent's children from the first new block onward: its first `n` entries are the `n` blocks you sent. The exception is an `end` append, where the whole first page of children comes back and the new blocks are last. For a link, give a text object `"link": {"url": "…"}`. Gray text is `"annotations": {"color": "gray"}`. Read-back: `list all` on `PARENT` shows the new blocks at the requested position.

### update (write)

```bash
ntn api v1/blocks/"$B" -X PATCH -d "$(jq -n --arg t "$(cat <<'EOF'
New text of the block
EOF
)" '{heading_3: {rich_text: [{text: {content: $t}}]}}')" </dev/null \
  | jq $NJQ 'include "notion"; {id, type, text: btext}'
```

The top-level key is the block's own type (`paragraph`, `heading_3`, `toggle`, `callout`, …). Only the fields you send change, and `rich_text` is replaced whole. A block's type cannot change: insert a new block and delete the old one. Read-back: the returned `text` is the new text.

### copy (write)

```bash
uv run ~/.agents/skills/control-notion/scripts/notion.py copy-blocks "$B" --to "$PARENT" --after "$AFTER"
```

Copies block `B` with every nested child to `PARENT`, after `AFTER`; `--start` puts it first, and with neither it goes at the end. With a page id as `B`, or with `--children-only`, it copies the content instead of the block itself. Notion-hosted images, files and embeds are downloaded and uploaded again. Returns `{copied, skipped}`. Child pages, child databases and synced-block references cannot be created this way and are listed in `skipped`. Read-back: `list all` on `PARENT` shows the copy, with the same `text` as the source at each depth.

### delete (destructive)

Preview: `list all` on `B` (with `--deep`) and `get` on `B`. Show the user the block and every child that goes with it. Only after their explicit yes:

```bash
ntn api v1/blocks/"$B" -X DELETE </dev/null | jq '{id, type, in_trash}'
```

Read-back: `in_trash: true`, and `list children` on the parent no longer shows `B`. To undo, `ntn api v1/blocks/"$B" -X PATCH -d '{"in_trash": false}' </dev/null` puts the block and its children back under their parent.

## Gotchas

- Appending children is `PATCH`, not `POST`. POST to `/children` fails with `invalid_request_url`.
- One request takes at most 100 children and two levels of nesting under the top block, as the `insert` example shows. Go deeper by appending to the new block's id afterwards; `copy-blocks` works this way.
- A table is created with its rows inside it, and `table_width` must equal the number of cells in every row.
- Block JSON from a read is not valid input as it stands. Drop the nulls (`icon: null` fails validation), the ids and timestamps, and Notion-hosted `file` objects, which must be uploaded again. `copy-blocks` does all of this.
- A rich-text `content` holds at most 2,000 characters. Split longer text across several text objects.
