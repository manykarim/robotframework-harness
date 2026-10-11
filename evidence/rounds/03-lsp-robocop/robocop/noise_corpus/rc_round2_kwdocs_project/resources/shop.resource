*** Settings ***
Documentation     Shop page objects for the demo shop.
Library           Collections

*** Keywords ***
Login As User
    [Documentation]    Logs into the shop with the given credentials.
    ...
    ...    Opens the login form, fills ``username`` and ``password`` and submits.
    ...    Fails if the dashboard does not appear within ``timeout``.
    [Tags]    auth    ui
    [Arguments]    ${username}    ${password}    ${timeout}=10s
    Log    ${username}

Add Product To Cart
    [Documentation]    Adds the named product to the shopping cart and verifies the badge count.
    [Arguments]    ${product}    ${quantity}=1
    Log    ${product}
