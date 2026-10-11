*** Settings ***
Documentation    Test suite generated from session greeting_test containing 1 test case for web automation.
Library         Browser
Test Tags       automated    generated    web

*** Test Cases ***
Greeting Flow
    [Documentation]    BDD spec for the greeting flow on the RF-MCP Lab page.
    Given the the application is open
    When the user fills in the form and clicks greet field
    Then the result is correct
    [Teardown]    Close Browser    

*** Keywords ***
the the application is open
    New Browser    chromium    headless=True    args=["--no-sandbox","--disable-dev-shm-usage","--disable-gpu"]
    New Page    file:///app/lab/index.html

the user fills in the form and clicks greet field
    Fill Text    id=name    Robot
    Click    id=greet
    Get Text    id=result

the result is correct
    Should Be Equal    ${greeting}    Hello, Robot!
