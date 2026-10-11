*** Test Cases ***
Escaped Form
    Set Test Variable    \${dyn1}    1
    Log    ${dyn1}

Unescaped Form
    Set Test Variable    ${dyn2}    1
    Log    ${dyn2}

Suite Var From Keyword
    Create Token
    Log    ${TOKEN}

Var Statement
    VAR    ${dyn3}    1    scope=SUITE
    Log    ${dyn3}

*** Keywords ***
Create Token
    Set Suite Variable    ${TOKEN}    abc
