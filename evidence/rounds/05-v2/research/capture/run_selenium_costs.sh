#!/bin/bash
# Measures capture costs for SeleniumLibrary 6.8 (headless Chrome) on local pages via a robotcode repl session.
cd "$(dirname "$0")"
SV=~/workspace/rf-mcp-robotcode/.venv/bin
SITE=file://$(cd ../site && pwd)
mkdir -p out_se
rm -f costs_selenium.jsonl
setsid $SV/robotcode repl --plain --no-history -d out_se <<RF > logs_selenium_costs.log 2>&1
Library    SeleniumLibrary    timeout=5s
Library    $(pwd)/rfcapture.py    state_dir=$(pwd)/.rf/state_se
Open Browser    $SITE/index.html    headlesschrome
Set Window Size    1280    720
Measure Capture Costs    index    6    $(pwd)/costs_selenium.jsonl
Go To    $SITE/form.html
Measure Capture Costs    form    6    $(pwd)/costs_selenium.jsonl
Go To    $SITE/frames.html
Measure Capture Costs    frames    6    $(pwd)/costs_selenium.jsonl
Go To    file://$(pwd)/big.html
Measure Capture Costs    big    6    $(pwd)/costs_selenium.jsonl
Close All Browsers
.exit
RF
