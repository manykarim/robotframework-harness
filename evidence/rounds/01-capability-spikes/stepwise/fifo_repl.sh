#!/usr/bin/env bash
# Approach B: `robotcode repl --plain` as a background process fed by a named pipe (FIFO).
# Each agent shell call runs one subcommand; all state lives in the background REPL.
#
#   fifo_repl.sh start DIR            # start REPL (+ fifo keeper) with output dir DIR
#   fifo_repl.sh step  DIR 'cell'     # send one cell, wait for its sentinel, print its output
#   fifo_repl.sh stop  DIR            # .exit and clean up
#
# Status detection: FAIL if the cell's output segment contains "[ FAIL ]", else PASS.
# Exit codes: 0 PASS, 1 FAIL, 4 timeout waiting for the sentinel, 3 not running.
set -u
RC=${RC:-/home/many/workspace/robotcode-experiments/.venv/bin/robotcode}
cmd=$1; D=$(realpath -m "$2"); FIFO=$D/in.fifo; LOG=$D/repl.log; STEPS=$D/steps.count
TIMEOUT_S=${STEP_TIMEOUT:-120}

case $cmd in
start)
  mkdir -p "$D"; rm -f "$FIFO" "$LOG"; mkfifo "$FIFO"; echo 0 > "$STEPS"; : > "$LOG"
  # keeper holds the write end open so the REPL never sees EOF between steps
  setsid bash -c "exec sleep infinity > '$FIFO'" </dev/null >/dev/null 2>&1 &
  echo $! > "$D/keeper.pid"
  PYTHONUNBUFFERED=1 setsid "$RC" ${RC_GLOBAL_OPTS:--v} repl --plain --no-history -d "$D" < "$FIFO" >> "$LOG" 2>&1 &
  echo $! > "$D/repl.pid"
  echo "started repl pid=$(cat "$D/repl.pid") keeper pid=$(cat "$D/keeper.pid")"
  ;;
step)
  kill -0 "$(cat "$D/repl.pid" 2>/dev/null)" 2>/dev/null || { echo "!! repl not running"; exit 3; }
  n=$(( $(cat "$STEPS") + 1 )); echo $n > "$STEPS"
  off=$(stat -c %s "$LOG")
  # cell, two blank lines (terminates any unfinished block), sentinel, blank line
  printf '%s\n\n\nLog To Console    __STEP_DONE_%d__\n\n' "$3" "$n" > "$FIFO"
  deadline=$(( $(date +%s) + TIMEOUT_S ))
  until tail -c +$((off + 1)) "$LOG" | grep -qx "__STEP_DONE_${n}__"; do
    [ "$(date +%s)" -ge "$deadline" ] && { echo "!! timeout waiting for step $n"; exit 4; }
    sleep 0.02
  done
  # print the segment for this cell, without the sentinel's own noise
  seg=$(tail -c +$((off + 1)) "$LOG" | sed "/__STEP_DONE_${n}__/,\$d")
  printf '%s\n' "$seg" | grep -v "Log To Console  __STEP_DONE_\|^\s*$"
  if grep -q "\[ FAIL \]" <<<"$seg"; then echo "== FAIL"; exit 1; else echo "== PASS"; exit 0; fi
  ;;
stop)
  if kill -0 "$(cat "$D/repl.pid" 2>/dev/null)" 2>/dev/null; then
    printf '.exit\n' > "$FIFO"
    for _ in $(seq 1 100); do kill -0 "$(cat "$D/repl.pid")" 2>/dev/null || break; sleep 0.1; done
  fi
  kill "$(cat "$D/keeper.pid")" 2>/dev/null
  kill -0 "$(cat "$D/repl.pid")" 2>/dev/null && { echo "repl still alive -> SIGKILL group"; kill -KILL -- -"$(cat "$D/repl.pid")"; }
  rm -f "$FIFO"; echo "stopped"
  ;;
esac
