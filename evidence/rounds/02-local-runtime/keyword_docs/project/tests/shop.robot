*** Settings ***
Library     Browser
Library     RequestsLibrary
Library     ../libs/ShopApi.py    base_url=http://localhost:8080
Resource    ../resources/shop.resource

*** Test Cases ***
Smoke
    Login As User    demo    secret
