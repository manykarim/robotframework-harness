*** Settings ***
Documentation     User keywords shared by the corpus cases.
Library           Collections

*** Variables ***
${DEFAULT_USER}    standard_user

*** Keywords ***
The User Is Logged In
    [Documentation]    BDD-style user keyword without args.
    Log    logged in as ${DEFAULT_USER}

The User Adds ${count:\d+} Items To The Cart
    [Documentation]    Embedded-argument keyword; count must be digits.
    Log    adding ${count} items

The Cart Should Contain "${item}"
    [Documentation]    Embedded arg with quotes.
    Log    cart contains ${item}

Login As
    [Documentation]    Normal keyword with 1 mandatory and 1 optional arg.
    [Arguments]    ${username}    ${password}=secret_sauce
    Log    ${username}/${password}
