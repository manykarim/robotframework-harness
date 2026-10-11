*** Test Cases ***
Branch
    ${x}=    Set Variable    1
    IF    ${x} == 2
        Log    two
    ELSE
        Log    other
    END
