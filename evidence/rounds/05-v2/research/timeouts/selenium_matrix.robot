*** Settings ***
Library    SeleniumLibrary    run_on_failure=Nothing
Library    ${CURDIR}/timing.py
Suite Setup    Open Browser    ${SITE}/index.html    headlesschrome
Suite Teardown    Close All Browsers

*** Variables ***
${SITE}    http://127.0.0.1:8765

*** Test Cases ***
Defaults And Return Values
    ${old}=    Set Selenium Timeout    2s
    Log To Console    sel_timeout_old=${old}
    ${oldi}=    Set Selenium Implicit Wait    0s
    Log To Console    sel_implicit_old=${oldi}
    Set Selenium Timeout    5s

Missing Locator Time To Fail
    Go To    ${SITE}/index.html
    FOR    ${to}    ${iw}    IN    10s    0s    2s    0s    1s    0s    5s    2s    5s    10s
        Set Selenium Timeout    ${to}
        Set Selenium Implicit Wait    ${iw}
        FOR    ${i}    IN RANGE    3
            Measure    missing/click/t${to}/iw${iw}    Click Element    css:#nope
            Measure    missing/wuev/t${to}/iw${iw}    Wait Until Element Is Visible    css:#nope
        END
        Measure    missing/wupce/t${to}/iw${iw}    Wait Until Page Contains Element    css:#nope
        Measure    missing/etsb/t${to}/iw${iw}    Element Text Should Be    css:#nope    x
        Measure    missing/gettext/t${to}/iw${iw}    Get Text    css:#nope
        Measure    missing/pcе/t${to}/iw${iw}    Page Should Contain Element    css:#nope
        Measure    missing/input/t${to}/iw${iw}    Input Text    css:#nope    x
        Measure    missing/count/t${to}/iw${iw}    Get Element Count    css:#nope
        Measure    missing/pnce/t${to}/iw${iw}    Page Should Not Contain Element    css:#nope
    END
    Set Selenium Implicit Wait    0s
    Set Selenium Timeout    5s

Slow But Valid Elements
    FOR    ${to}    ${iw}    IN    2s    0s    10s    0s    5s    2s    5s    10s
        Set Selenium Timeout    ${to}
        Set Selenium Implicit Wait    ${iw}
        FOR    ${id}    IN    a1500    a4000    a8000
            Go To    ${SITE}/async.html
            Measure    async/click/${id}/t${to}/iw${iw}    Click Element    id:${id}
            Go To    ${SITE}/async.html
            Measure    async/wuev/${id}/t${to}/iw${iw}    Wait Until Element Is Visible    id:${id}
            Go To    ${SITE}/async.html
            Measure    async/etsb/${id}/t${to}/iw${iw}    Element Text Should Be    id:${id}    Ready ${id}
        END
    END
    Set Selenium Implicit Wait    0s
    Set Selenium Timeout    5s

Explicit Timeout Arg Overrides
    Go To    ${SITE}/index.html
    Set Selenium Timeout    10s
    Measure    explicit/wuev_timeout1s_st10s    Wait Until Element Is Visible    css:#nope    timeout=1s
    Set Selenium Timeout    1s
    Measure    explicit/wuev_timeout5s_st1s    Wait Until Element Is Visible    css:#nope    timeout=5s
    Set Selenium Timeout    5s

Navigation Page Load Timeout
    Set Selenium Page Load Timeout    2s
    Measure    nav/goto_slow5s_plt2s    Go To    ${SITE}/slow?ms=5000
    Set Selenium Page Load Timeout    5 minutes
    Set Selenium Timeout    2s
    Measure    nav/goto_slow5s_st2s_plt300s    Go To    ${SITE}/slow?ms=5000
    Set Selenium Timeout    5s
