*** Test Cases ***
Cond
    ${status}=    Set Variable    PASS
    IF    ${status} == PASS
        Log    ok
    END
