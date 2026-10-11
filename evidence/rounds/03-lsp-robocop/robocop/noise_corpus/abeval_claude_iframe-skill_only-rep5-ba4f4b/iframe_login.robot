*** Settings ***
Library    Browser    auto_closing_level=KEEP

*** Test Cases ***
Login Through iframe And Read Shadow DOM Message
    New Browser    chromium    headless=false
    New Context
    New Page    file://~/.cache/ab-eval/work_conf/claude/iframe-skill_only-rep5-ba4f4b/workspace/pages/app.html

    # Fill username field inside iframe
    Fill Text    iframe#loginframe >> input#username    demo

    # Fill password field inside iframe
    Fill Secret    iframe#loginframe >> input#password    demo

    # Click submit button inside iframe
    Click    iframe#loginframe >> button#submit

    # Wait for result-box to become visible
    Wait For Elements State    result-box#result    visible    timeout=10s

    # Read message from shadow DOM and verify it contains "Welcome, demo"
    Get Text    result-box#result >> span#msg    contains    Welcome, demo
