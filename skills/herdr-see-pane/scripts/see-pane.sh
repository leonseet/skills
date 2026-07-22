#!/usr/bin/env bash
# Print the single other pane in the caller's Herdr tab (metadata + transcript).
# No CLI args. Optional env: HERDR_SEE_PANE_LINES (default 120).
set -euo pipefail

if [[ "${HERDR_ENV:-}" != "1" ]]; then
  echo "error: not inside Herdr (HERDR_ENV is not 1)" >&2
  exit 1
fi

: "${HERDR_WORKSPACE_ID:?HERDR_WORKSPACE_ID unset}"
: "${HERDR_TAB_ID:?HERDR_TAB_ID unset}"
: "${HERDR_PANE_ID:?HERDR_PANE_ID unset}"

LINES="${HERDR_SEE_PANE_LINES:-120}"

if ! command -v herdr >/dev/null 2>&1; then
  echo "error: herdr not on PATH" >&2
  exit 1
fi
if ! command -v python3 >/dev/null 2>&1; then
  echo "error: python3 required to parse herdr JSON" >&2
  exit 1
fi

list_json="$(herdr pane list --workspace "$HERDR_WORKSPACE_ID")"
target="$(
  printf '%s\n' "$list_json" | python3 -c '
import json, sys
tab_id = sys.argv[1]
me = sys.argv[2]
data = json.load(sys.stdin)
panes = [
    p for p in data["result"]["panes"]
    if p.get("tab_id") == tab_id and p.get("pane_id") != me
]
if not panes:
    print("error: no other pane in this tab", file=sys.stderr)
    sys.exit(2)
if len(panes) > 1:
    ids = ", ".join(p["pane_id"] for p in panes)
    print(
        f"error: expected exactly one other pane in this tab, found {len(panes)}: {ids}",
        file=sys.stderr,
    )
    sys.exit(3)
print(panes[0]["pane_id"])
' "$HERDR_TAB_ID" "$HERDR_PANE_ID"
)"

get_json="$(herdr pane get "$target")"
read_out="$(herdr pane read "$target" --source recent-unwrapped --lines "$LINES")"

python3 -c '
import json, sys
me, target, lines = sys.argv[1], sys.argv[2], sys.argv[3]
pane = json.load(sys.stdin)["result"]["pane"]
agent = pane.get("agent") or "(none)"
status = pane.get("agent_status") or "(none)"
title = pane.get("terminal_title_stripped") or pane.get("terminal_title") or "(none)"
cwd = pane.get("foreground_cwd") or pane.get("cwd") or "(none)"
print("=== herdr-see-pane ===")
print(f"caller: {me}")
print(f"target: {target}")
print(f"agent: {agent}")
print(f"agent_status: {status}")
print(f"title: {title}")
print(f"cwd: {cwd}")
print(f"lines: {lines} (recent-unwrapped)")
print()
print("=== metadata (pane get) ===")
json.dump({"result": {"pane": pane}}, sys.stdout, indent=2)
print()
' "$HERDR_PANE_ID" "$target" "$LINES" <<<"$get_json"

printf '\n=== transcript (recent-unwrapped) ===\n%s\n' "$read_out"
