*** Test Cases ***
Inline Ignore
    Set Test Variable    \${dyn1}    1
    Log    ${dyn1}    # robotcode: ignore[VariableNotFound]
