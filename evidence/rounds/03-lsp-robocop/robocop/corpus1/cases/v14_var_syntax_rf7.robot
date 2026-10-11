*** Settings ***


*** Test Cases ***
Step
    VAR    ${v}    hello    scope=TEST
    IF    $v == 'hello'
        Log    ${v}
    END
    FOR    ${i}    IN RANGE    2
        Log    ${i}
    END
    TRY
        Fail    x
    EXCEPT    x
        Log    caught
    END
