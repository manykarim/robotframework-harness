*** Test Cases ***
Loop
    FOR    ${i}    IN RANGE    10
        IF    ${i} == 1    CONTINUE
        IF    ${i} > 3    BREAK
        Log    ${i}
        IF    ${i} == 2    BREAK
    END
