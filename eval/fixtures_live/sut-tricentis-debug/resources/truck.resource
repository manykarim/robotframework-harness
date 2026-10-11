*** Settings ***
Documentation     Keywords for the Tricentis Vehicle Insurance sample app (truck quotes).
Library           Browser

*** Variables ***
${APP_URL}            http://sampleapp.tricentis.com/
${START_DATE}         01/15/2025
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
    Select From List By Label    id=make    Volvo
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
    Click    id=genderfemale
    Fill Text    id=streetaddress    Harbour Road 7
    Select Options By    id=country    label    Netherlands
    Fill Text    id=zipcode    1011
    Fill Text    id=city    Amsterdam
    Select Options By    id=occupation    label    Selfemployed
    Click    id=other
    Click    id=nextenterproductdata

Enter Product Data
    Fill Text    id=startdate    ${START_DATE}
    Select Options By    id=insurancesum    value    10000000
    Select Options By    id=damageinsurance    label    Full Coverage
    Click    id=LegalDefenseInsurance

Open Price Options
    Click    id=nextselectpriceoption

Choose Price Option
    [Arguments]    ${option}
    Click    id=select${option}
    Click    id=nextsendquote

Send Quote By Email
    Fill Text    id=email    ${QUOTE_EMAIL}
    Fill Text    id=phone    0201234567
    Fill Text    id=username    ghopper
    Fill Text    id=password    Cobol1959
    Fill Text    id=confirmpassword    Cobol1959
    Click    id=sendemail
    Wait For Elements State    css=.sweet-alert    visible    timeout=5s
