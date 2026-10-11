#!/usr/bin/env bash
# Approach B benchmark: FIFO-fed `robotcode repl --plain`, same saucedemo + booker steps as approach A
set -u
cd "$(dirname "$0")"
D=out/B_bench; F=./fifo_repl.sh; now() { date +%s%N; }
T0=$(now); $F start $D >/dev/null
step() { local t=$(now); $F step $D "$1" > $D/last.txt; local rc=$?; echo "rc=$rc wall_ms=$(( ($(now)-t)/1000000 )) :: ${1%%$'\n'*}"; [ $rc -ne 0 ] && grep -E "FAIL|timeout" $D/last.txt | head -2 | cut -c1-160; }
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
step 'Get Text  [data-test="shopping-cart-badge"]  ==  5'
step 'Click  css=#does-not-exist'
step 'Get Element Count  [data-test="inventory-item"]  ==  1'
step '${title}=  Get Title'
step 'Get Text  [data-test="shopping-cart-badge"]  ==  1'
step $'TRY\n    Click  css=#nope\nEXCEPT\n    Log  caught\nEND'
step 'Run Keyword And Ignore Error  Get Text  css=#nope'
step 'Import Library  RequestsLibrary'
step 'Import Library  Collections'
step 'Create Session  booker  https://restful-booker.herokuapp.com  headers={"Accept": "application/json"}'
step $'${auth}=  Create Dictionary  username=admin  password=password123\n${resp}=  POST On Session  booker  /auth  json=${auth}\n${token}=  Set Variable  ${resp.json()}[token]'
step $'${dates}=  Create Dictionary  checkin=2026-10-01  checkout=2026-10-05\n${body}=  Create Dictionary  firstname=Robo  lastname=Step  totalprice=${123}  depositpaid=${True}  bookingdates=${dates}  additionalneeds=Breakfast'
step '${resp}=  POST On Session  booker  /booking  json=${body}'
step '${id}=  Set Variable  ${resp.json()}[bookingid]'
step '${resp}=  GET On Session  booker  /booking/${id}'
step 'Should Be Equal  ${resp.json()}[firstname]  Robo'
step 'GET On Session  booker  /booking/999999999'
step $'${h}=  Create Dictionary  Cookie=token=${token}\nDELETE On Session  booker  /booking/${id}  headers=${h}  expected_status=201'
echo "total_ms=$(( ($(now)-T0)/1000000 ))"
echo "### .save via FIFO"; $F step $D ".save -t \"Fifo Recorded\" $PWD/$D/saved.robot" | tail -3
T1=$(now); $F stop $D; echo "stop_ms=$(( ($(now)-T1)/1000000 ))"
