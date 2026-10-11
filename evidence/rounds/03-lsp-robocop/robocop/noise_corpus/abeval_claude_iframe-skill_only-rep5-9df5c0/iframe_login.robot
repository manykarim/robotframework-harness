*** Settings ***
Library    Browser    auto_closing_level=KEEP
Test Teardown    Close Page

*** Variables ***
${FILE_URL}    file://~/.cache/ab-eval/work_conf/claude/iframe-skill_only-rep5-9df5c0/workspace/pages/app.html

*** Test Cases ***
Login Through Iframe And Verify Shadow DOM Message
    [Documentation]    Test login form inside iframe and verify welcome message in shadow DOM
    Open Browser And Navigate
    Fill Login Credentials
    Submit Login Form
    Verify Welcome Message

*** Keywords ***
Open Browser And Navigate
    [Documentation]    Initialize browser and open the app via file URL
    New Browser    chromium    headless=false
    New Context    viewport={'width': 1280, 'height': 720}
    New Page    ${FILE_URL}
    Wait For Load State    networkidle
    Wait For Elements State    iframe#loginframe    visible    timeout=10s

Fill Login Credentials
    [Documentation]    Fill username and password fields inside the iframe
    # Get the iframe element first to ensure it's loaded
    ${frame}=    Get Element    iframe#loginframe
    Fill Text    ${frame} >> input#username    demo
    Fill Secret    ${frame} >> input#password    demo

Submit Login Form
    [Documentation]    Click submit button inside the iframe
    ${frame}=    Get Element    iframe#loginframe
    Click    ${frame} >> button#submit

Verify Welcome Message
    [Documentation]    Wait for result box to appear and verify message in shadow DOM
    Wait For Elements State    result-box#result    visible    timeout=10s
    Get Text    result-box#result >> #msg    contains    Welcome, demo
