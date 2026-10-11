#!/usr/bin/env bash
# Approach D: `robotcode robot-debug --plain` paused at a `Breakpoint`, stdin from a FIFO (+keeper).
#   debug_fifo.sh start DIR SUITE | step DIR 'keyword line or .dotcmd' | stop DIR
set -u
RC=${RC:-/home/many/workspace/robotcode-experiments/.venv/bin/robotcode}
cmd=$1; D=$(realpath -m "$2"); FIFO=$D/in.fifo; LOG=$D/debug.log; STEPS=$D/steps.count
case $cmd in
start)
  rm -f "$FIFO"; mkfifo "$FIFO"; echo 0 > "$STEPS"; : > "$LOG"
  setsid bash -c "exec sleep infinity > '$FIFO'" </dev/null >/dev/null 2>&1 & echo $! > "$D/keeper.pid"
  PYTHONUNBUFFERED=1 setsid "$RC" robot-debug --plain --no-history -d "$D" "$3" < "$FIFO" >> "$LOG" 2>&1 & echo $! > "$D/dbg.pid"
  until grep -q "(rdb)\|breakpoint\|Breakpoint" "$LOG"; do sleep 0.05; done; echo "paused"
  ;;
step)
  n=$(( $(cat "$STEPS") + 1 )); echo $n > "$STEPS"; off=$(stat -c %s "$LOG")
  printf '%s\nLog To Console    __STEP_DONE_%d__\n' "$3" "$n" > "$FIFO"
  until tail -c +$((off + 1)) "$LOG" | grep -q "__STEP_DONE_${n}__$"; do sleep 0.02; done
  tail -c +$((off + 1)) "$LOG" | sed "/__STEP_DONE_${n}__/,\$d"; echo
  ;;
stop)
  printf '.continue\n' > "$FIFO"; for _ in $(seq 1 100); do kill -0 "$(cat "$D/dbg.pid")" 2>/dev/null || break; sleep 0.1; done
  kill "$(cat "$D/keeper.pid")" 2>/dev/null; kill -0 "$(cat "$D/dbg.pid")" 2>/dev/null && kill -KILL -- -"$(cat "$D/dbg.pid")"; rm -f "$FIFO"; tail -5 "$LOG"
  ;;
esac
