*** Settings ***
Documentation    Test suite generated from session 3c37977c-d6cd-4d0e-a11e-3b2084c9e165 containing 1 test case for API testing.
Library         RequestsLibrary
Test Tags       automated    generated    api

*** Test Cases ***
Restful Booker Full Lifecycle Test
    [Documentation]    End-to-end test of restful-booker API: authenticate, create, read, update, delete booking
    Create Session    rb    https://restful-booker.herokuapp.com
    Create Dictionary    Content-Type=application/json    Accept=application/json
    ${headers} =    Create Dictionary    Content-Type=application/json    Accept=application/json
    ${headers} =    Create Dictionary    Content-Type=application/json    Accept=application/json
    ${creds} =    Create Dictionary    username=admin    password=password123
    Set Variable    $creds={"username": "admin", "password": "password123"}
    ${headers} =    Create Dictionary    Content-Type=application/json    Accept=application/json
    Set Variable    $headers={"Content-Type": "application/json", "Accept": "application/json"}
    POST On Session    rb    /auth    json=${creds}    headers=${headers}
    ${auth_resp} =    POST On Session    rb    /auth    json=${creds}    headers=${headers}
    ${auth_resp} =    POST On Session    rb    /auth    json=${creds}    headers=${headers}
    Status Should Be    200    ${auth_resp}
    Status Should Be    200    ${auth_resp}
    ${token} =    Set Variable    ${auth_resp.json()["token"]}
    ${booking_data} =    Create Dictionary    firstname=John    lastname=Doe    totalprice=100    depositpaid=true    bookingdates.checkin=2024-01-01    bookingdates.checkout=2024-01-05    additionalneeds=Breakfast
    Sleep    3s
    ${booking_dates} =    Create Dictionary    checkin=2024-01-01    checkout=2024-01-05
    ${booking_data} =    Create Dictionary    firstname=John    lastname=Doe    totalprice=100    depositpaid=true    bookingdates=${booking_dates}    additionalneeds=Breakfast
    ${create_resp} =    POST On Session    rb    /booking    json=${booking_data}    headers=${headers}
    Status Should Be    200    ${create_resp}
    ${booking_id} =    Set Variable    ${create_resp.json()["bookingid"]}
    ${resp_firstname} =    Set Variable    ${create_resp.json()["booking"]["firstname"]}
    Log    Booking created with ID: ${booking_id}, firstname: ${resp_firstname}
    ${get_resp} =    GET On Session    rb    /booking/${booking_id}    headers=${headers}
    Status Should Be    200    ${get_resp}
    ${get_firstname} =    Set Variable    ${get_resp.json()["firstname"]}
    ${get_lastname} =    Set Variable    ${get_resp.json()["lastname"]}
    ${get_price} =    Set Variable    ${get_resp.json()["totalprice"]}
    ${updated_dates} =    Create Dictionary    checkin=2024-02-01    checkout=2024-02-10
    ${updated_data} =    Create Dictionary    firstname=Jane    lastname=Smith    totalprice=200    depositpaid=false    bookingdates=${updated_dates}    additionalneeds=Dinner
    ${auth_headers} =    Create Dictionary    Content-Type=application/json    Accept=application/json    Cookie=token=${token}
    ${update_resp} =    PUT On Session    rb    /booking/${booking_id}    json=${updated_data}    headers=${auth_headers}
    Status Should Be    200    ${update_resp}
    ${updated_firstname} =    Set Variable    ${update_resp.json()["firstname"]}
    ${updated_price} =    Set Variable    ${update_resp.json()["totalprice"]}
    ${delete_resp} =    DELETE On Session    rb    /booking/${booking_id}    headers=${auth_headers}
    Status Should Be    201    ${delete_resp}
    ${verify_resp} =    GET On Session    rb    /booking/${booking_id}    expected_status=404
    Status Should Be    404    ${verify_resp}
