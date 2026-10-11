*** Settings ***
Library    Collections    AS    Coll


*** Test Cases ***
Alias
    ${l}=    Create List    a    b
    Coll.List Should Contain Value    ${l}    a
