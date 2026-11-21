---
name: control-excalidraw
description: "Operate an Excalidraw+ workspace (api.excalidraw.com) and local .excalidraw files through the excalidraw CLI: scenes (find, create, rename, move, share link, trash), scene content (read elements, patch, replace, render to PNG/SVG), collections, local files (Mermaid to scene, draw a layout from a spec, render a file) and workspace reads (members, invites, audit logs). Use whenever a task reads, draws or changes anything in Excalidraw."
---

# Control Excalidraw

Excalidraw+ is reached through the official CLI `excalidraw` (`@excalidraw/cli`) at the public API `api.excalidraw.com`. One API key reaches one workspace: the one it was created in. The same CLI renders `.excalidraw` files and converts Mermaid locally, with no account. `scripts/excalidraw.py` holds `doctor` and what plain commands make clumsy: `edit-element` (change one element of a scene), `draw` (a spec of boxes, grids, texts, arrows and frames to a `.excalidraw` file) and `lint` (layout faults in a file).

## Setup

A new machine needs, in this order (`doctor` checks each and prints the fix for what is missing):

1. `uv`: `curl -LsSf https://astral.sh/uv/install.sh | sh`. `doctor` and the chain run on it.
2. Node 22 or newer. Under fnm: `fnm install 22 && fnm default 22`.
3. `excalidraw` 0.3.0: `npm install -g @excalidraw/cli@0.3.0`. A global npm install belongs to one Node version: after switching Node with fnm or nvm, install it again.
4. `jq`: `sudo apt install -y jq` on Linux, `brew install jq` on macOS.
5. Chrome, Chromium, Edge or Firefox, for `render` and `mermaid`. `doctor` looks on `PATH` and, on macOS, in `/Applications`. `EXCALIDRAW_BROWSER_PATH` names another binary.
6. An API key. The user creates a personal key (it starts `uk-`) at app.excalidraw.com under Account settings → MCP/API key, with full access, then runs `excalidraw login` in their own terminal (`! excalidraw login` from the agent prompt) and pastes it at the prompt. The CLI checks the key and saves it in `~/.config/excalidraw-cli/credentials.json`. Alternatively `export EXCALIDRAW_API_KEY=…` in the shell's startup file (`~/.bashrc`, `~/.zshrc`); the variable overrides the saved key.

The CLI does not read `.env` files: a key in a repo `.env` is invisible to it. `api.excalidraw.com` is public and publicly trusted; behind a proxy the CLI honours `HTTPS_PROXY` and `NO_PROXY`, and a proxy that intercepts TLS needs its CA bundle in `NODE_EXTRA_CA_CERTS`.

## Doctor

```bash
uv run ~/.agents/skills/control-excalidraw/scripts/excalidraw.py doctor
```

One `ok`/`WARN`/`FAIL` line each, in this order: node, the CLI and its version, jq, browser, where the API key comes from, host, auth (`excalidraw whoami`: key type and workspace), service version. Every `FAIL` has a `fix:` line under it. Run it first, and again whenever a command fails strangely.

On a `FAIL`, stop the task and walk the user through the `fix:` lines one at a time, offering to run each fix yourself; then rerun `doctor` until it is clean. Installs run only after the user's yes. The user creates the key and logs in themselves, never through the chat. A `FAIL` with no fix you can apply is reported to the user, never worked around. A `FAIL api key` blocks only the workspace features: [`features/files.md`](features/files.md) works without a key. A version `WARN` means a recipe may have drifted: check `excalidraw <command> --help`.

## Instances & conventions

- **One workspace**: the one the key belongs to; no flag switches workspace. `excalidraw whoami` names it, the key's type and its owner. A personal key acts as that user, with their role: writes are logged under their name "via API key", and the admin-only commands in [workspace](features/workspace.md) need an admin's key.
- **Collections**: every scene lives in exactly one.
  - `private`: the built-in private collection. The literal id is `private`; only personal keys reach it.
  - Every other collection, the default shared one included: id from [collections](features/collections.md) `list`, by name.
  - A repo's collection: the current repo's `AGENTS.md` or `CLAUDE.md` names it when the repo keeps diagrams in one. Otherwise ask the user.
- **Sandbox**: a collection named `control-sandbox`. Look for it with [collections](features/collections.md) `list`; when it is missing, tell the user you will create it, create it, work only inside it, and ask before trashing it.
- **Where a new scene goes**: where the user says; otherwise `private`. No naming rule for scenes.
- **Recipe variables**: `N` scene id, `C` collection id, `E` element id, `NAME` a scene or collection name, `FILE` a local `.excalidraw` or `.mmd` file, `OUT` an output path, `Q` search text. Each feature's `Finding things` says how to get them.

## Safety

Every operation in `features/` is tagged:

- **read**: run freely.
- **write**: run when the user asked for that change, then run the recipe's read-back and report what it shows. Local-file writes (`render`, `mermaid`, `--out`) overwrite their target without asking: write to a new path or the scratch directory unless the user named the file.
- **destructive** (trash a scene or collection, replace a scene's whole content, delete an element, anything under `workspace users` or `workspace invites` that removes or revokes): show the user exactly what goes, using the recipe's preview, and run it only after their explicit yes in the conversation. A Notion comment the user wrote that names what goes is also that yes, for exactly what it names. Trash is restorable only from the web app, which does not lower the bar.

Turning a share link on publishes the scene to anyone holding the URL, without sign-in: do it only when the user asked for a public link. The API key never appears in output, files or messages: leave `credentials.json` unread.

## Operate

Read [`features/README.md`](features/README.md): the common-task chains, then one recipe file per resource area.

## Output shaping

Keep calls few and output small:

- Every command prints JSON; pipe it through a `jq` projection. A scene's metadata is about 1 KB, most of it noise.
- Every listing passes `--limit` (default 5, max 100). `--all` walks every page and changes the envelope from `{limit, offset, hasNextPage, data}` to `{count, data}`.
- Scene content is large (the welcome scenes hold 600 to 1200 elements, about 0.5 KB each). Fetch it with `--out` into a file and query the file with `jq`. `content patch` and `content put` echo the scene's whole content back: always project their output.
- To see a drawing, render it to PNG and open the image, rather than reading element JSON.

## Gotchas

- The API is a public beta: fields and behaviour may change without a version bump. A recipe whose output no longer matches its stated shape has drifted; re-prove it.
- Errors go to stderr as `HTTP <code>: <message>` plus the API's JSON, and the exit status is 1, so a failed command leaves stdout empty and a following `jq` prints nothing. Keep `2>&1` out of that pipe: it turns the error into a `jq` parse error and hides it.
- On `HTTP 401` or `403`, run `excalidraw whoami`: it names the key's type, source and workspace. `EXCALIDRAW_API_KEY` in the shell silently overrides the saved login.
- Rate limit: 600 requests a minute per key. The CLI retries `429` and failed reads three times on its own.
