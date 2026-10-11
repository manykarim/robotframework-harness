*** Settings ***


*** Test Cases ***
Step
    IF
        Log    no condition
    ELSE
        Log    else
    ELSE IF    True
        Log    x
    END
