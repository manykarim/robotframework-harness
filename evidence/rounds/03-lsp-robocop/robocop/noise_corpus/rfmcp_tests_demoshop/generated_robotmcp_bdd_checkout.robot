*** Settings ***
Documentation    BDD-style Robot Framework suite created from stepwise RobotMCP execution against the demo shop.
Library          Browser
Test Tags        bdd    browser    demoshop    checkout    headed    robotmcp    generated

*** Variables ***
${BASE_URL}                  https://demoshop.makrocode.de/
${FIRST_PRODUCT_BUTTON}      button[aria-label="Add Echo Conference Speaker to cart"]
${SECOND_PRODUCT_BUTTON}     button[aria-label="Add Focus Loop Timer to cart"]
${CART_COUNT_BADGE}          [data-cart-count]
${CHECKOUT_LINK}             nav[aria-label="Primary navigation"] a[href="/checkout"]
${CHECKOUT_EMAIL_FIELD}      id=checkout-email
${CHECKOUT_NAME_FIELD}       id=checkout-name
${CHECKOUT_ADDRESS_FIELD}    id=checkout-address
${PLACE_ORDER_BUTTON}        button:has-text("Place order")
${CHECKOUT_ALERT}            [role="alert"] >> visible=true
${CHECKOUT_EMAIL}            jamie.product@example.com
${CHECKOUT_NAME}             Jamie Product
${CHECKOUT_ADDRESS}          123 Flow Street\nSan Francisco, CA

*** Test Cases ***
BDD Demoshop Checkout Stepwise
    [Documentation]    Open the demo shop, add two items with stepwise assertions, complete checkout, and verify the confirmation.
    [Teardown]    Close Browser
    Given the demoshop is open
    When the user adds the first item to the cart
    Then the cart count should be "1"
    When the user adds the second item to the cart
    Then the cart count should be "2"
    When the user completes checkout
    Then checkout should be successful

*** Keywords ***
the demoshop is open
    New Browser    chromium    headless=False
    New Page    ${BASE_URL}    networkidle

the user adds the first item to the cart
    Click    ${FIRST_PRODUCT_BUTTON}

the cart count should be "${expected_count}"
    Wait Until Keyword Succeeds    5 s    200 ms    cart count should eventually be    ${expected_count}

cart count should eventually be
    [Arguments]    ${expected_count}
    ${cart_count}=    Get Text    ${CART_COUNT_BADGE}
    Should Be Equal    ${cart_count}    ${expected_count}

the user adds the second item to the cart
    Click    ${SECOND_PRODUCT_BUTTON}

the user completes checkout
    Click    ${CHECKOUT_LINK}
    Fill Text    ${CHECKOUT_EMAIL_FIELD}    ${CHECKOUT_EMAIL}
    Fill Text    ${CHECKOUT_NAME_FIELD}    ${CHECKOUT_NAME}
    Fill Text    ${CHECKOUT_ADDRESS_FIELD}    ${CHECKOUT_ADDRESS}
    Click    ${PLACE_ORDER_BUTTON}

checkout should be successful
    ${checkout_alert}=    Get Text    ${CHECKOUT_ALERT}
    Should Contain    ${checkout_alert}    confirmed!
