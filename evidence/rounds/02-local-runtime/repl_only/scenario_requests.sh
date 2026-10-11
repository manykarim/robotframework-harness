#!/usr/bin/env bash
set -u
HERE=$(cd "$(dirname "$0")" && pwd); D=$HERE/run/requests; PY=~/workspace/robotcode-experiments/.venv/bin/python
rm -rf "$D"; export OUTJSON=$HERE/logs/latency.jsonl
step() { local t0=$(date +%s%N); local r; r=$($PY "$HERE/rfrepl.py" step --dir "$D" "$1"); local t1=$(date +%s%N); echo "[$(( (t1-t0)/1000000 )) ms] $r" | cut -c1-700; }
s0=$(date +%s%N); $PY "$HERE/rfrepl.py" start --dir "$D" --output output.xml; s1=$(date +%s%N); echo "start wall: $(( (s1-s0)/1000000 )) ms"
step 'Import Library    RequestsLibrary'
step 'Create Session    rb    https://restful-booker.herokuapp.com'
step '&{creds}    Create Dictionary    username=admin    password=password123'
step '${resp}    POST On Session    rb    /auth    json=${creds}'
step '${token}    Set Variable    ${resp.json()}[token]'
step '&{dates}    Create Dictionary    checkin=2026-10-01    checkout=2026-10-05
&{booking}    Create Dictionary    firstname=Rf    lastname=Mcp    totalprice=${123}    depositpaid=${True}    bookingdates=${dates}    additionalneeds=Breakfast'
step '${resp}    POST On Session    rb    /booking    json=${booking}'
step '${id}    Set Variable    ${resp.json()}[bookingid]'
step '${resp}    GET On Session    rb    /booking/${id}'
step 'Should Be Equal As Strings    ${resp.json()}[firstname]    Rf'
step 'Should Be Equal As Strings    ${resp.json()}[firstname]    Wrong'
step '${r2}    GET On Session    rb    /booking/999999999    expected_status=anything'
step 'Status Should Be    404    ${r2}'
"$HERE/bench.sh" py "$D" 30 'Status Should Be    200    ${resp}' requests-status-local-py
"$HERE/bench.sh" sh "$D" 30 'Status Should Be    200    ${resp}' requests-status-local-sh
"$HERE/bench.sh" py "$D" 30 'GET On Session    rb    /booking/${id}' requests-get-network-py
$PY "$HERE/rfrepl.py" build --dir "$D" -o "$HERE/proj/requests_recorded.robot" --name "Booker Recorded" --first 13
$PY "$HERE/rfrepl.py" stop --dir "$D"
