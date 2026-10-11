*** Settings ***
Documentation    Test suite generated from session 5d9ab7d1-da48-478b-a159-b06dd9ee14c3 containing 1 test case for automation.
Library         RequestsLibrary
Test Tags       restful-booker    api    booking-lifecycle    automated    generated

*** Test Cases ***
Restful Booker Full Lifecycle
    [Documentation]    End-to-end booking lifecycle test: authenticate, create, read, update, delete, confirm deletion
    [Tags]    api    restful-booker    booking-lifecycle
    Create Session    rb    https://restful-booker.herokuapp.com
    POST On Session    rb    /auth    data={"username": "admin", "password": "password123"}
    POST On Session    rb    /auth    data={"username": "admin", "password": "password123"}
    POST On Session    rb    /auth    data={"username": "admin", "password": "password123"}
    ${auth_resp} =    POST On Session    rb    /auth    data={"username": "admin", "password": "password123"}
    ${auth_resp} =    POST On Session    rb    /auth    data={"username": "admin", "password": "password123"}
    ${auth_body} =    Create Dictionary    username=admin    password=password123
    ${auth_resp} =    POST On Session    rb    /auth    json=${auth_body}
    Status Should Be    200    ${auth_resp}
    Status Should Be    200    ${auth_resp}
    ${debug} =    Evaluate    str($auth_resp.json())
    Status Should Be    200    ${auth_resp}
    ${debug} =    Evaluate    str($auth_resp.json())
    ${token} =    Set Variable    ${auth_resp.json()["token"]}
    ${booking_body} =    Create Dictionary    firstname=John    lastname=Doe    totalprice=150    depositpaid=true    bookingdates={"checkin": "2024-01-15", "checkout": "2024-01-20"}    additionalneeds=Breakfast
    Sleep    3s
    ${body} =    Create Dictionary    firstname=John    lastname=Doe    totalprice=150    depositpaid=true
    ${dates} =    Create Dictionary    checkin=2024-01-15    checkout=2024-01-20
    VAR    ${BODY}    ${body}    scope=SUITE
    Evaluate    $BODY.update({"bookingdates": $DATES, "additionalneeds": "Breakfast"})
    ${body_debug} =    Evaluate    str($BODY)
    ${booking_payload} =    Evaluate    {'firstname': 'John', 'lastname': 'Doe', 'totalprice': 150, 'depositpaid': True, 'bookingdates': {'checkin': '2024-01-15', 'checkout': '2024-01-20'}, 'additionalneeds': 'Breakfast'}
    ${create_resp} =    POST On Session    rb    /booking    json=${BOOKING_PAYLOAD}
    Status Should Be    200    ${create_resp}
    ${create_debug} =    Evaluate    str($create_resp.json())
    ${get_resp} =    GET On Session    rb    /booking/800
    Status Should Be    200    ${get_resp}
    ${get_debug} =    Evaluate    str($get_resp.json())
    Create Dictionary    firstname=Jane    lastname=Smith    totalprice=200    depositpaid=false
    Create Dictionary    checkin=2024-02-01    checkout=2024-02-05
    ${update_payload} =    Evaluate    {'firstname': 'Jane', 'lastname': 'Smith', 'totalprice': 200, 'depositpaid': False, 'bookingdates': {'checkin': '2024-02-01', 'checkout': '2024-02-05'}, 'additionalneeds': 'Lunch'}
    ${auth_headers} =    Create Dictionary    Cookie=token=759df3cd1641da0
    ${update_resp} =    PUT On Session    rb    /booking/800    json=${UPDATE_PAYLOAD}    headers=${AUTH_HEADERS}
    Status Should Be    200    ${update_resp}
    ${update_debug} =    Evaluate    str($update_resp.json())
    ${delete_resp} =    DELETE On Session    rb    /booking/800    headers=${AUTH_HEADERS}
    Status Should Be    201    ${delete_resp}
    ${confirm_resp} =    GET On Session    rb    /booking/800    expected_status=404
    Status Should Be    404    ${confirm_resp}
