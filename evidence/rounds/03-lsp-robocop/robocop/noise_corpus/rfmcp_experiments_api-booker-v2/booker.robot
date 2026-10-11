*** Settings ***
Documentation    Test suite generated from session 040ae4f8-e5dc-4542-a106-a18c1d8f252e containing 1 test case for automation.
Library         RequestsLibrary
Test Tags       automated    generated

*** Test Cases ***
Restful Booker Full Lifecycle
    [Documentation]    End-to-end smoke test of restful-booker.herokuapp.com covering auth, create, read, update, delete, and verify-deleted.
    Create Session    rb    https://restful-booker.herokuapp.com    disable_warnings=1
    ${creds} =    Create Dictionary    username=admin    password=password123
    ${auth_resp} =    POST On Session    rb    /auth    json=${creds}
    Status Should Be    200    ${auth_resp}
    ${token} =    Set Variable    ${auth_resp.json()}[token]
    ${dates} =    Create Dictionary    checkin=2025-01-01    checkout=2025-01-10
    ${booking} =    Create Dictionary    firstname=Jim    lastname=Brown    totalprice=111    depositpaid=True    bookingdates=${dates}    additionalneeds=Breakfast
    ${create_resp} =    POST On Session    rb    /booking    json=${booking}
    Status Should Be    200    ${create_resp}
    ${bookingid} =    Set Variable    ${create_resp.json()}[bookingid]
    ${get_resp} =    GET On Session    rb    /booking/${bookingid}    expected_status=200
    Status Should Be    200    ${get_resp}
    Should Be Equal As Strings    Jim    ${get_resp.json()}[firstname]
    ${update_body} =    Create Dictionary    firstname=James    lastname=Brown    totalprice=222    depositpaid=False    bookingdates=${dates}    additionalneeds=Lunch
    ${auth_headers} =    Create Dictionary    Cookie=token=${token}    Content-Type=application/json    Accept=application/json
    ${put_resp} =    PUT On Session    rb    /booking/${bookingid}    json=${update_body}    headers=${auth_headers}    expected_status=200
    Status Should Be    200    ${put_resp}
    Should Be Equal As Strings    James    ${put_resp.json()}[firstname]
    Should Be Equal As Strings    Lunch    ${put_resp.json()}[additionalneeds]
    ${del_resp} =    DELETE On Session    rb    /booking/${bookingid}    headers=${auth_headers}    expected_status=201
    Status Should Be    201    ${del_resp}
    ${notfound_resp} =    GET On Session    rb    /booking/${bookingid}    expected_status=404
    Status Should Be    404    ${notfound_resp}
