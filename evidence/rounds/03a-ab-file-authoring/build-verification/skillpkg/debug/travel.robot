*** Settings ***
Documentation     Toy FAILING suite for verify/verify_round2.py (debug workflow): planted stale locator in
...               "Request Is Confirmed", planted missing wait in "Three Offers Are Listed". Page: ../site/widgets.html
Library           Browser
Library           DateTime
Suite Setup       New Browser    chromium    headless=True
Test Setup        Open Request Form
Test Teardown     Close Page

*** Variables ***
${URL}            file://${CURDIR}/../site/widgets.html

*** Test Cases ***
Request Is Confirmed
    Fill Request    Ann
    Click    id=submit-request
    Wait For Condition    Text    id=status    contains    Request confirmed    timeout=10s
    Get Text    id=status    contains    insurance no

Three Offers Are Listed
    Fill Request    Bob
    Click    data-test=send
    ${offers}=    Get Element Count    css=#results li
    Should Be Equal As Integers    ${offers}    3

Missing Fields Are Reported
    Click    id=send-request
    Get Text    id=status    ==    Missing: name, trip type, destination, class, departure

*** Keywords ***
Open Request Form
    New Page    ${URL}
    Click    text=Accept all

Fill Request
    [Arguments]    ${name}
    Fill Text    id=traveller    ${name}
    Click    text=One way
    Select Options By    id=dest    label    Rome
    Click    id=travel-class
    Click    role=option[name="Economy"]
    ${dep}=    Get Current Date    increment=5 days    result_format=%Y-%m-%d
    Fill Text    id=depart    ${dep}
