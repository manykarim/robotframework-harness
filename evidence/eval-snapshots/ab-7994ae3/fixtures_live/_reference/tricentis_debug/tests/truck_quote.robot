*** Settings ***
Documentation     Truck insurance quote regression suite (Tricentis Vehicle Insurance sample app).
Resource          ../resources/truck.resource
Suite Setup       Open Quote Browser
Suite Teardown    Close Browser    ALL
Test Setup        Start Truck Quote
Test Teardown     Close Context

*** Test Cases ***
Product Data Is Accepted
    Enter Truck Vehicle Data
    Enter Insurant Data
    Enter Product Data
    Get Text    css=#enterproductdata .counter    ==    0

Truck Price Table Is Calculated
    Enter Truck Vehicle Data
    Enter Insurant Data
    Enter Product Data
    Open Price Options
    Get Text    id=selectgold_price    ==    1,784.00
    Get Text    id=selectplatinum_price    ==    3,501.00

Truck Quote Can Be Sent
    Enter Truck Vehicle Data
    Enter Insurant Data
    Enter Product Data
    Open Price Options
    Choose Price Option    gold
    Send Quote By Email
    Get Text    css=.sweet-alert h2    ==    Sending e-mail success!
