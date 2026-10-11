#!/usr/bin/env bash
# Browser lifecycle: keeper death, SIGKILL of the REPL pid only, SIGKILL of the group
set -u
HERE=$(cd "$(dirname "$0")" && pwd); PY=~/workspace/robotcode-experiments/.venv/bin/python; C="$PY $HERE/rfrepl.py"
# descendants of a pid (snapshot while the tree is intact)
desc() { local all=$1 frontier=$1 next; while [ -n "$frontier" ]; do next=$(ps -eo pid=,ppid= | awk -v f=" $frontier " 'index(f," "$2" ")>0{print $1}' | tr '\n' ' '); all="$all $next"; frontier=$(echo $next); done; echo $all; }
alive() { local out=""; for p in $1; do kill -0 "$p" 2>/dev/null && out="$out $p/$(ps -o comm= -p $p)"; done; echo "[${out# }]"; }
open_browser() { $C step --dir "$1" 'Import Library    Browser' >/dev/null; $C step --dir "$1" 'New Browser    chromium    headless=${HEADLESS}' >/dev/null; $C step --dir "$1" 'New Page    https://www.saucedemo.com' | jq -c '{id,status}'; }
echo "== A. keeper mode, kill the keeper (EOF on stdin)"
D=$HERE/run/lifeA; rm -rf "$D"; $C start --dir "$D" --mode keeper --output output.xml; read -r PID KEEPER < "$D/repl.pid"; open_browser "$D"
T=$(desc $PID); echo "tree: $(alive "$T")"; echo "pgids: $(ps -o pgid= -p $(echo $T | tr ' ' ',') | sort -u | tr '\n' ' ')"
t0=$(date +%s%N); kill "$KEEPER"; while kill -0 "$PID" 2>/dev/null; do sleep 0.05; done; t1=$(date +%s%N)
echo "REPL exited $(( (t1-t0)/1000000 )) ms after keeper death"; sleep 1; echo "left: $(alive "$T")"; ls "$D/out"; tail -2 "$D/steps.jsonl" | cut -c1-120
echo "== B. rdwr mode, SIGKILL the REPL pid only"
D=$HERE/run/lifeB; rm -rf "$D"; $C start --dir "$D" >/dev/null; read -r PID _ < "$D/repl.pid"; open_browser "$D"
T=$(desc $PID); echo "tree: $(alive "$T")"
kill -KILL "$PID"; sleep 1.5; echo "left after kill pid: $(alive "$T")"
$C step --dir "$D" --timeout 3 'Log    anyone?' ; echo "rc=$?"
echo "cleanup: killpg $PID"; kill -KILL -- -"$PID" 2>/dev/null; sleep 1.5; echo "left after killpg: $(alive "$T")"
echo "== C. rdwr mode, SIGKILL the whole group (REPL + node); chromium has its own pgid"
D=$HERE/run/lifeC; rm -rf "$D"; $C start --dir "$D" >/dev/null; read -r PID _ < "$D/repl.pid"; open_browser "$D"
T=$(desc $PID); kill -KILL -- -"$PID"; sleep 1.5; echo "left after killpg: $(alive "$T")"
echo "== D. .exit timing with Browser and 2 pages open"
D=$HERE/run/lifeD; rm -rf "$D"; $C start --dir "$D" --output output.xml >/dev/null; read -r PID _ < "$D/repl.pid"; open_browser "$D"; $C step --dir "$D" 'New Page    https://www.saucedemo.com' | jq -c '{status}'
T=$(desc $PID); $C stop --dir "$D"; sleep 1; echo "left: $(alive "$T")"; ls "$D/out"
