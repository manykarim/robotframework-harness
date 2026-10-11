*** Test Cases ***
Use Kw
    ${v}=    Pick    2
    Should Be Equal    ${v}    two

*** Keywords ***
Pick
    [Arguments]    ${n}
    IF    ${n} == 1
        RETURN    one
    END
    RETURN    two
