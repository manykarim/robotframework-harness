*** Settings ***


*** Test Cases ***
Step
    FOR    ${i}    IN RANG    3
        Log    ${i}
    END
