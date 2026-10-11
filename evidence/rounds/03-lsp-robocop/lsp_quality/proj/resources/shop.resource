*** Settings ***
Documentation     Shop + booker user keywords (BDD / embedded args) for the live-file experiments.
Library           Browser
Library           RequestsLibrary

*** Variables ***
${PASSWORD}       secret_sauce

*** Keywords ***
The User Opens The Shop
    New Page    ${BASE_URL}

The User Logs In As "${user}"
    Fill Text    id=user-name    ${user}
    Fill Secret    id=password    $PASSWORD
    Click    id=login-button

The User Adds ${n:\d+} Items To The Cart
    ${buttons}=    Get Elements    css=button.btn_inventory
    FOR    ${i}    IN RANGE    ${n}
        Click    ${buttons}[${i}]
    END

The Cart Badge Should Show ${n}
    Get Text    css=.shopping_cart_badge    ==    ${n}

Create Booking Token
    &{cred}=    Create Dictionary    username=admin    password=password123
    ${resp}=    POST    ${API_URL}/auth    json=${cred}
    Set Suite Variable    ${TOKEN}    ${resp.json()}[token]

Create Token With VAR
    VAR    ${TOKEN2}    abc    scope=SUITE
