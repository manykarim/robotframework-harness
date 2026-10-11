#!/bin/bash
# Measures capture costs for Browser 20.5 on local pages (n=6 each) via a robotcode repl session.
set -u
cd "$(dirname "$0")"
export PLAYWRIGHT_BROWSERS_PATH=~/.cache/ms-playwright
BV=~/workspace/robotcode-experiments/.venv/bin
SITE=file://$(cd ../site && pwd)
HERE=file://$(pwd)
mkdir -p out .rf/state
rm -f costs_browser.jsonl
setsid $BV/robotcode repl --plain --no-history -d out <<RF > logs_browser_costs.log 2>&1
Library    Browser    timeout=5s
Library    $(pwd)/rfcapture.py    state_dir=$(pwd)/.rf/state
New Browser    chromium    headless=True
New Page    $SITE/index.html
Measure Capture Costs    index    6    $(pwd)/costs_browser.jsonl
Go To    $SITE/form.html
Measure Capture Costs    form    6    $(pwd)/costs_browser.jsonl
Go To    $SITE/frames.html
Measure Capture Costs    frames    6    $(pwd)/costs_browser.jsonl
Go To    $HERE/big.html
Measure Capture Costs    big    6    $(pwd)/costs_browser.jsonl
.exit
RF
echo "exit=$?"
