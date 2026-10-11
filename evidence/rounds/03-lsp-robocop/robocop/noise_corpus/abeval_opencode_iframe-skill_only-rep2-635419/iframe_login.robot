*** Settings ***
Library    Browser    auto_closing_level=KEEP

*** Test Cases ***
Debug Iframe Login
    New Browser    chromium    headless=True
    New Context
    ${url}=    Set Variable    file://${CURDIR}/../pages/app.html
    Log    Loading URL: ${url}
    New Page    ${url}

    Wait For Load State    domcontentloaded

    Get Title    ==    Secure App

    ${count}=    Get Element Count    iframe
    Log    Iframe count: ${count}

    ${frame_element}=    Get Element    iframe#loginframe
    Log    Got frame element

    ${inner_elements}=    Get Elements    ${frame_element} >> *
    Log    Inner elements count: ${inner_elements}
