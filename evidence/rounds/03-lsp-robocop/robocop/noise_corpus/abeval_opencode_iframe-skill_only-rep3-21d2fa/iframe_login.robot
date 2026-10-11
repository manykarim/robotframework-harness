*** Settings ***
Documentation     Login test with iframe and shadow DOM
Library           Browser    auto_closing_level=TEST

*** Test Cases ***
Login With Iframe And Verify Shadow DOM Message
    New Browser    chromium    headless=true
    New Context    viewport={'width': 1280, 'height': 720}
    New Page    file://~/.cache/ab-eval/work_conf/opencode/iframe-skill_only-rep3-21d2fa/workspace/pages/app.html

    Wait For Elements State    iframe#loginframe    visible

    Execute JavaScript    document.getElementById('loginframe').contentDocument.getElementById('username').value = 'demo'
    Execute JavaScript    document.getElementById('loginframe').contentDocument.getElementById('password').value = 'demo'
    Execute JavaScript    document.getElementById('loginframe').contentDocument.getElementById('submit').click()

    Wait For Elements State    #result    visible
    Get Text    #result >> #msg    contains    Welcome, demo
