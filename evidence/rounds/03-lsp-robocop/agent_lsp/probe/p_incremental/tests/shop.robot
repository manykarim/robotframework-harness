*** Settings ***
Resource          ../resources/shop.resource
Suite Teardown    Close Browser    ALL

*** Test Cases ***
Catalog Api Is Up
    ${resp}=    Probe Catalog Endpoint    /health
    Should Be Equal As Integers    ${resp.status_code}    200
