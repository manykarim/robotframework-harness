*** Settings ***
Documentation     Reference solution (hidden from agents): login inside an iframe, read result from shadow DOM.
Library           Browser
Suite Setup       New Browser    chromium    headless=True
Suite Teardown    Close Browser    ALL

*** Variables ***
${APP_URL}        file://${CURDIR}/../pages/app.html

*** Test Cases ***
Login Inside Iframe Shows Welcome In Shadow DOM
    New Page    ${APP_URL}
    Fill Text    id=loginframe >>> id=username    demo
    Fill Text    id=loginframe >>> id=password    demo
    Click    id=loginframe >>> id=submit
    Wait For Elements State    css=result-box#result >> css=#msg    visible    timeout=10s
    Get Text    css=result-box#result >> css=#msg    contains    Welcome, demo
