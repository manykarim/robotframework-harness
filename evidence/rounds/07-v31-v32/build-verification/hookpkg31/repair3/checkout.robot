*** Settings ***
Documentation     Checkout suite of the local demo shop (site/). It used to pass; now it fails.
Library           Browser
Suite Setup       New Browser    chromium    headless=True
Test Setup        Open Shop And Sign In    erik
Test Teardown     Close Page

*** Variables ***
${LOGIN_URL}      file://${CURDIR}/../site/login.html

*** Test Cases ***
Greeting Shows The User
    Get Text    id=greeting    ==    Hello, erik

Express Shipping Costs Extra
    Check Checkbox    id=ship-express
    Select Options By    id=country    label    Italy
    Get Text    id=total    ==    Total: 55.00 EUR

Order Is Confirmed
    Click    label[for="ship-standard"]
    Select Options By    id=country    label    Germany
    Fill Text    id=pay-frame >>> id=card    4111
    Click    id=pay-frame >>> id=confirm-card
    Click    data-test=place-order
    Get Text    id=result    contains    confirmed
    Get Text    id=result    contains    Total: 40.00 EUR

*** Keywords ***
Open Shop And Sign In
    [Arguments]    ${user}
    New Page    ${LOGIN_URL}
    Click    text=Accept all
    Fill Text    id=username    ${user}
    Fill Text    id=password    secret
    Click    id=signin-button
