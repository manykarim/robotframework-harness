*** Test Cases ***
Check Value
    ${x}=    Set Variable    5
    IF    ${x} > 3    Log    big    ELSE    Log    small
    IF    not (${x} > 3)    Log    not big
