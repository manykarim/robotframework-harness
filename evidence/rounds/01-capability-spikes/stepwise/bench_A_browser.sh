#!/usr/bin/env bash
# Approach A: robotcode repl-server (TCP) + one-shot rfstep.py per step (each step = separate process)
set -u
cd "$(dirname "$0")"
RC=~/workspace/robotcode-experiments/.venv/bin/robotcode
PORT=${PORT:-6702}; OUT=out/A_browser; J=$OUT/journal.jsonl
rm -rf "$OUT"; mkdir -p "$OUT"
now() { date +%s%N; }
T0=$(now)
nohup $RC repl-server --tcp $PORT -d "$OUT" </dev/null >"$OUT/server.log" 2>&1 &
SPID=$!; echo "$SPID" > "$OUT/server.pid"
until ss -ltn | grep -q ":$PORT "; do sleep 0.02; done
echo "server pid=$SPID listening_ms=$(( ($(now)-T0)/1000000 ))"
step() {  # step "<cell>"
  local t=$(now)
  python3 rfstep.py run --port $PORT --journal "$J" --test "Saucedemo Add To Cart" "$1"
  local rc=$?
  echo "   -> rc=$rc wall_ms=$(( ($(now)-t)/1000000 ))"
}
step 'Import Library  Browser  timeout=10s'
step 'New Browser  chromium  headless=${HEADLESS}'
step 'New Page  https://www.saucedemo.com'
step 'Fill Text  [data-test="username"]  standard_user'
step 'Fill Text  [data-test="password"]  secret_sauce'
step 'Click  [data-test="login-button"]'
step 'Get Url  ==  https://www.saucedemo.com/inventory.html'
step 'Get Element Count  [data-test="inventory-item"]  ==  6'
step 'Click  [data-test="add-to-cart-sauce-labs-backpack"]'
step 'Get Text  [data-test="shopping-cart-badge"]  ==  1'
step 'Click  [data-test="shopping-cart-link"]'
step 'Get Url  *=  cart.html'
step 'Set Browser Timeout  2s'
step 'Get Text  [data-test="shopping-cart-badge"]  ==  5'          # intentional failure
step 'Click  css=#does-not-exist'                                  # intentional failure (locator)
step 'Get Element Count  [data-test="inventory-item"]  ==  1'
step '${title}=  Get Title'
step 'Get Text  [data-test="shopping-cart-badge"]  ==  1'
echo "### server children before shutdown:"; pgrep -P $SPID -a | cut -c1-150
echo "total_ms=$(( ($(now)-T0)/1000000 ))"
