*** Settings ***
Library    Browser
Library    ${CURDIR}/timing.py
Suite Setup    New Browser    chromium    headless=True
Suite Teardown    Close Browser    ALL

*** Test Cases ***
Default Timeout Survives
    New Page    http://127.0.0.1:8765/index.html
    ${cur}=    Set Browser Timeout    10s
    Log To Console    timeout_in_run=${cur}
