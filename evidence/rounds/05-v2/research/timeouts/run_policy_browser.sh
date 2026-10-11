#!/usr/bin/env bash
# Measures the REPL short-timeout + re-check policy (Browser) for several scenarios.
cd "$(dirname "$0")"
export PLAYWRIGHT_BROWSERS_PATH=~/.cache/ms-playwright
RC=~/workspace/robotcode-experiments/.venv/bin/robotcode
SITE=http://127.0.0.1:8765
SETTLE=${1:-10s}
export RFH_RECHECK_LOG=$PWD/logs/policy_browser_${SETTLE}.jsonl; rm -f "$RFH_RECHECK_LOG"
run() { # name, lines...
  local name=$1; shift
  local t0=$(date +%s.%N)
  printf '%s\n' "Library    Browser" "New Browser    chromium    headless=True" "$@" ".exit" | \
    ROBOT_OPTIONS="--listener $PWD/rfh_repl_timeouts.py:2s:$SETTLE" timeout 120 $RC repl --plain --no-history -d out/repl > logs/policy_${SETTLE}_$name.log 2>&1
  local t1=$(date +%s.%N)
  echo "{\"scenario\":\"$name\",\"settle\":\"$SETTLE\",\"repl_wall\":$(echo "$t1-$t0"|bc)}" >> logs/policy_browser_walls.jsonl
  echo "== $name ($(echo "$t1-$t0"|bc) s)"; grep -E "^\[rfh\]|FAIL|STEP_ELAPSED" logs/policy_${SETTLE}_$name.log | cut -c1-260
}
T='${t0}    Evaluate    time.time()'
E='Log To Console    STEP_ELAPSED=${{ round(time.time()-$t0, 2) }}'
run baseline_newpage_only "New Page    $SITE/index.html"
run S1_slow4s_right_after "New Page    $SITE/async.html" "$T" "Click    id=a4000" "$E"
run S2_missing_right_after "New Page    $SITE/index.html" "$T" "Click    css=#nope" "$E"
run S3_missing_settled "New Page    $SITE/index.html" "Sleep    10s" "$T" "Click    css=#nope" "$E"
run S4_fast1500 "New Page    $SITE/async.html" "$T" "Click    id=a1500" "$E"
run S5_slow8s_right_after "New Page    $SITE/async.html" "$T" "Click    id=a8000" "$E"
run S6_missing_after_click "New Page    $SITE/index.html" "Sleep    10s" "Click    id=cookie-ok" "$T" "Get Text    css=#nope" "$E"
run S7_iframe_unpierced "New Page    $SITE/frames.html" "Sleep    3s" "$T" "Fill Text    id=card    4111" "$E"
