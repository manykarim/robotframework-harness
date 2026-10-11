*** Settings ***
Documentation    Test suite generated from session b7e7e16b-6e81-4267-8590-bb06fc5b2893 containing 1 test case for automation.
Library         RequestsLibrary
Test Tags       automated    generated

*** Variables ***
&{auth_headers}     Content-Type=application/json    Accept=application/json    Cookie=token=675b4d4cfea1fb0
&{booking_data}     firstname=John    lastname=Doe    totalprice=100    depositpaid=True    bookingdates={'checkin': '2024-01-01', 'checkout': '2024-01-05'}    additionalneeds=Breakfast
&{creds}            username=admin    password=password123
&{headers}          Content-Type=application/json    Accept=application/json
&{update_data}      firstname=John    lastname=Smith    totalprice=200    depositpaid=False    bookingdates={'checkin': '2024-02-01', 'checkout': '2024-02-07'}    additionalneeds=Lunch

*** Test Cases ***
Restful Booker API End To End
    [Documentation]    Test case that verifies result, verifies result, verifies result, verifies result, verifies result, verifies result.
    Create Session    rb    https://restful-booker.herokuapp.com
    Create Dictionary    Content-Type=application/json    Accept=application/json
    Create Dictionary    username=admin    password=password123
    Create Dictionary    Content-Type=application/json    Accept=application/json
    Create Dictionary    username=admin    password=password123
    POST On Session    rb    /auth    json=${creds}    headers=${headers}
    POST On Session    rb    /auth    json=${creds}    headers=${headers}
    POST On Session    rb    /auth    json=${creds}    headers=${headers}
    ${auth_resp} =    POST On Session    rb    /auth    json=${creds}    headers=${headers}
    Status Should Be    200    ${auth_resp}
    VAR    ${token}    ${auth_resp.json()["token"]}    scope=TEST
    Create Dictionary    firstname=John    lastname=Doe    totalprice=100    depositpaid=true    checkin=2024-01-01    checkout=2024-01-05    additionalneeds=Breakfast
    ${create_resp} =    POST On Session    rb    /booking    json=${booking_data}    headers=${headers}
    Status Should Be    200    ${create_resp}
    VAR    ${booking_id}    ${create_resp.json()["bookingid"]}    scope=TEST
    ${get_resp} =    GET On Session    rb    /booking/${booking_id}    headers=${headers}
    Status Should Be    200    ${get_resp}
    VAR    ${firstname}    ${get_resp.json()["firstname"]}    scope=TEST
    ${update_resp} =    PUT On Session    rb    /booking/${booking_id}    json=${update_data}    headers=${auth_headers}
    Status Should Be    200    ${update_resp}
    VAR    ${lastname}    ${update_resp.json()["lastname"]}    scope=TEST
    ${delete_resp} =    DELETE On Session    rb    /booking/${booking_id}    headers=${auth_headers}
    Status Should Be    201    ${delete_resp}
    ${confirm_delete_resp} =    GET On Session    rb    /booking/${booking_id}    headers=${headers}    expected_status=404
    Status Should Be    404    ${confirm_delete_resp}
