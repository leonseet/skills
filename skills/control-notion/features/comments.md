# Comments

A comment is a message on a page or on one block, grouped into a **discussion** (a thread). Page comments show at the top of the page; block comments show beside their block. Comments the saved login posts carry the user as their author; an agent's own comments go out `as Claude Agent`.

Commands: `ntn api v1/comments`, `ntn api v1/comments/{id}`.

## Operations

- `list` (read): the open comments on a page or a block.
- `add` (write): a new discussion on a page or a block.
- `reply` (write): a comment in an existing discussion.
- `as Claude Agent` (write): post under the agent identity (SKILL.md) instead of the user.
- `edit` (write): change a comment's text.
- `delete` (destructive): remove one comment.

## Finding things

- `P` or `B`: the page, or the block a comment hangs on. From [pages](./pages.md) and [blocks](./blocks.md).
- `D` and `C`: the `discussion_id` and `id` from `list`.

## Recipes with ntn

### list (read)

```bash
ntn api v1/comments block_id=="$P" page_size==50 </dev/null \
  | jq $NJQ 'include "notion"; [.results[] | {id, discussion_id, at: .created_time[:16], text: (.rich_text | text | .[:300])}], {has_more}'
```

`block_id` takes a page id for page comments, or a block id for that block's comments. A page's listing does not include the comments on its blocks. Resolved discussions are left out. Comments come oldest first, one discussion's comments together.

### add (write)

```bash
ntn api v1/comments -d "$(jq -n --arg p "$P" --arg md "$(cat <<'EOF'
Comment text with `code` and **bold**.
EOF
)" '{parent: {page_id: $p}, markdown: $md}')" </dev/null | jq '{id, discussion_id}'
```

For a comment on one block, use `parent: {block_id: $b}` with `--arg b "$B"`. Read-back: `list` on the same page or block shows the text under the new `discussion_id`.

### reply (write)

```bash
ntn api v1/comments -d "$(jq -n --arg d "$D" --arg md "$(cat <<'EOF'
Reply text.
EOF
)" '{discussion_id: $d, markdown: $md}')" </dev/null | jq '{id, discussion_id}'
```

Read-back: `list` shows it after the discussion's earlier comments.

### as Claude Agent (write)

```bash
[ -n "$NOTION_CLAUDE_TOKEN" ] && NOTION_API_TOKEN="$NOTION_CLAUDE_TOKEN" ntn api v1/comments -d "$(jq -n --arg d "$D" --arg md "$(cat <<'EOF'
Reply text.
EOF
)" '{discussion_id: $d, markdown: $md}')" </dev/null | jq '{id, discussion_id, author: .display_name.resolved_name}'
```

`add` takes the same prefix. Read-back: `author` is the integration's display name. The guard matters: an empty variable falls through to the user's login without an error, and a session older than the startup-file line has it empty. `404 object_not_found` means the page is outside the integration's connection: ask the user to connect the integration to the page or a parent. Each identity edits and deletes only its own comments.

### edit (write)

```bash
ntn api v1/comments/"$C" -X PATCH -d "$(jq -n --arg md "$(cat <<'EOF'
Corrected comment text.
EOF
)" '{markdown: $md}')" </dev/null | jq $NJQ 'include "notion"; {id, text: (.rich_text | text)}'
```

Only comments this token wrote can be edited. Read-back: the returned `text`.

### delete (destructive)

Preview: show the user the comment's text from `list`. Only after their explicit yes:

```bash
ntn api v1/comments/"$C" -X DELETE </dev/null | jq '{id}'
```

Read-back: `list` no longer shows `C`.

## Gotchas

- The API cannot resolve or reopen a discussion. The user does that in Notion.
- A comment on a block that is in the trash moves to the page's `list`, and `edit` or `delete` on it fails with `400 validation_error: Can't edit block that is archived`. Find the block with `ntn api v1/comments/"$C" </dev/null | jq -r .parent.block_id`. Restore it with `ntn api v1/blocks/"$B" -X PATCH -d '{"in_trash": false}' </dev/null`, act on the comment, then delete the block again (blocks `delete`).
