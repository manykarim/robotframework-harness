*** Settings ***
Library    RequestsLibrary
Library    Collections

*** Test Cases ***
Booker Create And Get
    Create Session    booker    https://restful-booker.herokuapp.com    headers={"Accept": "application/json"}
    ${auth}=    Create Dictionary    username=admin    password=password123
    ${resp}=    POST On Session    booker    /auth    json=${auth}
    ${token}=    Set Variable    ${resp.json()}[token]
    ${dates}=    Create Dictionary    checkin=2026-10-01    checkout=2026-10-05
    ${body}=    Create Dictionary    firstname=Robo    lastname=Step    totalprice=${123}    depositpaid=${True}    bookingdates=${dates}    additionalneeds=Breakfast
    ${resp}=    POST On Session    booker    /booking    json=${body}
    ${id}=    Set Variable    ${resp.json()}[bookingid]
    ${resp}=    GET On Session    booker    /booking/${id}
    Should Be Equal    ${resp.json()}[firstname]    Robo
    Dictionary Should Contain Key    ${resp.json()}    bookingdates
    ${h}=    Create Dictionary    Cookie=token=${token}
    DELETE On Session    booker    /booking/${id}    headers=${h}    expected_status=201
