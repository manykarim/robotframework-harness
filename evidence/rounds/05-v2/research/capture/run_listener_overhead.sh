#!/bin/bash
# Same 12-step Browser journey with / without the capture listener; per-step wall from timestamps; stdout bytes.
cd "$(dirname "$0")"
export PLAYWRIGHT_BROWSERS_PATH=~/.cache/ms-playwright
BV=~/workspace/robotcode-experiments/.venv/bin
SITE=file://$(cd ../site && pwd)
steps() {
cat <<RF
Library    Browser    timeout=2s
New Browser    chromium    headless=True
New Page    $SITE/index.html
Click    id=cookie-ok
Click    id=to-form
Fill Text    id=name    Ada
Check Checkbox    id=agree    force=True
Select Options By    id=country    value    de
Click    id=submit
Get Text    id=out    ==    Thanks Ada
Go To    $SITE/frames.html
Fill Text    id=pay >>> id=card    4111
Click    id=pay-btn
Go To    file://$(pwd)/big.html
Click    id=add-3
.exit
RF
}
for mode in off on off on off on; do
  st=$(pwd)/.rf/state_l_$mode; rm -rf "$st"; mkdir -p out_l
  if [ $mode = on ]; then export ROBOT_OPTIONS="--listener $(pwd)/rfcapture_listener.py:$st"; else unset ROBOT_OPTIONS; fi
  t0=$(date +%s.%N)
  steps | setsid $BV/robotcode repl --plain --no-history -d out_l > logs/listener_$mode.log 2>&1
  t1=$(date +%s.%N)
  echo "{\"mode\":\"$mode\",\"wall_s\":$(echo "$t1 - $t0" | bc),\"stdout_bytes\":$(wc -c < logs/listener_$mode.log),\"fails\":$(grep -c '\[ FAIL \]' logs/listener_$mode.log)}" >> listener_overhead.jsonl
done
