*** Settings ***
Documentation     Shop helpers for the round-5 docs probe.
Library           Browser

*** Variables ***
${BASE}    file:///tmp

*** Keywords ***
Open Shop
    [Documentation]    Opens the shop start page in a new page. Uses ${BASE}.
    [Arguments]    ${path}=/index.html
    New Page    ${BASE}${path}

Add Product To Cart
    [Documentation]    Clicks the add button of product ``${index}`` and checks the badge.
    ...    Second line of docs.
    [Arguments]    ${index}    ${expected_count}=1
    Click    id=add-${index}

Login As
    [Arguments]    ${user}    ${password}    &{options}
    Fill Text    id=user    ${user}
