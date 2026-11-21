# Suggested edits

A suggested edit is a proposed change to page text that the user accepts or rejects in Notion. The page stays as it is until they accept. They go through the Notion connector, which acts as the user; `ntn` sees no pending suggestion.

Commands: none in `ntn`. Connector tools `notion-fetch`, `notion-get-comments`, `notion-create-suggested-edit`, `notion-get-suggested-edit`, `notion-resolve-suggested-edit`.

## Operations

- `list` (read): the pending suggestions on a page.
- `diff` (read): one suggestion's before and after.
- `suggest` (write): propose a replacement, a deletion or an insertion.
- `resolve` (write): accept or reject one suggestion.

## Finding things

- Load the tools in one ToolSearch call: `select:mcp__claude_ai_Notion__notion-get-comments,mcp__claude_ai_Notion__notion-fetch,mcp__claude_ai_Notion__notion-create-suggested-edit,mcp__claude_ai_Notion__notion-get-suggested-edit,mcp__claude_ai_Notion__notion-resolve-suggested-edit`.
- `P`: the page id, as in [pages](./pages.md).
- `old_text`: copied from `notion-fetch` on `P` with `include_discussions: true`. Its markdown differs from `ntn pages get`: `<code>` and `<b>` against backticks and `**`.
- `U`: a suggestion's `discussion://<page>/<block>/<suggestion>` URL, from `suggest` or `list`. The middle segment is its block; for an insertion it is the proposed new block, not the block of `old_text`.

## Recipes with ntn

### list (read)

`notion-get-comments` with `page_id: P`. Each pending suggestion is a discussion with `kind="suggested_edit"`, `resolved="false"`, its block id in the URL and a `text-context`. A resolved one no longer appears. `suggested_edits_status` other than `included` means the listing could not see suggestions.

### diff (read)

`notion-get-suggested-edit` with `suggested_edit_url: U`. Returns `status`, the `diff` and `allowed_actions`.

### suggest (write)

`notion-create-suggested-edit` with `page_id`, `old_text`, `new_text` and, optionally, `mode`:

- `replace` (the default) rewrites `old_text`; an empty `new_text` suggests deletion.
- `insert_after` and `insert_before` add `new_text` as new blocks beside the block of `old_text`.

`new_text` is Notion markdown (backticks and `**` are fine). Returns `{suggested_edit_url, status: "pending"}`.

To rewrite a block, give its full text as `old_text`, markup included, without the list marker. A bullet with bold and code spans is replaced in one suggestion this way.

Read-back: `list` shows `U`; `diff` on it shows the change.

### resolve (write)

`notion-resolve-suggested-edit` with `suggested_edit_url: U` and `action: accept` or `reject`. Returns the new `status`. Accepting changes the page, so it is the user's call unless they said otherwise. Read-back: `list` no longer shows `U`.

## Gotchas

- A block (a paragraph, a bullet, a whole code block) holds one pending suggestion. A second one anywhere in the block fails with `suggested_edit_conflict`, even on text the first did not touch. Put every change to a block in one suggestion, or resolve the older one first. An insertion counts against the block of its `old_text`: a second insertion beside the same block conflicts too, so send neighbouring new blocks as one `new_text`.
- `suggested_edit_multiple_matches`: `old_text` occurs more than once on the page. Widen it until it is unique.
- `suggested_edit_no_match`: `old_text` is not in the accepted page text as `notion-fetch` prints it. The usual causes:
  - markup written the `ntn` way (backticks) instead of the fetched way (`<code>`);
  - text that carries an inline comment, which matches only with its `<span discussion-urls="…">` wrapper included, as fetched (seen on a live page, not reproduced in the sandbox: the API cannot make inline comments);
  - text that exists only inside a pending suggestion, which is not accepted content yet.
- When a whole block still fails to match, suggest the runs of plain text between its formatted spans instead. Each is its own suggestion to accept.
- A suggested edit on an image caption proposes an image block with no file, which drops the image when accepted. Change captions directly ([files](./files.md) `replace image`).
- `entitlement_required` means the workspace plan lost access to suggested edits. Stop and tell the user; a direct text edit is not the fallback.
