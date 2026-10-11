*** Settings ***
Library    Collections    WITH NAME    Coll
Force Tags    smoke

*** Test Cases ***
Probe
    ${x}=    Set Variable    5
    Run Keyword If    ${x} > 3    Log    big
    Shuold Be Equal    a    a
    Should Be Equal    a
    Log    ${undefined_var}
