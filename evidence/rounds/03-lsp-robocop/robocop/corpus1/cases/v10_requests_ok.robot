*** Settings ***
Library    RequestsLibrary

*** Test Cases ***
Step
    Create Session    api    https://restful-booker.herokuapp.com
    ${resp}=    POST On Session    api    /auth    json=${{{'username': 'admin'}}}    expected_status=200
