*** Settings ***
Documentation    Test suite generated from session rf_mcp_lab_session containing 1 test case for web automation.
Library         Browser
Test Tags       automated    generated    web

*** Test Cases ***
RF-MCP Lab Greeting
    [Documentation]    Verifies the greeting flow on the RF-MCP Lab page.
    New Browser    chromium    headless=True
    Close Browser
    New Browser    browser=chromium    headless=True    args=["--no-sandbox","--disable-dev-shm-usage","--disable-gpu"]\n
    New Page    file:///app/lab/index.html
    ${title} =    Get Title
    Should Be Equal    ${title}    RF-MCP Lab
    Fill Text    id=name    Robot
    Click    id=greet    # Click on id=greet
    ${result} =    Get Text    id=result
    Should Be Equal    ${result}    Hello, Robot!
