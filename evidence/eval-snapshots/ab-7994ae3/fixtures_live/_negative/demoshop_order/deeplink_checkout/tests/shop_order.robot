*** Settings ***
Documentation     NEGATIVE CONTROL (deep link): jumps straight to /checkout instead of going through the cart.
Library           Browser
Suite Setup       New Browser    chromium    headless=True
Suite Teardown    Close Browser    ALL

*** Variables ***
${SHOP_URL}       https://demoshop.makrocode.de/?space=__AB_SPACE__
${DISPLAY}        Horizon Portable Display
${BOTTLE}         Cascade Water Bottle

*** Test Cases ***
Customer Orders Displays And A Bottle
    New Page    ${SHOP_URL}
    Wait For Elements State    css=[data-test=search-input]    visible
    # --- sign in with the demo account the sign-in dialog suggests (Cloudflare decodes the e-mail at runtime)
    Click    css=[data-test=login-button]
    Get Text    css=#auth-modal .auth-modal__hint    contains    jamie@flowlinesupply.com / demo123
    Fill Text    css=[data-test=auth-email-input]    jamie@flowlinesupply.com
    Fill Text    css=[data-test=auth-password-input]    demo123
    Click    css=[data-test=auth-submit]
    Wait For Elements State    css=[data-test=account-menu-trigger]    visible
    # --- search + add to cart (the badge updates asynchronously -> retrying assertion after each click)
    Fill Text    css=[data-test=search-input]    ${DISPLAY}
    Click    css=[data-test=search-submit]
    Get Text    id=search-results    contains    ${DISPLAY}
    Click    css=#search-results [data-test=product-card]:has-text("${DISPLAY}") [data-test=add-to-cart-btn]
    Get Text    css=[data-test=cart-count]    ==    1
    Click    css=#search-results [data-test=product-card]:has-text("${DISPLAY}") [data-test=add-to-cart-btn]
    Get Text    css=[data-test=cart-count]    ==    2
    Fill Text    css=[data-test=search-input]    ${BOTTLE}
    Click    css=[data-test=search-submit]
    Get Text    id=search-results    contains    ${BOTTLE}
    Click    css=#search-results [data-test=product-card]:has-text("${BOTTLE}") [data-test=add-to-cart-btn]
    Get Text    css=[data-test=cart-count]    ==    3
    # --- cart
    # --- checkout: the signed-in user's saved details are prefilled asynchronously -> wait, then overwrite
    Go To    https://demoshop.makrocode.de/checkout
    Wait For Elements State    css=.checkout-auth-note    visible
    Get Property    css=[data-test=checkout-email-input]    value    ==    jamie@flowlinesupply.com
    Fill Text    css=[data-test=checkout-email-input]    morgan.lee@example.com
    Fill Text    css=[data-test=checkout-name-input]    Morgan Lee
    Fill Text    css=[data-test=checkout-address-input]    42 Harbor Lane, Portland, OR 97201
    Fill Text    css=[data-test=checkout-team-size-input]    8
    Fill Text    css=[data-test=checkout-notes-input]    Leave at the front desk
    Get Text    css=[data-test=checkout-subtotal]    ==    $857.00
    Get Text    css=[data-test=checkout-tax]    ==    $59.99
    Get Text    css=[data-test=checkout-total]    ==    $916.99
    Click    css=[data-test=checkout-submit]
    Get Text    css=[data-test=checkout-result]    matches    Order ORD-[0-9A-Z]+ confirmed
    Get Text    css=[data-test=checkout-result]    contains    confirmation email to morgan.lee@example.com
