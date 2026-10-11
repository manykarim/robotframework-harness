*** Settings ***
Documentation    Broken variant of the rf-mcp generated restful-booker suite (P1..P5).
Library         RequestsLibrary
Suite Setup     Create Session    booker    https://restful-booker.herokuapp.com
Test Tags       api    restful-booker    e2e

*** Test Cases ***
Authenticate Admin
    ${auth_data} =    Create Dictionary    username=admin    password=password123
    ${auth_response} =    POST On Session    booker    json=${auth_data}
    Should Be Equal As Strings    ${auth_response.status_code}    200
    Dictionary Should Contain Key    ${auth_response.json()}    token
    Set Suite Variable    ${TOKEN}    ${auth_response.json()}[token]

Delete Booking While Authenticated
    ${delete_headers} =    Create Dictionary    Cookie=token=${TOKEN}
    ${delete_response} =    DELETE On Session    booker    /booking/1    expected_status=201    headers=${delete_headers}
    Should Be Equal As Strings    ${delete_response.status_code}    201    strip_space=True
    ${verify} =    GET On Session    booker    /booking/1    expected_status=404
    Status Should Be    404    ${verify}    msg    extra
