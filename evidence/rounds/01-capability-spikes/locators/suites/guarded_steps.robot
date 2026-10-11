*** Settings ***
Documentation     One-shot guarded steps run through `robotcode robot` (clean console: only GUARD lines).
Library           Browser    timeout=5s
Resource          ../resources/guard.resource
Suite Setup       New Page    https://www.saucedemo.com
Suite Teardown    Close Browser    ALL

*** Variables ***
${GUARD_FAIL}     ${TRUE}

*** Test Cases ***
Guarded Login Attempt
    Guarded    Fill Text    [data-test="username"]    standard_user
    Guarded    Fill Text    [data-test="password"]    secret_sauce
    Guarded    Click    [data-test="login-btn"]
