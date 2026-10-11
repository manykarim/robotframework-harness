#!/usr/bin/env bash
# Controlled per-step latency: N x 'Get Title' against an already logged-in saucedemo page,
# each step a separate process invocation (like separate agent shell calls).
set -u
cd "$(dirname "$0")"
RC=~/workspace/robotcode-experiments/.venv/bin/robotcode
N=${N:-30}; NC=${NC:-10}; OUT=out/latency; [ -z "${ONLY:-}" ] && rm -rf $OUT; mkdir -p $OUT
now() { date +%s%N; }
SETUP=$'New Browser  chromium  headless=True\nNew Page  https://www.saucedemo.com\nFill Text  [data-test="username"]  standard_user\nFill Text  [data-test="password"]  secret_sauce\nClick  [data-test="login-button"]'
series() { local name=$1; shift; : > $OUT/$name.ms; for i in $(seq 1 $REPS); do local t=$(now); "$@" >/dev/null 2>&1; echo $(( ($(now)-t)/1000000 )) >> $OUT/$name.ms; done; echo "$name done"; }

if [ -z "${ONLY:-}" ] || [[ $ONLY == *A* ]]; then
# ---- A: repl-server
setsid $RC repl-server --tcp 6720 -d $OUT/A </dev/null >$OUT/A.log 2>&1 &
APID=$!; echo "A pid $APID"; mkdir -p $OUT/A
until ss -ltn | grep -q ":6720 "; do sleep 0.02; done
python3 rfstep.py run --port 6720 "Import Library  Browser"$'\n'"$SETUP" | head -1
REPS=$N series A_python python3 rfstep.py run --port 6720 'Get Title'
REPS=$N series A_bash ./rfstep.sh 6720 'Get Title'
REPS=$N series A_python_log python3 rfstep.py run --port 6720 'Log  x'
python3 rfstep.py stop --port 6720; for i in $(seq 100); do kill -0 $APID 2>/dev/null || break; sleep 0.1; done; kill -0 $APID 2>/dev/null && kill -KILL -- -$APID

fi
if [ -z "${ONLY:-}" ] || [[ $ONLY == *B* ]]; then
# ---- B: FIFO repl
./fifo_repl.sh start $OUT/B >/dev/null
./fifo_repl.sh step $OUT/B "Import Library  Browser"$'\n'"$SETUP" | tail -1
REPS=$N series B_fifo ./fifo_repl.sh step $OUT/B 'Get Title'
REPS=$N series B_fifo_log ./fifo_repl.sh step $OUT/B 'Log  x'
./fifo_repl.sh stop $OUT/B >/dev/null

fi
if [ -z "${ONLY:-}" ] || [[ $ONLY == *C* ]]; then
# ---- C: one-shot repl + shared node + set_peer_id
BP=~/workspace/robotcode-experiments/.venv/lib/python3.13/site-packages
LOGABS=$PWD/$OUT/C_node.log; (cd $BP && PLAYWRIGHT_BROWSERS_PATH=0 exec node Browser/wrapper/index.js 127.0.0.1 6721 </dev/null >$LOGABS 2>&1) &
CPID=$!; for i in $(seq 200); do ss -ltn | grep -q ":6721 " && break; sleep 0.05; done; mkdir -p $OUT/C
./oneshot_step2.sh $OUT/C 6721 bench "$SETUP" | tail -1
REPS=$NC series C_oneshot ./oneshot_step2.sh $OUT/C 6721 bench 'Get Title'
REPS=$NC series C_bare_repl bash -c "printf 'Log  x\n' | $RC repl --plain --no-history -d $OUT/C"
kill -TERM $CPID; sleep 1; kill -0 $CPID 2>/dev/null && kill -KILL $CPID

fi
if [ -z "${ONLY:-}" ] || [[ $ONLY == *D* ]]; then
# ---- D: robot-debug at Breakpoint via FIFO
mkdir -p $OUT/D; cat > $OUT/D/s.robot <<'R'
*** Settings ***
Library    Browser
Library    robotcode.repl.Repl
*** Test Cases ***
T
    New Browser  chromium  headless=True
    New Page  https://www.saucedemo.com
    Fill Text  [data-test="username"]  standard_user
    Fill Text  [data-test="password"]  secret_sauce
    Click  [data-test="login-button"]
    Breakpoint
R
./debug_fifo.sh start $OUT/D $OUT/D/s.robot >/dev/null
REPS=$N series D_rdb ./debug_fifo.sh step $OUT/D 'Get Title'
./debug_fifo.sh stop $OUT/D >/dev/null

fi
stats() { sort -n $OUT/$1.ms | awk -v n="$1" '{a[NR]=$1} END {m=(NR%2)?a[(NR+1)/2]:(a[NR/2]+a[NR/2+1])/2; p=a[int(NR*0.9+0.999)]; printf "%-14s n=%-3d min=%-5d median=%-7.1f p90=%-5d max=%d\n", n, NR, a[1], m, p, a[NR]}'; }
echo "=== per-step wall time (ms), each step a separate process ==="
for s in A_python A_bash A_python_log B_fifo B_fifo_log C_oneshot C_bare_repl D_rdb; do [ -s $OUT/$s.ms ] && stats $s; done
