*** Test Cases ***
Loop
    FOR    ${i}    IN RANGE    10
        IF    ${i} == 1
            CONTINUE
        END
        IF    ${i} > 3
            BREAK
        END
        Log    ${i}
        IF    ${i} == 2
            BREAK
        END
    END
