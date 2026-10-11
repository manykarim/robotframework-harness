*** Settings ***
Documentation     Flowline Supply shop regression suite.
Resource          ../resources/shop.resource
Suite Setup       New Browser    chromium    headless=True
Suite Teardown    Close Browser    ALL
Test Setup        Open Shop
Test Teardown     Close Context

*** Test Cases ***
Demo Account Can Sign In
    Sign In As Demo User
    ${greeting}=    Get Text    css=[data-test=account-menu-trigger]
    Should Contain    ${greeting}    Jamie

Search Finds Standing Desk
    Search For    desk
    Get Element Count    css=#search-results [data-test=product-card]    ==    2
    Get Text    id=search-results    contains    Atlas Standing Desk

Speaker Can Be Added From Search Results
    Search For    speaker
    Click    css=[data-test=product-card]:has-text("Echo Conference Speaker") [data-test=add-to-cart-btn]
    Cart Badge Should Show    1

Cart Badge Counts Every Added Item
    Add To Cart From Product Page    ${SPEAKER_ID}    2
    Add To Cart From Product Page    ${BOTTLE_ID}
    Go To    ${SHOP_URL}/cart
    Cart Badge Should Show    3
    Get Text    css=[data-test=cart-total]    contains    $517.00

Checkout Adds Tax And Confirms Order
    Sign In As Demo User
    Add To Cart From Product Page    ${SPEAKER_ID}    2
    Add To Cart From Product Page    ${BOTTLE_ID}
    Go To Checkout
    Get Text    css=[data-test=checkout-subtotal]    ==    $517.00
    Get Text    css=[data-test=checkout-tax]    ==    $36.19
    Get Text    css=[data-test=checkout-total]    ==    $553.19
    Click    css=[data-test=checkout-submit]
    Get Text    css=[data-test=checkout-result]    matches    Order ORD-\\w+ confirmed
