# Examples

## Web UI, step by step, then a file
```
rfmcp start
rfmcp step 'Import Library    Browser'
rfmcp step 'New Browser    chromium    headless=True'
rfmcp step 'New Page    https://shop.example/login'
rfmcp state controls                  # fields/buttons: label, id, data-test, hidden?, => selector
rfmcp state aria                      # texts, roles, iframes
rfmcp step 'Fill Text    id=username    alice'
rfmcp step 'Click    role=button[name="Sign in"]'
rfmcp step 'Get Text    id=status    ==    Hello, alice'
rfmcp step 'Fill Text    id=editor-frame >>> id=title    Draft'   # element inside <iframe id="editor-frame">
```
Then write `tests/login.robot` with your edit tool:
```
*** Settings ***
Library    Browser
Suite Setup    New Browser    chromium    headless=True

*** Variables ***
${URL}    https://shop.example/login

*** Test Cases ***
Login Works
    New Page    ${URL}
    Fill Text    id=username    alice
    Click    role=button[name="Sign in"]
    Get Text    id=status    ==    Hello, alice
```
```
rfmcp run tests/login.robot          # runs the lines in the live session (static check first)
# fix the reported line with your edit tool ...
rfmcp run tests/login.robot          # only new/changed lines run
rfmcp stop
robot -d results tests/login.robot   # final real run (fresh browser)
```

## API with RequestsLibrary
```
rfmcp step 'Import Library    RequestsLibrary'
rfmcp step 'Create Session    api    http://127.0.0.1:8000'
rfmcp step '${resp}=    GET On Session    api    /users.json'
rfmcp step 'Status Should Be    200    ${resp}'
rfmcp step 'Should Be Equal As Strings    ${resp.json()}[0][name]    Ann'
rfmcp step '${resp}=    POST On Session    api    /users    json=${{ {"name": "Dave"} }}    expected_status=201'
```

## Repair an existing failing suite
```
robot -d results tests/orders.robot                      # 2 failed
robotcode results show --failed -o results/output.xml    # "Create Order" L14: TimeoutError ... waiting for locator('id=save')
                                                         # "Order List" L22: 0 != 3
rfmcp run tests/orders.robot --test "Create Order"       # stops at L14: NOT RUN, guard NOT_FOUND, page stays open
rfmcp state controls                                     # button "Save order" data-test=save-order => data-test=save-order
rfmcp step 'Click    data-test=save-order'               # works -> edit L14 with your edit tool
rfmcp run tests/orders.robot --test "Create Order"       # resumes at L14 -> rest of the test passes
rfmcp run tests/orders.robot --test "Order List"         # L22 FAIL: the count was read before the list loaded
# edit: add   Wait For Elements State    css=.order-row >> nth=2    visible    timeout=15s   before the count line
rfmcp run tests/orders.robot --test "Order List" --lines 20-23   # lines that already ran: re-run them explicitly
rfmcp stop
robot -d results tests/orders.robot                      # final proof: all tests pass, none removed or weakened
```

## Analyze an existing output.xml (no helper)
```
robotcode results summary -o results/output.xml
robotcode results show --failed -o results/output.xml
robotcode results log "*Login*" -o results/output.xml
rfmcp guide results                  # ExecutionResult API snippet for custom questions
```
