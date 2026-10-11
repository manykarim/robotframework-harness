*** Settings ***
Documentation     Keywords for the Tricentis Vehicle Insurance sample app (truck quotes). REFERENCE: planted bugs fixed.
Library           Browser
Library           DateTime

*** Variables ***
${APP_URL}            http://sampleapp.tricentis.com/
${QUOTE_EMAIL}        grace@example.com

*** Keywords ***
Open Quote Browser
    New Browser    chromium    headless=True

Start Truck Quote
    New Context
    New Page    ${APP_URL}
    Click    css=#nav_truck >> nth=0
    # the form switches to truck mode in a window-load handler
    Get Text    id=selectedinsurance    ==    Truck Insurance

Enter Truck Vehicle Data
    # FIX B4: SeleniumLibrary keyword -> Browser keyword
    Select Options By    id=make    label    Volvo
    Fill Text    id=engineperformance    250
    Fill Text    id=dateofmanufacture    03/01/2019
    Select Options By    id=numberofseats    label    2
    Select Options By    id=fuel    label    Diesel
    Fill Text    id=payload    800
    Fill Text    id=totalweight    7500
    Fill Text    id=listprice    85000
    Fill Text    id=licenseplatenumber    TRK-778
    Fill Text    id=annualmileage    60000
    Click    id=nextenterinsurantdata

Enter Insurant Data
    Fill Text    id=firstname    Grace
    Fill Text    id=lastname    Hopper
    Fill Text    id=birthdate    12/09/1976
    # FIX B2: radios/checkboxes are hidden inputs (left:-9999px) styled by their label
    Click    css=label:has(#genderfemale)
    Fill Text    id=streetaddress    Harbour Road 7
    Select Options By    id=country    label    Netherlands
    Fill Text    id=zipcode    1011
    Fill Text    id=city    Amsterdam
    Select Options By    id=occupation    label    Selfemployed
    Click    css=label:has(#other)
    Click    id=nextenterproductdata

Enter Product Data
    # FIX B1: start date must be more than one month in the future -> compute it
    ${start}=    Get Current Date    increment=60 days    result_format=%m/%d/%Y
    Fill Text    id=startdate    ${start}
    Select Options By    id=insurancesum    value    10000000
    Select Options By    id=damageinsurance    label    Full Coverage
    Click    css=label:has(#LegalDefenseInsurance)

Open Price Options
    Click    id=nextselectpriceoption

Choose Price Option
    [Arguments]    ${option}
    Click    css=label:has(#select${option})
    Click    id=nextsendquote

Send Quote By Email
    Fill Text    id=email    ${QUOTE_EMAIL}
    Fill Text    id=phone    0201234567
    Fill Text    id=username    ghopper
    Fill Text    id=password    Cobol1959
    Fill Text    id=confirmpassword    Cobol1959
    Click    id=sendemail
    # FIX B3: the confirmation pops up only after ~8-9 s (server-side delay)
    Wait For Elements State    css=.sweet-alert    visible    timeout=40s
