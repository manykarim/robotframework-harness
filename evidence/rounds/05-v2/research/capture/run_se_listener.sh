#!/bin/bash
cd "$(dirname "$0")"
SV=~/workspace/rf-mcp-robotcode/.venv/bin; SITE=file://$(cd ../site && pwd); st=$(pwd)/.rf/state_se_l; mkdir -p out_sel logs
for mode in off on; do
if [ $mode = on ]; then export ROBOT_OPTIONS="--listener $(pwd)/rfcapture_listener.py:$st"; else unset ROBOT_OPTIONS; fi
t0=$(date +%s.%N)
setsid -w $SV/robotcode repl --plain --no-history -d out_sel > logs/se_listener_$mode.log 2>&1 <<RF
Library    SeleniumLibrary    timeout=2s
Open Browser    $SITE/index.html    headlesschrome
Click Element    id=cookie-ok
Click Link    id=to-form
Input Text    id=name    Ada
Select From List By Value    id=country    de
Click Button    id=submit
Element Text Should Be    id=out    Thanks Ada
Go To    $SITE/frames.html
Click Button    id=pay-btn
Select Frame    id=pay
Click Button    id=pay-btn
Unselect Frame
Close All Browsers
.exit
RF
t1=$(date +%s.%N); echo "$mode wall=$(echo "$t1 - $t0"|bc) stdout=$(wc -c < logs/se_listener_$mode.log) fails=$(grep -c '\[ FAIL \]' logs/se_listener_$mode.log)"
done
