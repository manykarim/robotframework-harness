*** Settings ***
Library    Collections    WITH NAME    Coll

*** Test Cases ***
Alias
    ${l}=    Create List    a    b
    Coll.List Should Contain Value    ${l}    a
