#!/usr/bin/env bash
# Approach C (v2): fresh `robotcode repl` per step; adopts a NAMED Playwright state in a shared
# standalone node process via Browser's (non-keyword) PlaywrightState.set_peer_id().
#   oneshot_step2.sh DIR NODE_PORT PEER_ID 'cell'
set -u
RC=${RC:-/home/many/workspace/robotcode-experiments/.venv/bin/robotcode}
D=$(realpath -m "$1"); PORT=$2; PEER=$3; CELL=$4
{
  printf 'Import Library    Browser    auto_closing_level=KEEP    playwright_process_port=%s    timeout=10s\n' "$PORT"
  printf '${__b}=    Get Library Instance    Browser\n'
  printf 'Call Method    ${__b._playwright_state}    set_peer_id    %s\n' "$PEER"
  [ -f "$D/state_vars.robot" ] && cat "$D/state_vars.robot"      # optional client-side variable rehydration
  printf '%s\n' "$CELL"
} | "$RC" repl --plain --no-history -d "$D" > "$D/last.txt" 2>&1
grep -v "^\s*$" "$D/last.txt"
grep -q "\[ FAIL \]" "$D/last.txt" && { echo "== FAIL"; exit 1; } || { echo "== PASS"; exit 0; }
