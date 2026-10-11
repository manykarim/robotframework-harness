#!/usr/bin/env bash
# Approach A: repl-server + one-shot client, RequestsLibrary flow on restful-booker
set -u
cd "$(dirname "$0")"
RC=~/workspace/robotcode-experiments/.venv/bin/robotcode
PORT=${PORT:-6703}; OUT=out/A_requests; J=$OUT/journal.jsonl
rm -rf "$OUT"; mkdir -p "$OUT"
now() { date +%s%N; }
T0=$(now)
setsid nohup $RC repl-server --tcp $PORT -d "$OUT" </dev/null >"$OUT/server.log" 2>&1 &
SPID=$!; echo "$SPID" > "$OUT/server.pid"
until ss -ltn | grep -q ":$PORT "; do sleep 0.02; done
echo "server pid=$SPID listening_ms=$(( ($(now)-T0)/1000000 ))"
step() { local t=$(now); python3 rfstep.py run --port $PORT --journal "$J" --test "Booker Create And Get" "$1"; echo "   -> rc=$? wall_ms=$(( ($(now)-t)/1000000 ))"; }
step 'Import Library  RequestsLibrary'
step 'Import Library  Collections'
step 'Create Session  booker  https://restful-booker.herokuapp.com  headers={"Accept": "application/json"}'
step $'${auth}=  Create Dictionary  username=admin  password=password123\n${resp}=  POST On Session  booker  /auth  json=${auth}\n${token}=  Set Variable  ${resp.json()}[token]'
step $'${dates}=  Create Dictionary  checkin=2026-10-01  checkout=2026-10-05\n${body}=  Create Dictionary  firstname=Robo  lastname=Step  totalprice=${123}  depositpaid=${True}  bookingdates=${dates}  additionalneeds=Breakfast'
step '${resp}=  POST On Session  booker  /booking  json=${body}'
step '${id}=  Set Variable  ${resp.json()}[bookingid]'
step '${resp}=  GET On Session  booker  /booking/${id}'
step 'Should Be Equal  ${resp.json()}[firstname]  Robo'
step 'Dictionary Should Contain Key  ${resp.json()}  bookingdates'
step 'GET On Session  booker  /booking/999999999'                      # intentional failure (404)
step 'Should Be Equal As Integers  ${resp.status_code}  201'           # intentional failure
step $'${h}=  Create Dictionary  Cookie=token=${token}\nDELETE On Session  booker  /booking/${id}  headers=${h}  expected_status=201'
echo "total_ms=$(( ($(now)-T0)/1000000 ))"
python3 rfstep.py build --journal "$J" > "$OUT/recorded.robot"
python3 rfstep.py stop --port $PORT
T1=$(now); while kill -0 $SPID 2>/dev/null; do sleep 0.05; done; echo "server exit_ms_after_shutdown=$(( ($(now)-T1)/1000000 ))"
mkdir -p "$OUT/suite_run"; $RC robot -d "$OUT/suite_run" "$OUT/recorded.robot" | grep -E "PASS|FAIL" | tail -3
