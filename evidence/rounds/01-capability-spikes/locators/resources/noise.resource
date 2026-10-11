*** Keywords ***
KA
    ${a}=    Set Variable    1
    Log To Console    KA done
KB
    ${lvl}=    Set Log Level    NONE
    ${a}=    Set Variable    1
    Set Log Level    ${lvl}
    Log To Console    KB done
KC
    ${lvl}=    Set Log Level    NONE
    ${a}=    Set Variable    1
    Log To Console    KC done
KD
    ${a}=    Set Variable    1
    Log    info message
    Log    warn message    WARN
    Log To Console    KD done
