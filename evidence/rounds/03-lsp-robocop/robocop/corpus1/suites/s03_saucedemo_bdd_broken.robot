*** Settings ***
Documentation     Broken variant of s02 with 7 planted errors (P1..P7).
Library           Browser    timeout=10s
Suite Setup       New Browser    chromium    headless=${HEADLESS}
Suite Teardown    Close Browser    ALL
Test Setup        New Page    ${BASE_URL}
Test Tags         ui    saucedemo

*** Variables ***
${HEADLESS}       True
${PASSWORD}       secret_sauce

*** Test Cases ***
Standard User Adds Backpack To Cart
    [Tags]    smoke
    Given the user is logged in as "standard_user"
    When the user adds sauce-labs-backpack to the cart
    Then the cart badge shows "1"

Problem User Sorts By Price
    [Tag]    expected-fail
    Given the user is logged in as "problem_user"
    When the user sorts products by "lohi"
    Then the first product price is "$7.99"

*** Keywords ***
the user is logged in as "${username}"
    Fill Text    [data-test="username"]    ${usrname}
    Fill Secret    [data-test="password"]    $PASSWORD
    Input Text    [data-test="password"]    ${PASSWORD}
    Click    [data-test="login-button"]
    Get Url    *=    inventory.html

the user adds "${item}" to the cart
    Clik    [data-test="add-to-cart-${item}"]

the cart badge shows "${count}"
    Get Text    [data-test="shopping-cart-badge"]    ==

the user sorts products by "${order}"
    Select Options By    [data-test="product-sort-container"]    value    ${order}
    IF    ${order} == 'lohi'
        Log    sorted
    ELSE IF
        Log    other
    END

the first product price is "${price}"
    Get Text    [data-test="inventory-item-price"] >> nth=0    equals    ${price}    timeout=5s
