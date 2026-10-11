*** Settings ***
Library    Browser


*** Test Cases ***
Login
    New Page    https://example.org
    Input Text    id=user    bob
    Click Element    id=login
    Wait Until Page Contains    Welcome
