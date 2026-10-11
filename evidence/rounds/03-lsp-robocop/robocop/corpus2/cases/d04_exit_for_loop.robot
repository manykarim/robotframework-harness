*** Test Cases ***
Loop
    FOR    ${i}    IN RANGE    10
        Continue For Loop If    ${i} == 1
        Exit For Loop If    ${i} > 3
        Log    ${i}
        Run Keyword If    ${i} == 2    Exit For Loop
    END
