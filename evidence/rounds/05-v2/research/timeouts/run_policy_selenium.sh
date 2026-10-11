#!/usr/bin/env bash
# Measures the REPL short-timeout + re-check policy (SeleniumLibrary).
cd "$(dirname "$0")"
RC=~/workspace/rf-mcp-robotcode/.venv/bin/robotcode
SITE=http://127.0.0.1:8765
SETTLE=${1:-10s}
export RFH_RECHECK_LOG=$PWD/logs/policy_selenium_${SETTLE}.jsonl; rm -f "$RFH_RECHECK_LOG"
run() {
  local name=$1; shift
  local t0=$(date +%s.%N)
  printf '%s\n' "Library    SeleniumLibrary    run_on_failure=Nothing" "Open Browser    $SITE/index.html    headlesschrome" "$@" "Close All Browsers" ".exit" | \
    ROBOT_OPTIONS="--listener $PWD/rfh_repl_timeouts.py:2s:$SETTLE" timeout 120 $RC repl --plain --no-history -d out/repl > logs/policy_sel_${SETTLE}_$name.log 2>&1
  local t1=$(date +%s.%N)
  echo "== $name ($(echo "$t1-$t0"|bc) s)"; grep -E "^\[rfh\]|FAIL|STEP_ELAPSED" logs/policy_sel_${SETTLE}_$name.log | cut -c1-300
}
T='${t0}    Evaluate    time.time()'
E='Log To Console    STEP_ELAPSED=${{ round(time.time()-$t0, 2) }}'
run S1_slow4s_right_after "Go To    $SITE/async.html" "$T" "Click Element    id:a4000" "$E"
run S2_missing_right_after "Go To    $SITE/index.html" "$T" "Click Element    css:#nope" "$E"
run S3_missing_settled "Go To    $SITE/index.html" "Sleep    10s" "$T" "Click Element    css:#nope" "$E"
run S4_wuev_slow4s "Go To    $SITE/async.html" "$T" "Wait Until Element Is Visible    id:a4000" "$E"
run S5_wuev_missing_settled "Sleep    10s" "$T" "Wait Until Element Is Visible    css:#nope" "$E"
run S7_iframe "Go To    $SITE/frames.html" "Sleep    10s" "$T" "Input Text    id:card    4111" "$E"
