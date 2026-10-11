*** Settings ***
Documentation    rf-mcp style API suite with two runtime-only failures (statically clean).
Library         RequestsLibrary
Library         Collections
Suite Setup     Create Session    booker    https://restful-booker.herokuapp.com
Test Tags       api    restful-booker

*** Test Cases ***
Auth Returns Token
    ${creds} =    Create Dictionary    username=admin    password=password123
    ${resp} =    POST On Session    booker    /auth    json=${creds}
    Dictionary Should Contain Key    ${resp.json()}    token

Auth Expected Status Mismatch
    ${creds} =    Create Dictionary    username=admin    password=wrong
    ${resp} =    POST On Session    booker    /auth    json=${creds}    expected_status=401

Post Without Url
    ${creds} =    Create Dictionary    username=admin
    ${resp} =    POST On Session    booker    json=${creds}
