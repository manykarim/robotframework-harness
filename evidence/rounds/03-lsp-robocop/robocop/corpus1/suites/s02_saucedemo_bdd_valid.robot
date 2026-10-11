*** Settings ***
Documentation     Sauce Demo login and cart flow (rf-mcp build_test_suite style, bdd_style=True).
...               One test fails on purpose (problem_user sorting) so results analysis has a failure.
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
    When the user adds "sauce-labs-backpack" to the cart
    Then the cart badge shows "1"

Problem User Sorts By Price
    [Tags]    expected-fail
    Given the user is logged in as "problem_user"
    When the user sorts products by "lohi"
    Then the first product price is "$7.99"

*** Keywords ***
the user is logged in as "${username}"
    Fill Text    [data-test="username"]    ${username}
    Fill Secret    [data-test="password"]    $PASSWORD
    Click    [data-test="login-button"]
    Get Url    *=    inventory.html

the user adds "${item}" to the cart
    Click    [data-test="add-to-cart-${item}"]

the cart badge shows "${count}"
    Get Text    [data-test="shopping-cart-badge"]    ==    ${count}

the user sorts products by "${order}"
    Select Options By    [data-test="product-sort-container"]    value    ${order}

the first product price is "${price}"
    Get Text    [data-test="inventory-item-price"] >> nth=0    ==    ${price}
