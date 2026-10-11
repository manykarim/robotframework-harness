*** Settings ***
Library    RequestsLibrary
Library    Collections

*** Test Cases ***
Status Type Mismatch
    Create Session    rb    https://restful-booker.herokuapp.com
    ${resp}=    GET On Session    rb    /ping    expected_status=201
    Should Be Equal    ${resp.status_code}    201

Missing Booking
    Create Session    rb    https://restful-booker.herokuapp.com
    GET On Session    rb    /booking/99999999

Dict Dot Access
    &{creds}=    Create Dictionary    username=admin    password=password123
    ${resp}=    POST On Session    rb    /auth    json=${creds}
    Log    ${resp.json().token}
