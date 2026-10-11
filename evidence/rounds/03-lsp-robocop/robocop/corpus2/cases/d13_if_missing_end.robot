*** Test Cases ***
Branch
    ${x}=    Set Variable    1
    IF    ${x} == 1
        Log    one
    Log    after
