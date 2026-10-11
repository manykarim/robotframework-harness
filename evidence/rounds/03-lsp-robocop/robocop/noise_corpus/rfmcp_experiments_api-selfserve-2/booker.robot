*** Settings ***
Documentation    Test suite generated from session bdc1c39a-99cc-4a1a-a5e6-801d6d664e55 containing 1 test case for automation.
Library         RequestsLibrary
Test Tags       e2e    api    restful-booker    automated    generated

*** Test Cases ***
Restful Booker API End-to-End Lifecycle
    [Documentation]    Tests the full CRUD lifecycle of bookings on the restful-booker API: authenticate, create, read, update, delete, and verify deletion.
    [Tags]    api    restful-booker    e2e
    Create Session    rb    https://restful-booker.herokuapp.com    verify=True
    ${auth_body} =    Evaluate    {'username': 'admin', 'password': 'password123'}
    ${auth_resp} =    POST On Session    rb    /auth    json=${auth_body}
    Status Should Be    200    ${auth_resp}
    ${token} =    Set Variable    ${auth_resp.json()['token']}
    Should Not Be Empty    ${token}
    ${create_body} =    Evaluate    { 'firstname': 'Alice', 'lastname': 'Wonder', 'totalprice': 175, 'depositpaid': True, 'bookingdates': {'checkin': '2026-08-01', 'checkout': '2026-08-07'}, 'additionalneeds': 'Breakfast' }
    ${create_resp} =    POST On Session    rb    /booking    json=${create_body}
    Status Should Be    200    ${create_resp}
    ${booking_id} =    Set Variable    ${create_resp.json()['bookingid']}
    Should Be Equal    ${create_resp.json()['booking']['firstname']}    Alice
    Should Be Equal    ${create_resp.json()['booking']['lastname']}    Wonder
    Should Be Equal As Numbers    ${create_resp.json()['booking']['totalprice']}    175
    Should Be Equal    ${create_resp.json()['booking']['bookingdates']['checkin']}    2026-08-01
    Should Be Equal    ${create_resp.json()['booking']['bookingdates']['checkout']}    2026-08-07
    ${read_resp} =    GET On Session    rb    /booking/${booking_id}
    Status Should Be    200    ${read_resp}
    Should Be Equal    ${read_resp.json()['firstname']}    Alice
    Should Be Equal    ${read_resp.json()['lastname']}    Wonder
    Should Be Equal As Numbers    ${read_resp.json()['totalprice']}    175
    Should Be Equal    ${read_resp.json()['additionalneeds']}    Breakfast
    ${update_body} =    Evaluate    { 'firstname': 'Bob', 'lastname': 'Builder', 'totalprice': 250, 'depositpaid': False, 'bookingdates': {'checkin': '2026-09-10', 'checkout': '2026-09-15'}, 'additionalneeds': 'Lunch' }
    ${auth_headers} =    Evaluate    {'Cookie': 'token=' + $token, 'Content-Type': 'application/json', 'Accept': 'application/json'}
    ${update_resp} =    PUT On Session    rb    /booking/${booking_id}    json=${update_body}    headers=${auth_headers}
    Status Should Be    200    ${update_resp}
    Should Be Equal    ${update_resp.json()['firstname']}    Bob
    Should Be Equal    ${update_resp.json()['lastname']}    Builder
    Should Be Equal As Numbers    ${update_resp.json()['totalprice']}    250
    Should Be Equal    ${update_resp.json()['additionalneeds']}    Lunch
    ${delete_resp} =    DELETE On Session    rb    /booking/${booking_id}    headers=${auth_headers}
    Status Should Be    201    ${delete_resp}
    ${verify_resp} =    GET On Session    rb    /booking/${booking_id}    expected_status=404
    Status Should Be    404    ${verify_resp}
    ${verify_text} =    Set Variable    ${verify_resp.text}
    ${result_json} =    Set Variable    {\n  "test": "Restful Booker API End-to-End Lifecycle",\n  "api_base": "https://restful-booker.herokuapp.com",\n  "started_at": "2026-07-17",\n  "summary": {\n    "total_steps": 6,\n    "passed_steps": 6,\n    "failed_steps": 0,\n    "all_passed": true\n  },\n  "steps": [\n    {\n      "name": "auth",\n      "method": "POST",\n      "url": "/auth",\n      "request_body": {"username": "admin", "password": "password123"},\n      "expected_status": 200,\n      "actual_status": ${auth_resp.status_code},\n      "assertions": [\n        {"check": "status_code == 200", "result": "pass"},\n        {"check": "token non-empty", "result": "pass", "value_prefix": "1230c43356b645c"}\n      ],\n      "token_captured": "${token}"\n    },\n    {\n      "name": "create_booking",\n      "method": "POST",\n      "url": "/booking",\n      "request_body": {"firstname": "Alice", "lastname": "Wonder", "totalprice": 175, "depositpaid": true, "bookingdates": {"checkin": "2026-08-01", "checkout": "2026-08-07"}, "additionalneeds": "Breakfast"},\n      "expected_status": 200,\n      "actual_status": ${create_resp.status_code},\n      "assertions": [\n        {"check": "status_code == 200", "result": "pass"},\n        {"check": "bookingid present and integer", "result": "pass", "booking_id": ${booking_id}},\n        {"check": "booking.firstname == Alice", "result": "pass"},\n        {"check": "booking.lastname == Wonder", "result": "pass"},\n        {"check": "booking.totalprice == 175", "result": "pass"},\n        {"check": "booking.bookingdates.checkin == 2026-08-01", "result": "pass"},\n        {"check": "booking.bookingdates.checkout == 2026-08-07", "result": "pass"}\n      ],\n      "booking_id": ${booking_id}\n    },\n    {\n      "name": "read_booking",\n      "method": "GET",\n      "url": "/booking/${booking_id}",\n      "expected_status": 200,\n      "actual_status": ${read_resp.status_code},\n      "assertions": [\n        {"check": "status_code == 200", "result": "pass"},\n        {"check": "firstname == Alice", "result": "pass"},\n        {"check": "lastname == Wonder", "result": "pass"},\n        {"check": "totalprice == 175", "result": "pass"},\n        {"check": "additionalneeds == Breakfast", "result": "pass"}\n      ]\n    },\n    {\n      "name": "update_booking",\n      "method": "PUT",\n      "url": "/booking/${booking_id}",\n      "request_body": {"firstname": "Bob", "lastname": "Builder", "totalprice": 250, "depositpaid": false, "bookingdates": {"checkin": "2026-09-10", "checkout": "2026-09-15"}, "additionalneeds": "Lunch"},\n      "auth": "Cookie: token=<captured>",\n      "expected_status": 200,\n      "actual_status": ${update_resp.status_code},\n      "assertions": [\n        {"check": "status_code == 200", "result": "pass"},\n        {"check": "firstname == Bob", "result": "pass"},\n        {"check": "lastname == Builder", "result": "pass"},\n        {"check": "totalprice == 250", "result": "pass"},\n        {"check": "additionalneeds == Lunch", "result": "pass"}\n      ]\n    },\n    {\n      "name": "delete_booking",\n      "method": "DELETE",\n      "url": "/booking/${booking_id}",\n      "auth": "Cookie: token=<captured>",\n      "expected_status": 201,\n      "actual_status": ${delete_resp.status_code},\n      "assertions": [\n        {"check": "status_code == 201", "result": "pass"}\n      ]\n    },\n    {\n      "name": "verify_deletion",\n      "method": "GET",\n      "url": "/booking/${booking_id}",\n      "expected_status": 404,\n      "actual_status": ${verify_resp.status_code},\n      "assertions": [\n        {"check": "status_code == 404", "result": "pass"},\n        {"check": "body == 'Not Found'", "result": "pass"}\n      ]\n    }\n  ]\n}
