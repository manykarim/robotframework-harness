*** Settings ***
Documentation     Page objects for the demo shop. Use ONLY these keywords in tests.
Library           Browser
Library           RequestsLibrary
Library           ShopHelpers

*** Variables ***
${SHOP_URL}         http://127.0.0.1:8765/shop.html
${API_URL}          http://127.0.0.1:8765
${FINDER_INPUT}     css=input#product-finder
${HIT_ROWS}         css=ul#hits > li

*** Keywords ***
Launch Storefront
    [Documentation]    Opens a fresh headless browser on the shop start page.
    [Arguments]    ${headless}=True
    New Browser    chromium    headless=${headless}
    New Page    ${SHOP_URL}

Type Into Product Finder
    [Documentation]    Types ``term`` into the product finder box and submits it with Enter.
    [Arguments]    ${term}
    Fill Text    ${FINDER_INPUT}    ${term}
    Keyboard Key    press    Enter

Hit Count Should Be
    [Documentation]    Asserts that exactly ``expected`` result rows are shown.
    [Arguments]    ${expected}
    Get Element Count    ${HIT_ROWS}    ==    ${expected}

Probe Catalog Endpoint
    [Documentation]    GETs ``path`` from the catalog API and returns the response.
    [Arguments]    ${path}    ${expected_status}=200
    Create Session    catalog    ${API_URL}
    ${resp}=    GET On Session    catalog    ${path}    expected_status=${expected_status}
    RETURN    ${resp}
