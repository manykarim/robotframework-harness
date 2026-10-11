*** Settings ***
Library    Browser    auto_closing_level=KEEP

*** Test Cases ***
Login Through Iframe And Verify Shadow DOM Message
    New Browser    chromium    headless=false
    New Context
    New Page       file://~/.cache/ab-eval/work_conf/claude/iframe-both-rep3-65eee4/workspace/pages/app.html

    Fill Text      iframe#loginframe >> input#username    demo
    Fill Secret    iframe#loginframe >> input#password    demo
    Click          iframe#loginframe >> button#submit

    Wait For Elements State    result-box#result    visible
    Get Text    result-box#result >> span#msg    contains    Welcome, demo
