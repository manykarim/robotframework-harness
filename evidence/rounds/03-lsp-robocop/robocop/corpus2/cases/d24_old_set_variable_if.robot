*** Test Cases ***
T
    ${x}=    Set Variable    3
    ${size}=    Set Variable If    ${x} > 2    big    small
    Log    ${size}
