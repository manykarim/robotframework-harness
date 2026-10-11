*** Settings ***
Documentation    Test suite generated from session lab_session containing 1 test case for web automation.
Library         OperatingSystem
Library         Browser
Test Tags       automated    generated    web

*** Test Cases ***
Greeting Test
    [Documentation]    Test case that verifies result, performs click action, verifies result.
    Create Directory    /artifacts
    New Browser    chromium    headless=True    args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"]
    New Page    file:///app/lab/index.html
    RF-MCP Lab =    Get Title
    Should Be Equal    RF-MCP Lab    RF-MCP Lab
    Fill Text    id=name    Robot
    Click    id=greet    # Click on id=greet
    Hello, Robot! =    Get Text    id=result
    Should Be Equal    Hello, Robot!    Hello, Robot!
    Take Screenshot    /artifacts/greeting.png
    [Teardown]    Close Browser