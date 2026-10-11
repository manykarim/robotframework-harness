*** Keywords ***
Greet
    [Arguments]    ${who}
    Log To Console    hi ${who}
    RETURN    hello ${who}
