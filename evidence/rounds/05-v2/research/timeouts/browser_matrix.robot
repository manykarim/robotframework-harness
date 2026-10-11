*** Settings ***
Library    Browser
Library    ${CURDIR}/timing.py
Suite Setup    New Browser    chromium    headless=True
Suite Teardown    Close Browser    ALL

*** Variables ***
${SITE}    http://127.0.0.1:8765

*** Test Cases ***
Set Browser Timeout Semantics
    New Page    ${SITE}/index.html
    ${old}=    Set Browser Timeout    2s
    Log To Console    old=${old}
    ${old2}=    Set Browser Timeout    10s
    Log To Console    old2=${old2}
    ${old3}=    Set Retry Assertions For    3s
    Log To Console    retry_old=${old3}
    ${old4}=    Set Retry Assertions For    1s
    Log To Console    retry_old2=${old4}

Missing Locator Time To Fail
    New Page    ${SITE}/index.html
    FOR    ${to}    IN    10s    2s    1s
        Set Browser Timeout    ${to}
        FOR    ${i}    IN RANGE    3
            Measure    missing/click/${to}    Click    css=#nope
            Measure    missing/gettext/${to}    Get Text    css=#nope
            Measure    missing/wfes_visible/${to}    Wait For Elements State    css=#nope    visible
        END
        Measure    missing/fill/${to}    Fill Text    css=#nope    x
        Measure    missing/count/${to}    Get Element Count    css=#nope
        Measure    missing/getelements/${to}    Get Elements    css=#nope
        Measure    missing/textassert/${to}    Get Text    css=#nope    ==    x
    END
    Set Browser Timeout    10s

Explicit Timeout Overrides Browser Timeout
    New Page    ${SITE}/index.html
    Set Browser Timeout    10s
    Measure    explicit/wfes_timeout1s_with_bt10s    Wait For Elements State    css=#nope    visible    timeout=1s
    Set Browser Timeout    1s
    Measure    explicit/wfes_timeout5s_with_bt1s    Wait For Elements State    css=#nope    visible    timeout=5s
    Set Browser Timeout    10s

Slow But Valid Elements
    FOR    ${to}    IN    2s    10s
        Set Browser Timeout    ${to}
        FOR    ${id}    IN    a1500    a4000    a8000
            New Page    ${SITE}/async.html
            Measure    async/click/${id}/${to}    Click    id=${id}
            Close Page
        END
        FOR    ${id}    IN    a1500    a4000    a8000
            New Page    ${SITE}/async.html
            Measure    async/gettext/${id}/${to}    Get Text    id=${id}    ==    Ready ${id}
            Close Page
        END
    END
    Set Browser Timeout    10s

Assertion Retry Semantics
    # Title changes after 2 s: Get Title has no element wait, only assertion retry.
    FOR    ${ra}    IN    1s    3s
        Set Retry Assertions For    ${ra}
        FOR    ${bt}    IN    1s    10s
            Set Browser Timeout    ${bt}
            New Page    ${SITE}/async.html
            Measure    retry/title/ra${ra}/bt${bt}    Get Title    ==    R5 Async Done
            Close Page
        END
    END
    # Element exists immediately, text changes later: element wait done, assertion retry rules
    Set Retry Assertions For    1s
    Set Browser Timeout    10s
    New Page    ${SITE}/index.html
    Measure    retry/text_wrong_ra1s_bt10s    Get Text    css=h1    ==    Never This
    Set Retry Assertions For    3s
    Set Browser Timeout    1s
    Measure    retry/text_wrong_ra3s_bt1s    Get Text    css=h1    ==    Never This
    Set Retry Assertions For    1s
    Set Browser Timeout    10s

Navigation Timeout
    New Page    ${SITE}/index.html
    Set Browser Timeout    2s
    Measure    nav/goto_slow5s_bt2s    Go To    ${SITE}/slow?ms=5000
    Measure    nav/goto_slow5s_bt2s_explicit10s    Go To    ${SITE}/slow?ms=5000    timeout=10s
    Measure    nav/newpage_slow5s_bt2s    New Page    ${SITE}/slow?ms=5000
    Set Browser Timeout    10s
    Measure    nav/goto_slow5s_bt10s    Go To    ${SITE}/slow?ms=5000
    Measure    nav/newpage_slow5s_bt10s    New Page    ${SITE}/slow?ms=5000
    Measure    nav/newpage_slow12s_bt10s    New Page    ${SITE}/slow?ms=12000
