#!/usr/bin/env bash
# saucedemo via stock robotcode repl + FIFO + rfmcp listener; every step a separate process
set -u
HERE=$(cd "$(dirname "$0")" && pwd); D=$HERE/run/browser; PY=~/workspace/robotcode-experiments/.venv/bin/python
rm -rf "$D"; export OUTJSON=$HERE/logs/latency.jsonl
step() { local t0=$(date +%s%N); local r; r=$($PY "$HERE/rfrepl.py" step --dir "$D" "$1"); local t1=$(date +%s%N); echo "[$(( (t1-t0)/1000000 )) ms] $r" | cut -c1-600; }
s0=$(date +%s%N); $PY "$HERE/rfrepl.py" start --dir "$D" --output output.xml; s1=$(date +%s%N); echo "start wall: $(( (s1-s0)/1000000 )) ms"
step 'Import Library    Browser    timeout=5s'
step 'New Browser    chromium    headless=${HEADLESS}'
step 'New Page    https://www.saucedemo.com'
step 'Fill Text    id=user-name    standard_user'
step 'Fill Text    id=password    secret_sauce'
step 'Click    id=login-button'
step 'Get Url    *=    inventory'
step 'Click    id=add-to-cart-sauce-labs-backpack'
step '${badge}    Get Text    css=.shopping_cart_badge    ==    1'
step 'TRY
    Click    id=does-not-exist    
EXCEPT    *    type=glob    AS    ${err}
    Log    caught: ${err}
END'
step '${st}    ${msg}    Run Keyword And Ignore Error    Get Text    css=.shopping_cart_badge    ==    5'
step 'Get Text    css=.shopping_cart_badge    ==    5'
step 'FOR    ${item}    IN    bike-light    bolt-t-shirt
    Click    id=add-to-cart-sauce-labs-${item}
END'
step 'Get Text    css=.shopping_cart_badge    ==    3'
step 'Get Element Count    css=.inventory_item    ==    6'
"$HERE/bench.sh" py "$D" 30 'Get Title' browser-get-title-py
"$HERE/bench.sh" sh "$D" 30 'Get Title' browser-get-title-sh
"$HERE/bench.sh" py "$D" 30 'Get Text    css=.shopping_cart_badge    ==    3' browser-get-text-assert-py
