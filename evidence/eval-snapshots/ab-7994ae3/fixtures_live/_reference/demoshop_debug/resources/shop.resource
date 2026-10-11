*** Settings ***
Documentation     Keywords for the Flowline Supply demo shop (REFERENCE: all planted test bugs fixed).
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
    Set Test Variable    ${IN_CART}    0

Sign In As Demo User
    # FIX B1: the header button is data-test="login-button" (was "signin-button")
    Click    css=[data-test=login-button]
    Fill Text    css=[data-test=auth-email-input]    ${DEMO_EMAIL}
    Fill Text    css=[data-test=auth-password-input]    ${DEMO_PASSWORD}
    Click    css=[data-test=auth-submit]
    Wait For Elements State    css=[data-test=account-menu-trigger]    visible

Search For
    [Arguments]    ${term}
    Fill Text    css=[data-test=search-input]    ${term}
    Click    css=[data-test=search-submit]
    Wait For Elements State    id=search-results    visible

Add Product From Search Results
    [Arguments]    ${name}
    # FIX B4: the product also appears in the featured/popular grids -> scope to the results region
    Click    css=#search-results [data-test=product-card]:has-text("${name}") [data-test=add-to-cart-btn]

Add To Cart From Product Page
    [Arguments]    ${product_id}    ${times}=1
    Go To    ${SHOP_URL}/products/${product_id}
    FOR    ${i}    IN RANGE    ${times}
        Click    css=[data-test=detail-add-to-cart]
        Set Test Variable    ${IN_CART}    ${{ str(int($IN_CART) + 1) }}
        # FIX B3: the badge is updated asynchronously - wait for it before navigating on
        Get Text    css=[data-test=cart-count]    ==    ${IN_CART}
    END

Cart Badge Should Show
    [Arguments]    ${expected}
    # FIX B3: retrying assertion instead of a one-shot read
    Get Text    css=[data-test=cart-count]    ==    ${expected}

Go To Checkout
    Go To    ${SHOP_URL}/cart
    # FIX B2: SeleniumLibrary-style "link:" locator is not a Browser selector
    Click    text=Proceed to checkout
    Wait For Elements State    css=[data-test=checkout-submit]    visible
