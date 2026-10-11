#!/usr/bin/env bash
# Kill ONLY processes started by these experiments: they carry LOCATOR_EXP_MARKER=locexp
# in their environment (inherited by robotcode -> python -> playwright node -> chromium).
self=$$
found=0
for d in /proc/[0-9]*; do
  [ -O "$d" ] || continue
  pid=${d#/proc/}
  [ "$pid" = "$self" ] && continue
  [ "$pid" = "$PPID" ] && continue
  if tr '\0' '\n' < "$d/environ" 2>/dev/null | grep -qx 'LOCATOR_EXP_MARKER=locexp'; then
    cmd=$(tr '\0' ' ' < "$d/cmdline" 2>/dev/null | cut -c1-120)
    case "$cmd" in *reap.sh*|*run_repl.sh*|bash*|"") continue;; esac
    echo "[reap] killing $pid: $cmd"
    kill "$pid" 2>/dev/null; found=1
  fi
done
[ $found = 1 ] && sleep 1 && for d in /proc/[0-9]*; do [ -O "$d" ] || continue; pid=${d#/proc/}; tr '\0' '\n' < "$d/environ" 2>/dev/null | grep -qx 'LOCATOR_EXP_MARKER=locexp' || continue; cmd=$(tr '\0' ' ' < "$d/cmdline" 2>/dev/null); case "$cmd" in *reap.sh*|*run_repl.sh*|bash*|"") continue;; esac; kill -9 "$pid" 2>/dev/null && echo "[reap] SIGKILL $pid"; done
exit 0
