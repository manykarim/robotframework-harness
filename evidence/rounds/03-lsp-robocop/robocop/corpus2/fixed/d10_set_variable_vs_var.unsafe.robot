*** Test Cases ***
Vars
    ${name}=    Set Variable    Bob
    ${items}=    Create List    a    b
    Set Test Variable    ${GREETING}    hi
    Log Many    ${name}    @{items}    ${GREETING}
