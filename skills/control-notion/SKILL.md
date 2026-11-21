---
name: control-notion
description: "Operate a Notion workspace through the ntn CLI: pages (find, read as markdown, create, edit text, move, trash), blocks (list, insert, update, copy, delete), file uploads (images, HTML embeds, attachments), databases (schema, query, rows, properties) and comments. Use whenever a task reads or changes anything in Notion."
---

# Control Notion

Notion is reached through the Notion CLI `ntn` at the public API `api.notion.com`, one workspace per login. Raw endpoints go through `ntn api <path>` (`ntn api ls` lists them, `ntn api <path> --spec` gives the request schema). `ntn pages`, `ntn datasources` and `ntn files` wrap the common ones. `scripts/notion.py` holds `doctor` and the chains plain commands make clumsy: `children`, `images`, `attach` and `copy-blocks`. `scripts/notion.jq` holds the jq helpers the recipes include (`title`, `props`, `btext`, `text`).

## Setup

A new machine needs, in this order (`doctor` checks each and prints the fix for what is missing):

1. `uv`: `curl -LsSf https://astral.sh/uv/install.sh | sh`. `doctor` and the chains run on it.
2. `ntn` 0.23.28 in `~/.local/bin` (must be on `PATH`). The user installs it in their own terminal with `curl -fsSL https://ntn.dev | bash`. To upgrade, run `ntn update`. In an agent's shell, which has no terminal, `ntn update` only reports the new version; `script -qec "ntn update" /dev/null` gives it one and runs the upgrade.
3. `jq`: `sudo apt install jq` on Linux, `brew install jq` on macOS.
4. A place for the login. `ntn` keeps it in the OS keychain: macOS always has one; Linux has one only with a running Secret Service (GNOME Keyring, KWallet). Without one, `ntn login` fails with `Failed to create keychain entry` and every later call with `No auth token found for the current workspace`: export `NOTION_KEYRING=0` in the shell's startup file (`~/.bashrc`, `~/.zshrc`), and `ntn` keeps the login in `~/.config/notion/auth.json` instead.
5. Login: the user runs `ntn login` in their own terminal (`! ntn login` from the agent prompt). It opens a browser; they pick the workspace. The token is saved in the keychain, or in `~/.config/notion/auth.json` under `NOTION_KEYRING=0`, and belongs to the bot **Notion CLI**, owned by that user. Alternatively, `NOTION_API_TOKEN` in the shell overrides the saved login. An internal-integration token there only sees pages explicitly shared with that integration.

Credentials live only where `ntn` reads them (the saved login or the shell variable), never in a repo `.env`. Recipes call `ntn` directly, and `ntn` does not read `.env`. `api.notion.com` is public and publicly trusted.

## Doctor

```bash
uv run ~/.agents/skills/control-notion/scripts/notion.py doctor
```

One `ok`/`WARN`/`FAIL` line each, in this order:

- uv
- `ntn` and its version
- jq
- where the credentials come from
- auth (`v1/users/me`)
- the workspace
- the `Notion-Version` header `ntn` sends, against the one this map was proven on

Every `FAIL` has a `fix:` line under it. Run it first, and again whenever a command fails strangely.

On a `FAIL`, stop the task and walk the user through the `fix:` lines one at a time, offering to run each fix yourself; then rerun `doctor` until it is clean. Install commands and edits to the shell's startup file run only after the user's yes. The user logs in or sets tokens themselves, never through the chat. A `FAIL` with no fix you can apply is reported to the user, never worked around. A version `WARN` means a recipe may have drifted: check `ntn <command> --help` or `ntn api <path> --spec`.

## Instances & conventions

- **One workspace**: the one picked at `ntn login`; `doctor` names it and the identity the token acts as. A saved login acts as the user: it reaches every page they can, and comments it posts show them as the author.
- **Workspace map**: `~/.config/control-notion/workspace.md`, this machine's notes on the workspace: the fixed pages and databases with their ids, where a new page goes, the sandbox. Read it before the first recipe when it exists. For what it lacks, or when the file is missing: the current repo's `AGENTS.md` or `CLAUDE.md` (a repo names its own pages there), then [pages](features/pages.md) `find by title`, then the user. Offer to record what the user answers in the map, ids only.
- **Agent identity** (optional): an internal integration the user created for agents, its token in `NOTION_CLAUDE_TOKEN` in the shell. Comments an agent writes go through it, so a thread shows who said what: [comments](features/comments.md) `as Claude Agent`. It reaches only the pages it is connected to. To set it up, the user creates an internal integration at notion.so/profile/integrations, connects it to a root page, and exports its token under that name in their shell's startup file (`~/.bashrc`, `~/.zshrc`).
- **Where a new page goes**: where the user says, else where the workspace map says, else ask.
- **Sandbox**: the page the workspace map names. With none recorded, ask the user for a page to write under, tell them that proof writes will land there, and record it in the map.
- **Ids**: `ntn` takes an id with or without dashes, never a URL. From a URL: `P=$(grep -oE '[0-9a-f]{32}' <<<"${URL%%\?*}" | tail -1)`. For a peek link (`…?p=<id>&pm=s`), take the `p=` value.
- **Recipe variables**:
  - `P` page
  - `B` block
  - `PARENT` page or block to add under
  - `AFTER` sibling block to insert after
  - `TO` destination page
  - `DB` database
  - `DS` data source
  - `R` database row
  - `C` comment
  - `D` discussion
  - `UP` file upload
  - `FILE` local file
  - `Q` search text
  - `TITLE` page title
  - `BODY` scratch JSON file (`BODY=$(mktemp).json`; macOS `mktemp` has no `--suffix`)

  Each feature's `Finding things` says how to get them. `NJQ="-L $HOME/.agents/skills/control-notion/scripts"` makes `include "notion";` resolve. Set it once per shell, unquoted where used.

## Safety

Every operation in `features/` is tagged:

- **read**: run freely.
- **write**: run when the user asked for that change, then run the recipe's read-back and report what it shows.
- **destructive** (delete a block, trash a page or row, replace a page's whole content, delete a comment, drop a property): show the user exactly what goes, using the recipe's preview, and run it only after their explicit yes in the conversation. A Notion comment the user wrote that names what goes is also that yes, for exactly what it names. Notion keeps trashed pages for 30 days, but that does not lower the bar.

Free text (page markdown, comments, block text) goes into commands through a quoted heredoc (`"$(cat <<'EOF' … EOF)"`) and `jq --arg`, never inside `"..."`, where backticks run as commands. The token never appears in output, files or messages: leave `ntn auth token` alone.

## Operate

Read [`features/README.md`](features/README.md): the common-task chains, then one recipe file per resource area.

## Beyond ntn

Two things only the Notion connector does (load its tools with ToolSearch; they act as the user):

- **Every open discussion of a page in one call**: `notion-get-comments` with the page id. It covers block comments, which `ntn` lists one block at a time. A person's comment carries `user-url="user://…"`, an integration's `user-url="bot"`.
- **Suggested edits**, a text change the user accepts or rejects: [suggested edits](features/suggested-edits.md).

## Output shaping

Keep calls few and output small:

- `ntn api` prints the full API JSON: pipe it through a `jq` projection of the fields the task needs. `include "notion";` gives `title`, `props` and `btext` instead of hand-walking rich text.
- Every listing sets its size: `page_size==N` on GET endpoints, `"page_size": N` in POST bodies, `--limit N` on `ntn datasources query`. To get every child block, every page of them, use the script's `children`.
- Page markdown can be long, and Notion-hosted file URLs carry about 1.5 KB of signature each. Cut both: `ntn pages get "$P" </dev/null | sed -E 's/\?X-Amz-[^")> ]*//g' | head -c 20000`. Fetch a whole page only into a file.

## Gotchas

- `ntn api` with an open stdin waits for a request body and hangs. Every recipe ends `</dev/null`; only `ntn files create` reads stdin, and it gets the file.
- On GET endpoints, query parameters use `==` (`page_size==100`). `page_size:=100` or `page_size=100` makes a body, and a body flips the method to POST: `400 invalid_request_url: Invalid request URL`.
- Errors are plain text on stderr. Keep `2>&1` out of a pipe into `jq`: it turns every error into `parse error: Invalid numeric literal` and hides the real one.
- `error: Failed to execute public API request` is transient. Rerun a read. After a write, first read back whether it landed, then rerun. The script's chains retry reads and `rate_limited` on their own.
- `400 validation_error: This page's ancestor is in the trash` (older wording: `Can't edit page on block with an archived ancestor`) means the target or one of its parents is in the trash. Restore it (pages `restore`) or pick another target.
- The API rejects the nulls it returns on read: `body.children[0]…icon should be an object or undefined, instead was null`. Block JSON copied from a read needs its nulls dropped. `copy-blocks` does this.
- Page markdown is Notion's "enhanced markdown" (`v1`), the default for API version `2026-03-11`. The next API version rejects `v1`. When `doctor` warns that the API version changed, re-prove the markdown recipes in `pages.md`.
