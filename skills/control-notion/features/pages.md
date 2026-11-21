# Pages

A page is a document: a title, optional properties (when it is a database row), and a body of blocks. Pages nest under pages or sit as rows in a database. Their body reads and writes as markdown, which suits text. Structured blocks (toggle headings, tables, embeds) go through [blocks](./blocks.md). Database rows are pages too: their properties live in [databases](./databases.md), their body here.

Commands: `ntn api v1/search`, `ntn pages get|create|edit|trash`, `ntn api v1/pages/{id}`, `ntn api v1/pages/{id}/markdown`, `ntn api v1/pages/{id}/move`.

## Operations

- `find by title` (read): pages whose title matches text.
- `read` (read): a page's body as markdown, with its properties as frontmatter.
- `info` (read): title, parent, URL, trash state.
- `create` (write): a new page from markdown under a page.
- `append` (write): markdown added at the end or start of a page.
- `edit text` (write): exact search-and-replace in a page's body.
- `rename` (write): change the title.
- `move` (write): give a page a new parent.
- `restore` (write): bring a trashed page back.
- `replace content` (destructive): overwrite the whole body.
- `trash` (destructive): move a page and everything under it to the trash.

## Finding things

- `P` from a URL: `P=$(grep -oE '[0-9a-f]{32}' <<<"${URL%%\?*}" | tail -1)`. From a title: `find by title`. The workspace's fixed pages are in the workspace map (SKILL.md).
- Child pages of a page: `uv run ~/.agents/skills/control-notion/scripts/notion.py children "$P" | jq -c '.[] | select(.type=="child_page") | {id, text}'`.
- `PARENT` for a new page: the page the user named. Otherwise per SKILL.md "Where a new page goes".
- `TO` for `move`: a page id, or a data source id to make the page a row of it.

## Recipes with ntn

### find by title (read)

```bash
ntn api v1/search -d "$(jq -n --arg q "$Q" '{query: $q, filter: {property: "object", value: "page"}, page_size: 10}')" </dev/null \
  | jq $NJQ 'include "notion"; [.results[] | {id, title: title, parent: (.parent.page_id // .parent.data_source_id // "workspace"), edited: .last_edited_time[:10]}]'
```

Returns `[{id, title, parent, edited}]`, most recently edited first. The search matches titles loosely, so check `title` before acting. An empty `Q` lists everything the token sees.

### read (read)

```bash
ntn pages get "$P" </dev/null | sed -E 's/\?X-Amz-[^")> ]*//g' | head -c 20000
```

Prints frontmatter (`title`, or a row's properties), a blank line, then the body as markdown. Toggles come out as `<details><summary>`, embeds as `<embed src=…>`, callouts as `<callout>`. The `sed` drops the signatures from Notion-hosted file URLs, so those links no longer open. For a live file URL, read the block in [blocks](./blocks.md). When the page is too big for one read, stderr says so: `ntn pages get "$P" --json </dev/null | jq '.markdown | {truncated, unknown_block_ids}'` names the blocks to read separately.

### info (read)

```bash
ntn api v1/pages/"$P" </dev/null | jq $NJQ 'include "notion"; {id, title: title, parent, in_trash, url, edited: .last_edited_time}'
```

### create (write)

```bash
ntn pages create --parent "page:$PARENT" --json --content="$(cat <<'EOF'
---
title: Page title
---
Body in **markdown**.

- a list item
EOF
)" </dev/null | jq '{id, url}'
```

Returns `{id, url}`. The frontmatter `title` becomes the title; any other frontmatter is ignored. Keep the `=` in `--content=`: without it, content starting with `---` parses as a flag (`error: unexpected argument '---…'`). Read-back: `read` on the new `id` shows the title and body.

### append (write)

```bash
ntn api v1/pages/"$P"/markdown -X PATCH -d "$(jq -n --arg md "$(cat <<'EOF'
## New section

Text to add.
EOF
)" '{type: "insert_content", insert_content: {content: $md, position: {type: "end"}}}')" </dev/null \
  | jq '{truncated, warnings, tail: (.markdown | .[-400:])}'
```

Returns the page's new markdown, cut here to its tail. `position: {type: "start"}` prepends. To insert after a passage instead, replace `position` with `after: "first words...last words"` of the passage. `insert_content` is marked deprecated in the API spec but works on `2026-03-11`. Read-back: `tail` ends with the added text.

### edit text (write)

```bash
ntn api v1/pages/"$P"/markdown -X PATCH -d "$(jq -n --arg old "$(cat <<'EOF'
exact text now on the page
EOF
)" --arg new "$(cat <<'EOF'
the replacement
EOF
)" '{type: "update_content", update_content: {content_updates: [{old_str: $old, new_str: $new}]}}')" </dev/null \
  | jq '{warnings, truncated}'
```

`old` must match the page's markdown exactly as `read` prints it, `**bold**` and backticks included, and must occur once (add `replace_all_matches: true` to change every occurrence). Send several edits in one call by adding more `{old_str, new_str}` items. Each item that matches nothing comes back in `warnings` as `no_match`; the call fails only when none match. Read-back: `warnings` is `null`, and `read` shows the new text.

### rename (write)

```bash
ntn api v1/pages/"$P" -X PATCH -d "$(jq -n --arg t "$TITLE" '{properties: {title: {title: [{text: {content: $t}}]}}}')" </dev/null \
  | jq $NJQ 'include "notion"; {id, title: title}'
```

The key `title` is the title property's id, so this also renames a database row whatever its title column is called. Read-back: the returned `title` equals `TITLE`.

### move (write)

```bash
ntn api v1/pages/"$P"/move -d "$(jq -n --arg to "$TO" '{parent: {type: "page_id", page_id: $to}}')" </dev/null | jq '{id, parent}'
```

To move it into a database, use `{type: "data_source_id", data_source_id: $to}`. Read-back: `info` shows the new `parent`.

### restore (write)

```bash
ntn api v1/pages/"$P" -X PATCH -d '{"in_trash": false}' </dev/null | jq '{id, in_trash}'
```

Read-back: `in_trash` is `false`.

### replace content (destructive)

Preview: run `read` and show the user the body that will go, and say whether it holds child pages or databases. Only after their explicit yes:

```bash
ntn pages edit "$P" --content="$(cat <<'EOF'
The whole new body.
EOF
)" </dev/null | head -c 400
```

Prints the page id. When the page has child pages or databases, the edit is refused with `400 validation_error: This operation would delete 1 child page(s), database(s), or meeting note(s)`, followed by their titles and ids. To keep them, put each one's `<page url="…">…</page>` (or `<database url=…>`) line from `read` into the new content. `--allow-deleting-content` deletes them instead, and needs its own yes. Prefer `edit text` or `append`, which leave the rest of the page alone. Read-back: `read` shows only the new body, plus any kept child pages.

### trash (destructive)

Preview: `info` plus `uv run ~/.agents/skills/control-notion/scripts/notion.py children "$P" | jq -c '[.[] | select(.type=="child_page" or .type=="child_database") | .text]'`, the sub-pages that go with it. Only after the user's explicit yes:

```bash
ntn pages trash "$P" --yes </dev/null
```

Prints `✔ Page trashed`. Its child pages go to the trash with it, and come back with it. Read-back: `info` shows `in_trash: true`. `restore` undoes it within 30 days.

## Gotchas

- `ntn pages create --parent data-source:<id>` sets only the title of the new row. For row properties, use [databases](./databases.md) `add row`.
- Markdown cannot express every block. Tables with merged cells, embeds and file blocks round-trip through `read` only approximately, so edit them as [blocks](./blocks.md).
- `edit text` sees the page as `read` prints it. Text inside a collapsed toggle is part of it and matches.
