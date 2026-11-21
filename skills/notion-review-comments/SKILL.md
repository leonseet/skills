---
name: notion-review-comments
description: "Answer and act on the open review comments of a Notion page: /notion-review-comments <page link>."
disable-model-invocation: true
---

# Notion review comments

Work through every open **discussion** on the page the **owner** linked: answer it, suggest the revision it asks for, reply in its thread. With no link, the page is the spec that the repo's `AGENTS.md` links. Page text changes only as a **suggested edit**, which the owner accepts or rejects. The owner is the user who ran this skill: the Notion connector acts as them, and their word decides. Notion mechanics come from two `control-notion` feature files, read directly: `~/.agents/skills/control-notion/features/suggested-edits.md` and `comments.md` beside it. Load the `control-notion` and `control-excalidraw` skills themselves only when a diagram, image or caption changes; their recipes and safety tags apply.

The owner resolves discussions and suggested edits. Leave every discussion open and every suggestion pending. The one exception: reject a suggestion you created in this run when it is faulty or superseded (suggested edits `resolve`), and name it in the report.

## Steps

1. **Collect.** Load the connector tools with the one ToolSearch call in suggested edits `Finding things`. `notion-get-comments` on the page returns every open discussion, block comments included, with each one's block id in its `discussion://<page>/<block>/<discussion>` URL. Done when `shown-count` equals `total-count` (fetch each `omitted-discussion` otherwise). `notion-fetch` the page for its text.
2. **Sort.** A discussion is **open for you** when its last comment is from a person (`user-url="user://…"`). One whose last comment is an agent's (`user-url="bot"`) is waiting on the owner: skip it. `by-you="true"` marks the owner's comments. Then, by what the last comment is:
   - A question, from anyone ("why…", "is it better to…", "what does this mean"): answer it in its thread and leave the page as it is. It skips step 4. When the answer shows the page's wording caused the question, quote a clearer wording in the reply for the owner to ask for.
   - The owner's statement is a decision. Apply it, even when it reverses what the page says.
   - Anyone else's statement is a request. Answer it; revise only what is plainly a fix (a typo, a missing definition), and bring the rest to the owner in the final report.
3. **Gather context** before answering: the repo's glossary and ADRs. An answer quotes the source of truth, not your guess.
4. **Revise, following the ripple.** A comment names one spot; the decision behind it usually lives in several. Change every place it appears:
   - the page text, as suggested edits (see "Suggesting edits");
   - each diagram that shows it. A caption's "Open in Excalidraw" link gives the scene id. Patch the scene, render, look at the PNG, then swap the render into the same image block (`control-notion` files `replace image`), so the block's discussion stays on it. Images cannot be suggested, so these are direct edits;
   - each image caption that words it, as a direct edit too: PATCH the caption with its link kept (`control-notion` files `replace image`). A suggested edit on a caption proposes an image block with no file, which shows as an empty "Add an image" box and drops the image when accepted;
   - a local copy of the text, when the repo keeps one, edited directly: its review is the git diff.
   Done when every place the old wording appears in the page text has a pending suggestion, and no diagram, caption or local copy has a trace of it.
5. **Reply** in each discussion, after its suggestions are read back as `pending`: the answer first, then, for a discussion you revised, `Suggested:` and what would change where (`Changed:` for the direct edits to diagrams and captions). When you chose between options, name the one you took and the alternative. When you did not act, say why.
6. **Report** to the owner: one row per discussion (comment, answer, what is suggested), the count of suggestions awaiting them, then what they should check: choices you made for them, stale text you noticed that no comment covered, requests from other people awaiting their call.

Complete when every discussion that was open for you ends on your reply and every reply's "Suggested" claim has been read back as a pending suggestion.

## Suggesting edits

The tool calls, the read-backs and the error codes are in suggested edits. How a review uses them:

- **One suggestion per block**, carrying every change to that block, so the owner accepts each block once. Rewrite the block whole (suggested edits `suggest`).
- When a whole block will not match and you fall back to its runs of plain text, tell the owner in the reply and the report which suggestions form one change, to accept together.
- On `suggested_edit_conflict`: when the older suggestion is yours from this run, reject it and suggest the block again with both changes. Otherwise put the wording in the reply and name the block in the report, for the owner to resolve the older suggestion first.
- Read-back: one suggested edits `list` after the last suggestion; every `suggested_edit_url` you were given appears in it. `diff` is for a suggestion whose result you doubt.

## Commenting as the agent

Replies post with comments `as Claude Agent`, the agent identity `control-notion` describes, with `D` the last segment of the discussion's `discussion://` URL, after its read-back names the author. If `NOTION_CLAUDE_TOKEN` is empty, stop and tell the owner rather than reply under their name; `control-notion`'s SKILL.md says how they set that identity up.

A reply that fails with `Failed to execute public API request` may have landed: run `notion-get-comments` on its discussion, then post again.
