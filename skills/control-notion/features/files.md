# Files

A file upload is a file staged in Notion, then attached to a block (image, embed, file, pdf, video, audio), a page icon or cover, or a `files` property. An upload that is never attached expires an hour after it was created. HTML attached as an `embed` renders inline in an iframe: this is how charts and plots go on a page.

Commands: `ntn files create|get|list`, script `attach`.

## Operations

- `attach` (write): upload a local file and append it as one block, in one step.
- `upload` (write): stage a local file and get its upload id.
- `import from URL` (write): stage a public HTTPS file without downloading it.
- `use an upload` (write): put a staged upload into a block you build yourself.
- `replace image` (write): put a new file into an existing image block, keeping its caption and comments.
- `status` (read): one upload's state and expiry.
- `list` (read): recent uploads.

## Finding things

- `FILE`: a local path. The MIME type comes from the extension; `.html` attaches as an embed, images as `image`, `.pdf` as `pdf`, anything else as `file`.
- `PARENT` and `AFTER`: as in [blocks](./blocks.md).
- `UP`: from `upload` or `import from URL` (`id`), or from `list`.

## Recipes with ntn

### attach (write)

```bash
uv run ~/.agents/skills/control-notion/scripts/notion.py attach "$FILE" --to "$PARENT" --after "$AFTER" --caption "$(cat <<'EOF'
Caption text
EOF
)"
```

Returns `{block_id, type, upload_id}`. Instead of `--after "$AFTER"`, `--start` inserts the block first, and with neither it goes last. `--as image|embed|file|pdf|video|audio` overrides the guessed block type. `--caption` is optional. Read-back: `ntn api v1/blocks/"$PARENT"/children page_size==100 </dev/null | jq -c '.results[] | {id, type}'` lists `block_id` with the expected `type`.

### upload (write)

```bash
ntn files create --filename "$(basename "$FILE")" --content-type "$(file -b --mime-type "$FILE")" --json < "$FILE" \
  | jq '{id, status, filename, content_type, content_length, expiry_time}'
```

Returns `status: "uploaded"` and an `expiry_time` an hour away. Set both `--filename` and `--content-type`: a piped stdin has no name, and HTML must say `text/html` to render as an embed. Attach it with `use an upload` before it expires. Read-back: `status` on `id`.

### import from URL (write)

```bash
ntn files create --external-url "$URL" --json </dev/null | jq '{id, status, filename, content_type}'
```

Returns `status: "pending"`. Notion fetches the file in the background, and a few seconds later `status` shows `uploaded`. The URL must be public and answer a HEAD request. Notion's own signed file URLs do not: `400 validation_error: Failed to fetch the headers of the external URL`. To reuse a Notion-hosted file, use [blocks](./blocks.md) `copy`, which downloads and re-uploads it.

### use an upload (write)

```bash
ntn api v1/blocks/"$PARENT"/children -X PATCH -d "$(jq -n --arg up "$UP" --arg after "$AFTER" \
  '{position: {type: "after_block", after_block: {id: $after}}, children: [{type: "image", image: {type: "file_upload", file_upload: {id: $up}}}]}')" </dev/null \
  | jq '.results[0] | {id, type}'
```

For HTML, use `type: "embed", embed: {type: "file_upload", file_upload: {id: $up}}`. Swap `image` the same way for `file`, `pdf`, `video` or `audio`. A page cover or icon takes the same object: `ntn api v1/pages/"$P" -X PATCH -d '{"cover": {"type": "file_upload", "file_upload": {"id": "…"}}}'`. Read-back: as in `attach`.

### replace image (write)

```bash
UP=$(ntn files create --filename "$(basename "$FILE")" --content-type "$(file -b --mime-type "$FILE")" --json < "$FILE" | jq -r .id)
ntn api v1/blocks/"$B" -X PATCH -d "$(jq -n --arg up "$UP" '{image: {file_upload: {id: $up}}}')" </dev/null | jq '{id, type: .image.type}'
```

`B` comes from `uv run ~/.agents/skills/control-notion/scripts/notion.py images "$P"`: every image block of the page as `{id, caption, links, source}`, where `links` holds the caption's hrefs (a diagram's "Open in Excalidraw" link names its scene). `children` gives each block's text only, without links.

Returns `type: "file"`. The block, its caption and its discussions stay. Send no `type` key beside `file_upload`: `400 body.image.type should be not present`. To change the caption, PATCH `{image: {caption: [...]}}` with the whole rich text, links included. Read-back: download `.image.file.url` from `ntn api v1/blocks/"$B"` and check it is the new file.

### status (read)

```bash
ntn files get "$UP" --json </dev/null | jq '{status, filename, content_type, expiry_time, file_import_result: .file_import_result.type}'
```

Once the upload is attached, `expiry_time` turns `null`.

### list (read)

```bash
ntn files list --json </dev/null | jq '[.[:10][] | {id, filename, status, created: .created_time}]'
```

Returns a bare array, newest first: only the first page, since `ntn files list` does not paginate.

## Gotchas

- Plotly HTML that inlines the 4.8 MB plotly.js bundle does not render in Notion. Swap the bundle for a CDN script tag (about 35 to 110 KB left) before uploading it.
- Notion-hosted file URLs, from a block or from page markdown, are signed and expire after an hour. To share a file, link the page; for a fresh URL, `get` the block again.
- A failed attach can leave a staged upload behind. It expires by itself within the hour and needs no cleanup.
