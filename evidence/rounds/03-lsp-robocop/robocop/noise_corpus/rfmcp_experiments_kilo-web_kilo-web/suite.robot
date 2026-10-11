*** Settings ***
Documentation    Test suite generated from session web_test containing 1 test case for web automation.
Library         Browser
Test Tags       automated    generated    web

*** Test Cases ***
RF-MCP Lab Greeting Test
    [Documentation]    Test case that performs click action.
    New Browser    chromium    headless=True    args=["--no-sandbox","--disable-dev-shm-usage","--disable-gpu"]
    New Page    file:///app/lab/index.html
    ${page_title} =    Get Title
    Fill Text    id=name    Robot
    Click    id=greet    # Click on id=greet
    ${greeting} =    Get Text    id=result
    Take Screenshot    filename=/artifacts/kilo-web/greeting.png
    [Teardown]    Close Browser    
