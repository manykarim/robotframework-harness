*** Settings ***
Documentation    End-to-end test of the Flowline Supply web shop: open the home page, navigate to a product, add it to cart, open the cart, and verify the item is present.
Library          Browser
Library          Screenshot
Test Tags        automated    generated    web    shop    e2e
Suite Setup      Open Shop

*** Variables ***
${BROWSER_ARGS}        --no-sandbox
${SHOP_URL}            https://demoshop.makrocode.de/
${CART_COUNTER_LINK}   css=nav a[href="/cart"]

*** Keywords ***
Open Shop
    New Browser    browser=chromium    headless=True    chromiumSandbox=False
    New Page       ${SHOP_URL}

*** Test Cases ***
Web Shop E2E Test
    [Documentation]    Add the Aurora Neural Headphones product to the cart and verify it appears on the cart page.
    Click                 text=Aurora Neural Headphones
    ${page_title} =       Get Title
    Click                 css=button[data-product="1"][data-event="add_to_cart"]
    Click                 ${CART_COUNTER_LINK}
    ${cart_item_name} =   Get Text    css=article h3
    ${cart_link_text} =   Get Text    ${CART_COUNTER_LINK}
    Should Be Equal       ${cart_item_name}              Aurora Neural Headphones
    Should Be Equal       ${cart_link_text}              Cart 1
    Take Screenshot       filename=/artifacts/demoshop.png    fullPage=True
