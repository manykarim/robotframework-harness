*** Settings ***
Documentation    Open the RF-MCP Lab HTML fixture in headless chrome, type a name, click Greet, and confirm the result text.
Library         SeleniumLibrary

*** Test Cases ***
RF-MCP Lab Greeting Test
    [Documentation]    Types a name into the input, clicks the Greet button, and confirms the resulting text.
    Open Browser    file:///app/lab/index.html    chrome    options=add_argument("--headless=new");add_argument("--no-sandbox");add_argument("--disable-dev-shm-usage");add_argument("--disable-gpu")
    Title Should Be    RF-MCP Lab
    Input Text    id=name    Robot
    Click Element    id=greet
    ${result_text} =    Get Text    id=result
    Should Be Equal    ${result_text}    Hello, Robot!
    Capture Page Screenshot    /artifacts/greeting.png
    Close All Browsers
