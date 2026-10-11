*** Settings ***
Documentation     NEGATIVE CONTROL (skipped fields): places the order with the prefilled account details
...               instead of entering the given e-mail/name/address/team size/instructions.
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
    Click    css=a.site-nav__link--cart
    Get Text    css=[data-test=cart-item]:has-text("${DISPLAY}")    contains    2 × $389.00
    Get Text    css=[data-test=cart-item]:has-text("${BOTTLE}")    contains    1 × $79.00
    Get Text    css=[data-test=cart-total]    contains    $857.00
    # --- checkout: the signed-in user's saved details are prefilled asynchronously -> wait, then overwrite
    Click    text=Proceed to checkout
    Wait For Elements State    css=.checkout-auth-note    visible
    Get Text    css=[data-test=checkout-subtotal]    ==    $857.00
    Get Text    css=[data-test=checkout-tax]    ==    $59.99
    Get Text    css=[data-test=checkout-total]    ==    $916.99
    Click    css=[data-test=checkout-submit]
    Get Text    css=[data-test=checkout-result]    matches    Order ORD-[0-9A-Z]+ confirmed
