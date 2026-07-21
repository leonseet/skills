#!/usr/bin/env bash
# Summarize sandcastle run logs into per-run metrics + a cross-run friction
# tally. Deterministic so the skill doesn't re-derive parsing each time.
#
# Usage: scan-logs.sh [LOG_DIR]   (default: .sandcastle/logs, recursive)
#        scan-logs.sh --archive   (also include any archive/ subtree)
set -euo pipefail

dir="${1:-.sandcastle/logs}"
shopt -s nullglob globstar
if [[ "${1:-}" == "--archive" ]]; then
  dir=".sandcastle/logs"
fi
# The loop writes one dir per bead, named with the FULL issue id, holding
# role-named logs (e.g. logs/agentic-reid-poc-g8a.2/implementer-c1.log,
# logs/agentic-reid-poc-3a8/merger-c1.log). Older runs wrote flat
# logs/sandcastle-*.log. Match both layouts (** covers any archive/ subtree).
files=( "$dir"/*.log "$dir"/**/*.log )
[[ ${#files[@]} -gt 0 ]] || { echo "no logs in $dir"; exit 0; }

# Primary prioritisation signal is LOG LENGTH (lines), not the reported context
# window — the context-window number these runs print is unreliable. A longer log
# means more turns / more exploration / more thrash, which is what we want to fix.

# friction accumulators
bd_friction=0; timeouts=0; warns=0; retries=0; backup_warn=0; reread=0; env_churn=0
rows=()   # each: "<lines>\t<formatted table row>" — sorted by <lines> desc below
beads=()  # bead ids, derived from the per-bead parent dir of each log

for f in "${files[@]}"; do
  base="$(basename "$f")"
  parent="$(basename "$(dirname "$f")")"
  # Role is the basename prefix in the nested layout; reviewer wins over
  # implementer because reviewer logs are named implementer-reviewer-*.
  role=other
  case "$base" in
    *reviewer*)    role=review ;;
    implementer-*|*-implementer-*) role=impl ;;
    merger-*|*-merger-*) role=merge ;;
    committer-*|*-committer-*) role=commit ;;
  esac

  lines="$(wc -l < "$f" | tr -d ' ')"
  iters="$(grep -oE 'Iteration [0-9]+/[0-9]+' "$f" | tail -1 | grep -oE '[0-9]+/[0-9]+' || true)"
  maxed=no;  grep -q 'Reached max iterations' "$f" && maxed=YES
  done=no;   grep -qE '<promise>COMPLETE</promise>|signaled completion|<review>|<merge>' "$f" && done=yes
  # A run that emitted a parseable verdict (reviewer <review>, merger <merge>)
  # completed its single pass by design; "Reached max iterations (1)" on such a
  # run is not a real stall, so don't flag it as maxed.
  [[ "$done" == yes ]] && maxed=no

  # Display: "<bead>/<file>" for the nested layout, bare name for flat logs.
  # The folder is the full issue id; strip the prefix for the display column
  # only, but keep the full id for the bead list ('bd show <id>').
  short="${base#sandcastle-}"; short="${short%.log}"
  short="${short//agentic-reid-poc-/}"
  if [[ "$parent" != "logs" && "$parent" != "archive" ]]; then
    short="${parent#agentic-reid-poc-}/$short"
    beads+=("$parent")
  fi
  row="$(printf '%-44.44s %-6s %-7s %-7s %-6s %-5s' "$short" "$role" "$lines" "${iters:-?}" "$maxed" "$done")"
  rows+=("${lines}	${row}")

  # --- friction signals (recurring = systemic, fixable upstream) ---
  bd_friction=$(( bd_friction + $(grep -ciE '\-\-thread|command shape|supported way|not supported|uses .*--comments|--help' "$f" || true) ))
  timeouts=$(( timeouts + $(grep -ciE 'idle timeout|timed out|timeout [0-9]' "$f" || true) ))
  warns=$(( warns + $(grep -cE '⚠|[Ww]arning' "$f" || true) ))
  retries=$(( retries + $(grep -cE '↺|[Rr]etry|re-run' "$f" || true) ))
  backup_warn=$(( backup_warn + $(grep -ciE 'backup warning|\.beads .*permission' "$f" || true) ))
  reread=$(( reread + $(grep -ciE "sed -n .*SKILL\.md|sed -n .*CONTEXT\.md|sed -n .*\.md.* (do-work|tdd)" "$f" || true) ))
  # toolchain/env churn: interpreter & GPU/runtime pin thrash, re-locks, re-syncs,
  # missing native libs. This is what dominated the g8a.2 runs (Python 3.14 vs
  # 3.12, onnxruntime-gpu / CUDA). A high count means the sandbox env isn't pinned.
  env_churn=$(( env_churn + $(grep -ciE 'libcudart|onnxruntime|--python [0-9]|3\.1[0-9]|uv (lock|sync|add)|get_available_providers' "$f" || true) ))
done

# Longest logs first — that's the prioritisation order for "read the worst offenders".
printf '%-44s %-6s %-7s %-7s %-6s %-5s\n' RUN ROLE LINES ITERS MAXED DONE
printf '%.0s-' {1..79}; printf '\n'
printf '%s\n' "${rows[@]}" | sort -t$'\t' -k1,1 -nr | cut -f2-

echo
echo "Cross-run friction tally (recurring counts -> fix upstream, not per-run):"
printf '  bd CLI command-shape friction  : %s\n' "$bd_friction"
printf '  toolchain/env churn (py/cuda)  : %s\n' "$env_churn"
printf '  timeouts / long bounded waits  : %s\n' "$timeouts"
printf '  warnings emitted               : %s\n' "$warns"
printf '  retries / re-runs              : %s\n' "$retries"
printf '  beads backup/permission warns  : %s\n' "$backup_warn"
printf '  skill/context re-reads         : %s\n' "$reread"
echo
echo "Bead ids referenced (for 'bd show <id>' context):"
{ printf '%s\n' "${beads[@]:-}"; printf '%s\n' "${files[@]##*/}" | grep -oE 'agentic-reid-poc-[a-z0-9]+(\.[0-9]+)?'; } \
  | grep -E 'agentic-reid-poc-' | sort -u | sed 's/^/  /'
