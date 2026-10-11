#!/bin/bash
# Probe: aria depth, mode=ai output format, aria-ref selectors, shadow/iframe coverage, screenshot size options.
cd "$(dirname "$0")"
export PLAYWRIGHT_BROWSERS_PATH=~/.cache/ms-playwright
BV=~/workspace/robotcode-experiments/.venv/bin
SITE=file://$(cd ../site && pwd)
mkdir -p out
setsid $BV/robotcode repl --plain --no-history -d out <<RF > logs_aria_probe.log 2>&1
Library    Browser    timeout=3s
New Browser    chromium    headless=True
New Page    $SITE/frames.html
\${a}    Get Aria Snapshot    css=body    mode=ai
Log To Console    ---AI---\n\${a}\n---END---
\${d}    Get Aria Snapshot    css=body
Log To Console    ---DEFAULT---\n\${d}\n---END---
\${src}    Get Page Source
Log To Console    ---SRC---\n\${src}\n---END---
Click    aria-ref=e5
Get Text    aria-ref=e3
Fill Text    aria-ref=e8    4111
Get Property    id=pay >>> id=card    value
Go To    $(pwd)/big.html
\${d1}    Get Aria Snapshot    css=body    depth=1
Log To Console    ---DEPTH1 len---\n\${{len(\$d1)}}\n\${{\$d1[:300]}}
\${d2}    Get Aria Snapshot    css=body    depth=2
Log To Console    ---DEPTH2 len---\n\${{len(\$d2)}}
\${d3}    Get Aria Snapshot    css=main    depth=2
Log To Console    ---MAIN DEPTH2 len---\n\${{len(\$d3)}}
\${p}    Take Screenshot    \${OUTPUT_DIR}/q30    fileType=jpeg    quality=30    log_screenshot=False
\${p}    Take Screenshot    \${OUTPUT_DIR}/sc_css    scale=css    log_screenshot=False
Log To Console    \${{[ (f, __import__('os').path.getsize(f)) for f in __import__('glob').glob(\$OUTPUT_DIR + '/*.*g')]}}
.exit
RF
