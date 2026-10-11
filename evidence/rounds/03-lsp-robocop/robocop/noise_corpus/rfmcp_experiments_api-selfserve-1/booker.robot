*** Settings ***
Documentation    Test suite generated from session 92f65be5-0b75-4464-95cc-74abb8564eca containing 1 test case for automation.
Library         RequestsLibrary
Test Tags       restful-booker    e2e    api    automated    generated

*** Variables ***
&{creds}            username=admin    password=password123

*** Test Cases ***
Restful Booker E2E Lifecycle
    [Documentation]    End-to-end test of restful-booker.herokuapp.com: authenticate, create, read, update, delete, and confirm deletion of a booking.
    [Tags]    api    e2e    restful-booker
    Create Session    rb    https://restful-booker.herokuapp.com
    ${auth_resp} =    POST On Session    rb    /auth    json={'username': 'admin', 'password': 'password123'}    expected_status=anything
    ${headers} =    Create Dictionary    Content-Type=application/json    Accept=application/json
    ${auth_resp} =    POST On Session    rb    /auth    json={'username': 'admin', 'password': 'password123'}    headers=${headers}    expected_status=anything
    ${creds} =    Create Dictionary    username=admin    password=password123
    ${auth_resp} =    POST On Session    rb    /auth    json=${creds}    headers=${headers}    expected_status=anything
    ${auth_body} =    Set Variable    ${auth_resp.content}
    Status Should Be    200    ${auth_resp}
    ${token} =    Set Variable    ${auth_resp.json()}[token]
    ${dates} =    Create Dictionary    checkin=2026-08-01    checkout=2026-08-05
    ${booking} =    Create Dictionary    firstname=Jane    lastname=Smith    totalprice=250    depositpaid=True    bookingdates=${dates}    additionalneeds=Breakfast
    ${booking} =    Evaluate    {'firstname': 'Jane', 'lastname': 'Smith', 'totalprice': 250, 'depositpaid': True, 'bookingdates': {'checkin': '2026-08-01', 'checkout': '2026-08-05'}, 'additionalneeds': 'Breakfast'}
    ${create_resp} =    POST On Session    rb    /booking    json=${booking}    headers=${headers}
    Status Should Be    200    ${create_resp}
    ${booking_id} =    Set Variable    ${create_resp.json()}[bookingid]
    ${get_resp} =    GET On Session    rb    /booking/${booking_id}    headers=${headers}
    Status Should Be    200    ${get_resp}
    ${read_firstname} =    Set Variable    ${get_resp.json()}[firstname]
    Should Be Equal    ${read_firstname}    Jane
    Should Be Equal    ${get_resp.json()}[lastname]    Smith
    Should Be Equal As Numbers    ${get_resp.json()}[totalprice]    250
    ${auth_headers} =    Create Dictionary    Cookie=token=${token}
    ${update_body} =    Evaluate    {'firstname': 'Janet', 'lastname': 'Doe', 'totalprice': 500, 'depositpaid': False, 'bookingdates': {'checkin': '2026-09-01', 'checkout': '2026-09-10'}, 'additionalneeds': 'Lunch'}
    ${put_resp} =    PUT On Session    rb    /booking/${booking_id}    json=${update_body}    headers=${auth_headers}
    Status Should Be    200    ${put_resp}
    Should Be Equal    ${put_resp.json()}[firstname]    Janet
    ${delete_resp} =    DELETE On Session    rb    /booking/${booking_id}    headers=${auth_headers}
    Status Should Be    201    ${delete_resp}
    ${confirm_resp} =    GET On Session    rb    /booking/${booking_id}    headers=${headers}    expected_status=404
    Status Should Be    404    ${confirm_resp}
