*** Settings ***
Documentation    Test suite generated from session lab_session containing 1 test case for web automation.
Library         Browser
Test Tags       automated    generated    web

*** Test Cases ***
Greeting Lab Test
    New Browser    chromium    headless=True    args=['--no-sandbox', '--disable-dev-shm-usage', '--disable-gpu']
    New Page    file:///app/lab/index.html
    ${title} =    Get Title
    Fill Text    id=name    Robot
    Click    id=greet
    ${result_text} =    Get Text    id=result
    Take Screenshot    /artifacts/greeting.png
