*** Settings ***
Documentation    Test suite generated from session f56c3621-c62e-43f5-86e5-d865c4fddd01 containing 1 test case for automation.
Library         RequestsLibrary
Test Tags       api    crud    restful-booker    automated    generated

*** Test Cases ***
Restful Booker End-to-End Test
    [Documentation]    Full lifecycle: auth, create, read, update, delete, confirm deletion.
    [Tags]    api    restful-booker    crud
    Create Session    rb    https://restful-booker.herokuapp.com
    ${creds} =    Evaluate    {'username': 'admin', 'password': 'password123'}
    ${auth_resp} =    POST On Session    rb    /auth    json=${creds}
    Status Should Be    200    ${auth_resp}
    ${token} =    Set Variable    ${auth_resp.json()['token']}
    ${booking} =    Evaluate    {'firstname': 'Jim', 'lastname': 'Brown', 'totalprice': 111, 'depositpaid': True, 'bookingdates': {'checkin': '2026-01-01', 'checkout': '2026-02-01'}, 'additionalneeds': 'Breakfast'}
    ${create_resp} =    POST On Session    rb    /booking    json=${booking}
    Status Should Be    200    ${create_resp}
    ${booking_id} =    Set Variable    ${create_resp.json()['bookingid']}
    ${read_resp} =    GET On Session    rb    /booking/${booking_id}
    Status Should Be    200    ${read_resp}
    Should Be Equal    ${read_resp.json()['firstname']}    Jim
    Should Be Equal    ${read_resp.json()['lastname']}    Brown
    Should Be Equal As Integers    ${read_resp.json()['totalprice']}    111
    ${update_body} =    Evaluate    {'firstname': 'James', 'lastname': 'Brown-Updated', 'totalprice': 222, 'depositpaid': False, 'bookingdates': {'checkin': '2026-03-01', 'checkout': '2026-04-01'}, 'additionalneeds': 'Lunch'}
    ${auth_headers} =    Evaluate    {'Cookie': 'token=' + $token, 'Content-Type': 'application/json', 'Accept': 'application/json'}
    ${update_resp} =    PUT On Session    rb    /booking/${booking_id}    json=${update_body}    headers=${auth_headers}
    Status Should Be    200    ${update_resp}
    Should Be Equal    ${update_resp.json()['firstname']}    James
    Should Be Equal    ${update_resp.json()['lastname']}    Brown-Updated
    Should Be Equal As Integers    ${update_resp.json()['totalprice']}    222
    ${reread_resp} =    GET On Session    rb    /booking/${booking_id}
    Should Be Equal    ${reread_resp.json()['firstname']}    James
    ${delete_resp} =    DELETE On Session    rb    /booking/${booking_id}    headers=${auth_headers}
    Status Should Be    201    ${delete_resp}
    ${confirm_404} =    GET On Session    rb    /booking/${booking_id}    expected_status=404
    Status Should Be    404    ${confirm_404}
    ${read_body} =    Set Variable    ${read_resp.json()}
    ${update_body_resp} =    Set Variable    ${update_resp.json()}
    ${create_body} =    Set Variable    ${create_resp.json()}
