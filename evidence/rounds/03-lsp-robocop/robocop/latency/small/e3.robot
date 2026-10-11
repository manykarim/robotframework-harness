*** Settings ***
Documentation     Agent-written checkout flow with 3 planted mistakes.
Library           Browser    timeout=10s
Library           Collections

*** Variables ***
${BASE_URL}       https://www.saucedemo.com

*** Test Cases ***
Add Backpack To Cart
    New Browser    chromium    headless=True
    New Page    ${BASE_URL}
    Fill Text    [data-test="username"]    standard_user
    Fill Text    [data-test="password"]    secret_sauce
    Click    [data-test="login-button"]
    Get Url    ==    ${BASE_URL}/inventory.html
    Input Text    id=search    backpack
    Click    [data-test="add-to-cart-sauce-labs-backpack"]
    ${badge}=    Get Text    [data-test="shopping-cart-badge"]
    Run Keyword If    '${badge}' != '1'    Fail    badge is ${badge}
    Fill Text    [data-test="firstName"]
    ${items}=    Create List    a    b
    Log Many    @{items}
    [Teardown]    Close Browser
