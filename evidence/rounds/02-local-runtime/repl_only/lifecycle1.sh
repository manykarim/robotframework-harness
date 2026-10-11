#!/usr/bin/env bash
# concurrency, timeout+wait, interrupt, signals while idle, .exit inside a cell
set -u
HERE=$(cd "$(dirname "$0")" && pwd); D=$HERE/run/life1; PY=~/workspace/robotcode-experiments/.venv/bin/python
C="$PY $HERE/rfrepl.py"; rm -rf "$D"
$C start --dir "$D" >/dev/null; read -r PID _ < "$D/repl.pid"; echo "repl pid $PID"
echo "== 1. five concurrent clients, each Sleep 0.3s (lock serializes)"
t0=$(date +%s%N)
for i in 1 2 3 4 5; do ( $C step --dir "$D" --id c$i "Sleep    0.3s
Log    client $i" > "$D/c$i.out" ) & done; wait
t1=$(date +%s%N); echo "total $(( (t1-t0)/1000000 )) ms"; for i in 1 2 3 4 5; do jq -c '{id,status,ms,n:(.steps|length),log:.steps[1].args}' "$D/c$i.out"; done
echo "== 1b. five concurrent raw writers WITHOUT lock/client (atomic <PIPE_BUF writes)"
off=$(stat -c %s "$D/steps.jsonl")
for i in 1 2 3 4 5; do ( printf '# rfmcp-step: raw%s\nSleep    0.1s\nLog    raw %s\n\n# rfmcp-end: raw%s\n' $i $i $i > "$D/in.fifo" ) & done; wait; sleep 1.2
tail -c +$((off+1)) "$D/steps.jsonl" | jq -c 'select(.t=="begin" or .t=="end") | [.t,.id]' | tr '\n' ' '; echo
tail -c +$((off+1)) "$D/steps.jsonl" | jq -c 'select(.t=="step" and .name=="Log") | [.id, .args[0]]' | tr '\n' ' '; echo
echo "== 2. step longer than client timeout, then resume with wait"
$C step --dir "$D" --timeout 1 --id long1 'Sleep    3s'; echo "rc=$?"
$C step --dir "$D" --id after1 'Log    queued behind long step'; echo "rc=$?"
$C wait --dir "$D" long1; echo "rc=$?"
echo "== 3. SIGINT to the REPL pid while a keyword runs"
( $C step --dir "$D" --id int1 'Sleep    10s' > "$D/int1.out" ) & sleep 1; kill -INT "$PID"; wait; cat "$D/int1.out"; echo
$C step --dir "$D" 'Log    still alive after interrupt'
echo "== 4. SIGINT / SIGTERM while idle"
kill -INT "$PID"; sleep 0.5; echo "after idle SIGINT alive=$(kill -0 $PID 2>/dev/null && echo yes || echo no)"
$C step --dir "$D" 'Log    alive after idle SIGINT?' 
kill -TERM "$PID"; sleep 0.5; echo "after idle SIGTERM alive=$(kill -0 $PID 2>/dev/null && echo yes || echo no)"
$C step --dir "$D" 'Log    alive after idle SIGTERM?'
echo "== 5. .exit inside a cell (agent mistake)"
$C step --dir "$D" --timeout 5 '.exit'; echo "rc=$?"
sleep 0.5; echo "alive=$(kill -0 $PID 2>/dev/null && echo yes || echo no)"
$C stop --dir "$D"
tail -5 "$D/repl.log"
