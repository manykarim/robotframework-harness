*** Settings ***
Documentation    End-to-end RobotMCP-generated suite for the Tricentis automobile insurance quote flow.
Library         Browser
Test Tags       tricentis    insurance    automobile    robotmcp    e2e

*** Test Cases ***
Automobile Insurance Quote Via RobotMCP
    [Documentation]    Opens the Tricentis sample app, completes the automobile insurance quote flow, selects a price option, and verifies the quote email succeeds.
    [Tags]    generated    regression
    [Timeout]    3 minutes
    [Teardown]    Close Browser    ALL
    New Browser    browser=chromium    headless=False
    New Page    https://sampleapp.tricentis.com/101/
    Click    div.main-navigation >> id=nav_automobile
    Wait For Elements State    id=make    visible    timeout=10s

    Fill Vehicle Data
    Click    id=nextenterinsurantdata
    Wait For Elements State    id=firstname    visible    timeout=10s

    Fill Insurant Data
    Click    id=nextenterproductdata
    Wait For Elements State    id=startdate    visible    timeout=10s

    Fill Product Data
    Click    id=nextselectpriceoption
    Wait For Load State    domcontentloaded

    Select Price Option
    Click    id=nextsendquote

    Send Quote Request

*** Keywords ***
Fill Vehicle Data
    Select Options By    id=make    label    Toyota
    Fill Text    id=engineperformance    100
    Fill Text    id=dateofmanufacture    12/01/2020
    Select Options By    id=numberofseats    label    4
    Select Options By    id=fuel    label    Petrol
    Fill Text    id=listprice    25000
    Fill Text    id=licenseplatenumber    ABC-1234
    Fill Text    id=annualmileage    10000

Fill Insurant Data
    Fill Text    id=firstname    John
    Fill Text    id=lastname    Smith
    Fill Text    id=birthdate    01/15/1985
    Click With Options    id=gendermale    force=True
    Fill Text    id=streetaddress    123 Main Street
    Select Options By    id=country    label    United States
    Fill Text    id=zipcode    12345
    Fill Text    id=city    New York
    Select Options By    id=occupation    label    Employee
    Click With Options    id=cliffdiving    force=True

Fill Product Data
    Fill Text    id=startdate    12/15/2026
    Select Options By    id=insurancesum    label    5.000.000,00
    Select Options By    id=meritrating    label    Bonus 3
    Select Options By    id=damageinsurance    label    Full Coverage
    Click With Options    id=EuroProtection    force=True
    Select Options By    id=courtesycar    label    Yes

Select Price Option
    Evaluate JavaScript    body    document.getElementById('pricePlans').style.display = 'block'
    Wait For Elements State    id=selectsilver    visible    timeout=10s
    Click With Options    id=selectsilver    force=True

Send Quote Request
    Evaluate JavaScript    body    document.getElementById('sendQuoteForm').style.display = 'block'
    Wait For Elements State    id=email    visible    timeout=10s
    Fill Text    id=email    john.smith@example.com
    Fill Text    id=phone    5551234567
    Fill Text    id=username    johnsmith
    Fill Text    id=password    Secret123!
    Fill Text    id=confirmpassword    Secret123!
    Fill Text    id=Comments    Automated quote request via RobotMCP.
    Click    id=sendemail
    Wait For Elements State    css=button.confirm    visible    timeout=20s
    ${alert_heading} =    Evaluate JavaScript    body    document.querySelector('.sweet-alert h2') ? document.querySelector('.sweet-alert h2').textContent.trim() : ''
    Should Be Equal As Strings    ${alert_heading}    Sending e-mail success!
    Click    css=button.confirm