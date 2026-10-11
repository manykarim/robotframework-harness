*** Settings ***
Resource          ../resources/shop.resource
Suite Teardown    Close Browser    ALL

*** Test Cases ***
Catalog Api Is Up
    ${resp}=    Probe Catalog Endpoint    /health
    Should Be Equal As Integers    ${resp.status_code}    200

Planted Errors
    Launch Storefront
    Clik    id=search-button
    Type Into Product Finder    shoes    extra-arg
    Hit Count Should Be    ${undefined}
