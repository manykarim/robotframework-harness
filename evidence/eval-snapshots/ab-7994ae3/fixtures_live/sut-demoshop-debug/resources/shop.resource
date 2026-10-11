*** Settings ***
Documentation     Keywords for the Flowline Supply demo shop.
Library           Browser

*** Variables ***
${SHOP_URL}           https://demoshop.makrocode.de
${SHOP_SPACE}         __AB_SPACE__
${DEMO_EMAIL}         jamie@flowlinesupply.com
${DEMO_PASSWORD}      demo123
${SPEAKER_ID}         10
${BOTTLE_ID}          12

*** Keywords ***
Open Shop
    New Context
    New Page    ${SHOP_URL}/?space=${SHOP_SPACE}
    Wait For Elements State    css=[data-test=search-input]    visible

Sign In As Demo User
    Click    css=[data-test=signin-button]
    Fill Text    css=[data-test=auth-email-input]    ${DEMO_EMAIL}
    Fill Text    css=[data-test=auth-password-input]    ${DEMO_PASSWORD}
    Click    css=[data-test=auth-submit]

Search For
    [Arguments]    ${term}
    Fill Text    css=[data-test=search-input]    ${term}
    Click    css=[data-test=search-submit]
    Wait For Elements State    id=search-results    visible

Add To Cart From Product Page
    [Arguments]    ${product_id}    ${times}=1
    Go To    ${SHOP_URL}/products/${product_id}
    FOR    ${i}    IN RANGE    ${times}
        Click    css=[data-test=detail-add-to-cart]
    END

Cart Badge Should Show
    [Arguments]    ${expected}
    ${count}=    Get Text    css=[data-test=cart-count]
    Should Be Equal    ${count}    ${expected}

Go To Checkout
    Go To    ${SHOP_URL}/cart
    Click    link:Proceed to checkout
    Wait For Elements State    css=[data-test=checkout-submit]    visible
