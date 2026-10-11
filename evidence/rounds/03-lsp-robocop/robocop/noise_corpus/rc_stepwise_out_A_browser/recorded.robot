*** Settings ***
Library    Browser    timeout=10s

*** Test Cases ***
Saucedemo Add To Cart
    New Browser    chromium    headless=${HEADLESS}
    New Page    https://www.saucedemo.com
    Fill Text    [data-test="username"]    standard_user
    Fill Text    [data-test="password"]    secret_sauce
    Click    [data-test="login-button"]
    Get Url    ==    https://www.saucedemo.com/inventory.html
    Get Element Count    [data-test="inventory-item"]    ==    6
    Click    [data-test="add-to-cart-sauce-labs-backpack"]
    Get Text    [data-test="shopping-cart-badge"]    ==    1
    Click    [data-test="shopping-cart-link"]
    Get Url    *=    cart.html
    Set Browser Timeout    2s
    Get Element Count    [data-test="inventory-item"]    ==    1
    ${title}=    Get Title
    Get Text    [data-test="shopping-cart-badge"]    ==    1
