*** Settings ***
Documentation    Test suite generated from session 8dd2de9a-d0cd-4842-bb35-ab59f9df27ef containing 1 test case for automation.
Library         RequestsLibrary
Test Tags       automated    generated

*** Variables ***
&{auth_headers}     Cookie=token=1ee0a00508313f9
&{booking}          firstname=Jim    lastname=Brown    totalprice=150    depositpaid=True    bookingdates={'checkin': '2026-07-20', 'checkout': '2026-07-25'}    additionalneeds=Breakfast
&{creds}            username=admin    password=password123
&{headers}          Content-Type=application/json
&{token_headers}    Cookie=token=e96a93d740ab872
&{update_booking}   firstname=Jim    lastname=Brown    totalprice=200    depositpaid=True    bookingdates={'checkin': '2026-07-20', 'checkout': '2026-07-26'}    additionalneeds=Breakfast + Parking

*** Test Cases ***
Restful Booker Booking Lifecycle
    [Documentation]    End-to-end booking lifecycle test using restful-booker.herokuapp.com API
    Create Session    rb    https://restful-booker.herokuapp.com
    Create Session    rb    https://restful-booker.herokuapp.com
    POST On Session    rb    /auth    json=${creds}    headers=${headers}
    ${auth_resp} =    POST On Session    rb    /auth    json=${creds}    headers=${headers}
    ${create_resp} =    POST On Session    rb    /booking    json=${booking}    headers=${headers}
    Create Session    rb    https://restful-booker.herokuapp.com
    ${auth_resp} =    POST On Session    rb    /auth    json=${creds}    headers=${headers}
    Status Should Be    200    ${auth_resp}
    ${token} =    Set Variable    ${auth_resp.json()["token"]}
    Status Should Be    200    ${auth_resp}
    ${token} =    Set Variable    ${auth_resp.json()["token"]}
    Evaluate    {"Cookie": "token=" + $token}
    ${auth_headers} =    Evaluate    {"Cookie": "token=" + $token}
    Create Dictionary    Cookie=token=${token}
    Create Dictionary    Cookie=token=${token}
    ${create_resp} =    POST On Session    rb    /booking    json=${booking}    headers=${headers}
    Status Should Be    200    ${create_resp}
    ${booking_id} =    Set Variable    ${create_resp.json()["bookingid"]}
    ${created_firstname} =    Set Variable    ${create_resp.json()["booking"]["firstname"]}
    Status Should Be    200    ${create_resp}
    ${booking_id} =    Set Variable    ${create_resp.json()["bookingid"]}
    ${read_resp} =    GET On Session    rb    /booking/${booking_id}
    GET On Session    rb    /booking/${booking_id}
    ${created_firstname} =    Set Variable    ${create_resp.json()["booking"]["firstname"]}
    ${read_resp} =    GET On Session    rb    /booking/${booking_id}
    Status Should Be    200    ${read_resp}
    ${read_firstname} =    Set Variable    ${read_resp.json()["firstname"]}
    ${read_totalprice} =    Set Variable    ${read_resp.json()["totalprice"]}
    Status Should Be    200    ${read_resp}
    ${read_firstname} =    Set Variable    ${read_resp.json()["firstname"]}
    ${read_totalprice} =    Set Variable    ${read_resp.json()["totalprice"]}
    ${token_headers} =    Evaluate    {"Cookie": "token=" + $token}
    ${update_resp} =    PUT On Session    rb    /booking/${booking_id}    json=${update_booking}    headers=${token_headers}
    Status Should Be    200    ${update_resp}
    ${updated_totalprice} =    Set Variable    ${update_resp.json()["totalprice"]}
    ${delete_resp} =    DELETE On Session    rb    /booking/${booking_id}    headers=${token_headers}
    Status Should Be    201    ${delete_resp}
    ${confirm_resp} =    GET On Session    rb    /booking/${booking_id}    expected_status=404
    Status Should Be    404    ${confirm_resp}
