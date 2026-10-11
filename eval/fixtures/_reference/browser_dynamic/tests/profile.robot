*** Settings ***
Documentation     Reference solution (hidden from agents): wait for an async-injected card, check text + attribute.
Library           Browser
Suite Setup       New Browser    chromium    headless=True
Suite Teardown    Close Browser    ALL

*** Test Cases ***
Profile Card Loads Asynchronously
    New Page    file://${CURDIR}/../pages/profile.html
    Click    id=load
    Wait For Elements State    id=profile    visible    timeout=10s
    Get Text    id=name    contains    Ada Lovelace
    Get Attribute    id=profile    data-uid    ==    u-42
