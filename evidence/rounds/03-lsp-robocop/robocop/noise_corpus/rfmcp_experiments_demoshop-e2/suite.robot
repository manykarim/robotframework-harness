*** Settings ***
Documentation    Test suite generated from session 13ed3322-4bd2-4ea8-890b-18639f68182e containing 1 test case for web automation.
Library         Screenshot
Library         Browser
Test Tags       smoke    demoshop    automated    generated    web

*** Test Cases ***
Demoshop Product Smoke
    [Documentation]    Open Flowline Supply, verify the title, read the first product card title, and click into the product.
    [Tags]    demoshop    smoke
    New Browser    chromium    headless=True    args=["--no-sandbox","--disable-dev-shm-usage","--disable-gpu"]
    New Page    https://demoshop.makrocode.de/
    ${title} =    Get Title
    Should Contain    ${title}    Shop    # Verify page contains '${title}'
    ${product_name} =    Get Text    css=article >> nth=0 >> h3
    Click    css=article >> nth=0 >> h3 a    # Click on css=article >> nth=0 >> h3 a
    Take Screenshot    /artifacts/demoshop.png
    [Teardown]    Close Browser    
