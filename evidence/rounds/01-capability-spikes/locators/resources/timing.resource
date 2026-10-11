*** Settings ***
Documentation    Timing helper for latency measurements (research only).

*** Keywords ***
Timed
    [Documentation]    Run ${kw} with @{args}, print TIME|label|ms|status|result(first 160 chars).
    [Arguments]    ${label}    ${kw}    @{args}
    ${t0}=    Evaluate    time.perf_counter()    modules=time
    ${st}    ${res}=    Run Keyword And Ignore Error    ${kw}    @{args}
    ${ms}=    Evaluate    round((time.perf_counter() - $t0) * 1000, 1)    modules=time
    ${short}=    Evaluate    str($res).replace('\\n', ' ')[:160]
    Log To Console    TIME|${label}|${ms}|${st}|${short}
    RETURN    ${res}
