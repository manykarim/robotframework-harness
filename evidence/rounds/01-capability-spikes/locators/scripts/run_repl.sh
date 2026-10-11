#!/usr/bin/env bash
# usage: scripts/run_repl.sh <name> <input-file> [extra robotcode repl args]
# Runs `robotcode repl --plain` with piped input, captures full output + wall time,
# then reaps any leftover processes started by this run (env-marker based).
set -u
HERE=$(cd "$(dirname "$0")/.." && pwd)
RC=~/workspace/robotcode-experiments/.venv/bin/robotcode
name=$1; input=$2; shift 2
out="$HERE/out/$name"; mkdir -p "$out" "$HERE/logs"
log="$HERE/logs/$name.log"
export LOCATOR_EXP_MARKER=locexp
{
  echo "# experiment: $name   date: $(date -Iseconds)"
  echo "\$ robotcode repl --plain --no-history -d out/$name $* < $input"
} > "$log"
s=$(date +%s.%N)
( cd "$HERE" && timeout -s TERM -k 15 "${TMO:-300}" "$RC" repl --plain --no-history -d "$out" "$@" < "$input" ) >> "$log" 2>&1
rc=$?
e=$(date +%s.%N)
LC_ALL=C printf '# exit=%s wall=%.2fs\n' "$rc" "$(echo "$e - $s" | bc)" >> "$log"
"$HERE/scripts/reap.sh" 2>/dev/null >> "$log"
tail -1 "$log"
