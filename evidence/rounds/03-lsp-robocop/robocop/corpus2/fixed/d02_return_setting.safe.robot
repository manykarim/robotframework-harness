*** Test Cases ***
Use Kw
    ${v}=    Get Five
    Should Be Equal As Integers    ${v}    5

*** Keywords ***
Get Five
    ${r}=    Evaluate    2 + 3
    RETURN    ${r}
