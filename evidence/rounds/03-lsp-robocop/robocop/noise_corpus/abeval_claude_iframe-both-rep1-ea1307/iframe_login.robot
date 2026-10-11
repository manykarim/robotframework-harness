*** Settings ***
Documentation     Test login form inside iframe and verify success message in shadow DOM
Library           Browser    auto_closing_level=TEST

*** Variables ***
${APP_URL}        file://~/.cache/ab-eval/work_conf/claude/iframe-both-rep1-ea1307/workspace/pages/app.html
${USERNAME}       demo
${PASSWORD}       demo

*** Test Cases ***
Login Through Iframe And Verify Shadow DOM Message
    [Documentation]    Fill login form in iframe, submit, and verify success message in shadow DOM
    New Browser       chromium    headless=false
    New Context       viewport={'width': 1280, 'height': 720}
    New Page          ${APP_URL}

    # Wait for iframe to be visible and page to load
    Wait For Elements State    iframe#loginframe    visible    timeout=10s
    Wait For Load State    networkidle

    # Get iframe element reference
    ${frame}=    Get Element    iframe#loginframe

    # Fill username field inside iframe using frame reference
    Fill Text    ${frame} >> input#username    ${USERNAME}

    # Fill password field inside iframe using frame reference
    Fill Text    ${frame} >> input#password    ${PASSWORD}

    # Click submit button inside iframe using frame reference
    Click        ${frame} >> button#submit

    # Wait for result-box to be visible
    Wait For Elements State    result-box#result    visible    timeout=10s

    # Get text from shadow DOM inside result-box
    ${message}=       Get Text    result-box#result >> span#msg

    # Verify message contains expected text
    Should Contain    ${message}    Welcome, demo

    Log    Test passed! Message: ${message}
