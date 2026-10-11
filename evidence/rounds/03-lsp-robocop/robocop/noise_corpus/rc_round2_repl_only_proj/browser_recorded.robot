*** Settings ***
Library    Browser    timeout=5s

*** Test Cases ***
Saucedemo Recorded
    New Browser    chromium    headless=${HEADLESS}
    New Page    https://www.saucedemo.com
    Fill Text    id=user-name    standard_user
    Fill Text    id=password    secret_sauce
    Click    id=login-button
    Get Url    *=    inventory
    Click    id=add-to-cart-sauce-labs-backpack
    ${badge}    Get Text    css=.shopping_cart_badge    ==    1
    TRY
        Click    id=does-not-exist    
    EXCEPT    *    type=glob    AS    ${err}
        Log    caught: ${err}
    END
    ${st}    ${msg}    Run Keyword And Ignore Error    Get Text    css=.shopping_cart_badge    ==    5
    FOR    ${item}    IN    bike-light    bolt-t-shirt
        Click    id=add-to-cart-sauce-labs-${item}
    END
    Get Text    css=.shopping_cart_badge    ==    3
    Get Element Count    css=.inventory_item    ==    6
