*** Settings ***
Library    SeleniumLibrary

*** Test Cases ***
Step
    Open Browser    https://example.org    headlesschrome
    Input Text    id=user    bob
