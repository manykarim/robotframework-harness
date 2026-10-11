*** Settings ***
Library    Browser

*** Test Cases ***
Step
    New Page    https://example.org    wait_until=load
    Fill Text    id=user    bob
    Get Text    id=foo    ==    bar
