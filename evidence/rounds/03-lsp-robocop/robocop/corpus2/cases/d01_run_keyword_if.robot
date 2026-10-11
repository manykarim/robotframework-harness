*** Test Cases ***
Check Value
    ${x}=    Set Variable    5
    Run Keyword If    ${x} > 3    Log    big    ELSE    Log    small
    Run Keyword Unless    ${x} > 3    Log    not big
