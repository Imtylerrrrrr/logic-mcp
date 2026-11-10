#!/bin/sh
# Collect bundle tables for several plug-ins in a row (test project only, never save it).
# Usage: scripts/calibrate_batch.sh [strip] "Name 1" "Name 2" ...   — logs go to ~/.logic-mcp/calib-logs/<name>.log
# Already-bundled names are skipped; a failed plug-in is logged and the loop continues.
set -u
cd "$(dirname "$0")/.."
strip=1; case "${1:-}" in ''|*[!0-9]*) ;; *) strip=$1; shift;; esac
logdir="$HOME/.logic-mcp/calib-logs"; mkdir -p "$logdir"
for name in "$@"; do
  if uv run python -c "import json,sys; sys.exit(0 if sys.argv[1] in json.load(open('src/logic_mcp/logic/plugins/known.json'))['params'] else 1)" "$name"; then
    echo "skip (bundled): $name"; continue
  fi
  log="$logdir/$(printf '%s' "$name" | tr ' /' '__').log"
  start=$(date +%s)
  uv run python scripts/calibrate_plugin.py "$name" "$strip" --write --yes >"$log" 2>&1
  rc=$?
  printf '%s rc=%s %ss %s\n' "$name" "$rc" "$(( $(date +%s) - start ))" "$(grep -m1 '^calibrate:' "$log" | cut -c1-80)"
done
