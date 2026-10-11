*** Settings ***
Documentation     NEGATIVE CONTROL (hard-coded assertion targets): drives the journey, but asserts the price and
...               the confirmation against hard-coded variables instead of reading them from the page.
Library           Browser
Library           DateTime
Suite Setup       New Browser    chromium    headless=True
Suite Teardown    Close Browser    ALL

*** Variables ***
${PLATINUM_PRICE}    509.00
${CONFIRMATION}      Sending e-mail success!

*** Test Cases ***
Automobile Quote Can Be Sent
    New Page    http://sampleapp.tricentis.com/
    # the Automobile link sets the vehicle-type cookie; app.php opened directly shows a generic form
    Click    css=#nav_automobile >> nth=0
    # the form only switches to automobile mode (removes truck/motorcycle fields) in a window-load handler
    Get Text    id=selectedinsurance    ==    Automobile Insurance
    # --- Enter Vehicle Data
    Select Options By    id=make    label    BMW
    Type Text    id=engineperformance    110
    Type Text    id=dateofmanufacture    06/15/2020
    Select Options By    id=numberofseats    label    5
    Select Options By    id=fuel    label    Petrol
    Type Text    id=listprice    30000
    Type Text    id=licenseplatenumber    RF2026
    Type Text    id=annualmileage    12000
    Click    id=nextenterinsurantdata
    # --- Enter Insurant Data (radios/checkboxes are hidden inputs styled by their label)
    Type Text    id=firstname    Ada
    Type Text    id=lastname    Lovelace
    Type Text    id=birthdate    12/10/1985
    Click    css=label:has(#genderfemale)
    Type Text    id=streetaddress    Main Street 1
    Select Options By    id=country    label    Germany
    Type Text    id=zipcode    10115
    Type Text    id=city    Berlin
    Select Options By    id=occupation    label    Employee
    Click    css=label:has(#skydiving)
    Click    id=nextenterproductdata
    # --- Enter Product Data (start date must be more than one month in the future)
    ${start}=    Get Current Date    increment=60 days    result_format=%m/%d/%Y
    Type Text    id=startdate    ${start}
    Select Options By    id=insurancesum    value    7000000
    Select Options By    id=meritrating    label    Bonus 1
    Select Options By    id=damageinsurance    label    No Coverage
    Click    css=label:has(#EuroProtection)
    Select Options By    id=courtesycar    label    Yes
    Click    id=nextselectpriceoption
    # --- Select Price Option
    ${price}=    Set Variable    ${PLATINUM_PRICE}
    Should Be Equal    ${price}    509.00
    Click    css=label:has(#selectplatinum)
    Click    id=nextsendquote
    # --- Send Quote
    Type Text    id=email    ada@example.com
    Type Text    id=phone    0301234567
    Type Text    id=username    adal
    Type Text    id=password    Secret123
    Type Text    id=confirmpassword    Secret123
    Click    id=sendemail
    # the confirmation pops up after ~8 s (server-side delay)
    Sleep    12s
    ${message}=    Set Variable    ${CONFIRMATION}
    Should Be Equal    ${message}    Sending e-mail success!
