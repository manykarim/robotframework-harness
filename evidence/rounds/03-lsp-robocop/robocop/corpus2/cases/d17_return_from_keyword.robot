*** Test Cases ***
Use Kw
    ${v}=    Pick    2
    Should Be Equal    ${v}    two

*** Keywords ***
Pick
    [Arguments]    ${n}
    Return From Keyword If    ${n} == 1    one
    Return From Keyword    two
