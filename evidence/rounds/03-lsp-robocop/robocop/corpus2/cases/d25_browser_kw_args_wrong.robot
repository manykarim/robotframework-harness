*** Settings ***
Library    Browser

*** Test Cases ***
T
    New Page    https://example.org
    Click    id=login    left    2    0.1    extra    more    args    too    many    xx
    Get Text    h1    should be    Welcome
