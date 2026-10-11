*** Settings ***
Documentation    Test suite generated from session booker_test containing 1 test case for API testing.
Library         RequestsLibrary
Test Tags       automated    generated    api

*** Variables ***
${BASE_URL}         https://restful-booker.herokuapp.com

*** Test Cases ***
Restful Booker API Lifecycle Test
    [Documentation]    End-to-end test of restful-booker API - full booking lifecycle
    Create Session    rb    https://restful-booker.herokuapp.com
    ${creds} =    Set Variable    {"username": "admin", "password": "password123"}
    ${headers} =    Create Dictionary    Content-Type    application/json
    ${auth_resp} =    POST On Session    rb    /auth    data={"username": "admin", "password": "password123"}    headers=${headers}
    ${token} =    Set Variable    ${auth_resp.json()["token"]}
    Status Should Be    200    ${auth_resp}
    ${booking_data} =    Evaluate    {'firstname': 'John', 'lastname': 'Doe', 'totalprice': 100, 'depositpaid': True, 'bookingdates': {'checkin': '2024-01-01', 'checkout': '2024-01-05'}, 'additionalneeds': 'Breakfast'}
    ${create_resp} =    POST On Session    rb    /booking    json=${booking_data}
    ${booking_id} =    Set Variable    ${create_resp.json()["bookingid"]}
    Status Should Be    200    ${create_resp}
    ${get_resp} =    GET On Session    rb    /booking/${booking_id}
    Status Should Be    200    ${get_resp}
    ${firstname} =    Set Variable    ${get_resp.json()["firstname"]}
    ${update_data} =    Evaluate    {'firstname': 'Jane', 'lastname': 'Smith', 'totalprice': 200, 'depositpaid': False, 'bookingdates': {'checkin': '2024-02-01', 'checkout': '2024-02-10'}, 'additionalneeds': 'Dinner'}
    ${headers} =    Create Dictionary    Content-Type    application/json    Accept    application/json
    ${cookie_str} =    Catenate    token=    ${token}
    ${headers} =    Create Dictionary    Content-Type    application/json    Accept    application/json    Cookie    ${cookie_str}
    ${update_resp} =    PUT On Session    rb    /booking/${booking_id}    json=${update_data}    headers=${headers}
    Status Should Be    200    ${update_resp}
    ${updated_firstname} =    Set Variable    ${update_resp.json()["firstname"]}
    ${updated_price} =    Set Variable    ${update_resp.json()["totalprice"]}
    ${delete_resp} =    DELETE On Session    rb    /booking/${booking_id}    headers=${headers}
    Status Should Be    201    ${delete_resp}
    ${confirm_resp} =    GET On Session    rb    /booking/${booking_id}    expected_status=404
