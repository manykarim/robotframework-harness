*** Settings ***
Library    Browser    timeout=2s
Library    ${CURDIR}/timing.py
Suite Setup    New Browser    chromium    headless=True
Suite Teardown    Close Browser    ALL

*** Variables ***
${SITE}    http://127.0.0.1:8765

*** Test Cases ***
Import Timeout Applies
    New Page    ${SITE}/index.html
    ${cur}=    Set Browser Timeout    2s
    Log To Console    import_timeout_reported=${cur}
    FOR    ${i}    IN RANGE    3
        Measure    import2s/missing/click    Click    css=#nope
    END

Assertion Retry Cap
    New Page    ${SITE}/index.html
    FOR    ${ra}    ${bt}    IN    1s    10s    3s    10s    5s    2s    3s    1s
        Set Retry Assertions For    ${ra}
        Set Browser Timeout    ${bt}
        Measure    retrycap/text_never/ra${ra}/bt${bt}    Get Text    css=h1    ==    Never This
        Measure    retrycap/title_never/ra${ra}/bt${bt}    Get Title    ==    Never This
        Measure    retrycap/count_never/ra${ra}/bt${bt}    Get Element Count    css=li    ==    999
    END
    Set Retry Assertions For    1s

Go To Repeat
    New Page    ${SITE}/index.html
    Set Browser Timeout    2s
    FOR    ${i}    IN RANGE    3
        Measure    nav/goto_slow5s_bt2s    Go To    ${SITE}/slow?ms=5000
        Measure    nav/goto_slow5s_bt2s_domcontent    Go To    ${SITE}/slow?ms=5000    wait_until=commit
    END

Scope Test Set
    Set Browser Timeout    3s    scope=Test
    ${cur}=    Set Browser Timeout    3s    scope=Test
    Log To Console    in_test_scope_test=${cur}

Scope Test Check Next
    ${cur}=    Set Browser Timeout    2s
    Log To Console    next_test_after_test_scope=${cur}

Scope Global Set
    Set Browser Timeout    4s    scope=Global

Scope Global Check Next
    ${cur}=    Set Browser Timeout    2s
    Log To Console    next_test_after_global=${cur}
