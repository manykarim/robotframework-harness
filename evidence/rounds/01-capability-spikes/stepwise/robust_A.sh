#!/usr/bin/env bash
# Approach A robustness probes: concurrency, client disconnect, interrupt, idle interrupt
set -u
cd "$(dirname "$0")"
RC=~/workspace/robotcode-experiments/.venv/bin/robotcode
PORT=6704; OUT=out/A_robust; rm -rf $OUT; mkdir -p $OUT
now() { date +%s%N; }
setsid nohup $RC repl-server --tcp $PORT -d $OUT </dev/null >$OUT/server.log 2>&1 &
SPID=$!; echo $SPID > $OUT/server.pid; until ss -ltn | grep -q ":$PORT "; do sleep 0.02; done
R="python3 rfstep.py run --port $PORT"
echo "### 1. concurrent clients on one server (c1 Sleep 3s, c2 starts +0.5s)"
t=$(now); ( $R $'Sleep  3s\nLog  c1-done' > $OUT/c1.txt; echo "c1 rc=$? ms=$(( ($(now)-t)/1000000 ))" ) &
C1=$!
sleep 0.5; t2=$(now); $R 'Log  c2-done' > $OUT/c2.txt; echo "c2 rc=$? ms=$(( ($(now)-t2)/1000000 )) (started 500ms after c1)"; wait $C1
cat $OUT/c1.txt $OUT/c2.txt
echo "### 2. client disconnect mid-step (client timeout 1s during Sleep 4s)"
t=$(now); python3 rfstep.py run --port $PORT --timeout 1 $'Sleep  4s\n${after_disc}=  Set Variable  ran-after-disconnect'; echo "client rc=$? ms=$(( ($(now)-t)/1000000 ))"
t=$(now); $R 'Log  next-call ${after_disc}'; echo "next rc=$? ms=$(( ($(now)-t)/1000000 ))"
echo "### 3. interrupt RPC while a step runs (Sleep 30s, interrupt after 1s)"
t=$(now); ( $R 'Sleep  30s' > $OUT/int.txt; echo "sleeper rc=$? ms=$(( ($(now)-t)/1000000 ))" ) &
C3=$!
sleep 1; python3 raw_probe.py $PORT interrupt 2>&1 | tr -d '\n'; echo; wait $C3; cat $OUT/int.txt
t=$(now); $R 'Log  alive-after-interrupt'; echo "rc=$? ms=$(( ($(now)-t)/1000000 ))"
echo "### 4. interrupt RPC while idle"
python3 raw_probe.py $PORT interrupt 2>&1 | tr -d '\n'; echo; sleep 1
kill -0 $SPID 2>/dev/null && echo "server alive after idle interrupt" || echo "server DIED after idle interrupt"
$R 'Log  alive-after-idle-interrupt'; echo "rc=$?"
echo "### server log (filtered)"; grep -v "UserWarning\|warnings.warn" $OUT/server.log | tail -15
kill -0 $SPID 2>/dev/null && { python3 rfstep.py stop --port $PORT; sleep 1; }
kill -0 $SPID 2>/dev/null && echo "server still alive -> kill pgid" && kill -- -$SPID
