*** Settings ***
Library    Collections

*** Variables ***
${BASE}    10

*** Test Cases ***
Sum Items
    ${total}=    Set Variable    ${0}
    FOR    ${i}    IN RANGE    1    4
        ${total}=    Process Item    ${i}    ${total}
    END
    Should Be Equal As Integers    ${total}    7

*** Keywords ***
Process Item
    [Arguments]    ${item}    ${acc}
    ${new}=    Evaluate    ${acc} + ${item}
    RETURN    ${new}
