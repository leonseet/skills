---
name: herdr-see-pane
description: Show the other pane in the current Herdr tab (metadata + transcript).
disable-model-invocation: true
---

# Herdr See Pane

No arguments. Run when you open a sibling agent and need the other pane's context.

## Steps

1. If `HERDR_ENV` is not `1`, say you are not inside Herdr and stop.
2. Run exactly this command — do not invent your own `herdr` sequence:

```bash
bash "$HOME/.agents/skills/herdr-see-pane/scripts/see-pane.sh"
```

3. From the script output, tell the user: target pane id, agent + status, title, and a short summary of what that pane is doing or waiting on.

Done when the script has run and that summary is delivered.

## Rules

- Expects exactly one other pane in the current tab. If the script errors (0 or 2+ siblings), report the error and stop.
- Do not focus, rename, close, or send input to the other pane.
- Optional: `HERDR_SEE_PANE_LINES=N` before the script (default 120).
