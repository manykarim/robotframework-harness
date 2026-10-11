*** Settings ***
Documentation     Reference solution (hidden from agents): nested JSON aggregation over HTTP.
Library           RequestsLibrary
Library           Collections
Suite Setup       Start Server
Suite Teardown    Stop Orders Server

*** Test Cases ***
Order Aggregates Are Correct
    ${resp}=    GET    ${BASE_URL}/orders    expected_status=200
    ${orders}=    Set Variable    ${resp.json()}
    ${revenue}=    Set Variable    ${0}
    ${alice_qty}=    Set Variable    ${0}
    ${cancelled}=    Set Variable    ${0}
    FOR    ${order}    IN    @{orders}
        IF    $order['status'] == 'cancelled'
            ${cancelled}=    Evaluate    ${cancelled} + 1
            CONTINUE
        END
        FOR    ${item}    IN    @{order}[items]
            ${discount}=    Evaluate    $item.get('discount', 0) or 0
            ${revenue}=    Evaluate    ${revenue} + $item['price'] * $item['qty'] * (1 - ${discount})
            IF    $order['customer'] == 'Alice'
                ${alice_qty}=    Evaluate    ${alice_qty} + $item['qty']
            END
        END
    END
    Should Be Equal As Numbers    ${revenue}    114
    Should Be Equal As Numbers    ${alice_qty}    6
    Should Be Equal As Numbers    ${cancelled}    1

*** Keywords ***
Start Server
    Import Library    ${CURDIR}/../resources/OrdersServer.py
    ${url}=    Start Orders Server    ${CURDIR}/../data/orders.json
    Set Suite Variable    ${BASE_URL}    ${url}
