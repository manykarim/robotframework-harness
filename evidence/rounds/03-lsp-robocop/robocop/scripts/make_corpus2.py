"""Round 3 / robocop: agent-typical outdated or incorrect RF syntax corpus.

Writes ../corpus2/cases/*.robot, ../corpus2/robot.toml and ../corpus2/manifest.json.
kind:
  deprecated  - still runs on RF 7.5, but outdated syntax an agent learned from old docs
  error       - fails parsing / keyword lookup / execution
  style       - valid, only a style question (should NOT be reported as an error)
  runtime     - only fails at runtime (static tools are not expected to catch it)
runnable: BuiltIn-only cases are executed for real; others only dry-run.
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent / "corpus2"
CASES = ROOT / "cases"

T = "*** Test Cases ***\n"

C: dict[str, tuple[str, str, bool, str]] = {}


def case(cid: str, kind: str, cls: str, text: str, runnable: bool = True) -> None:
    C[cid] = (kind, cls, runnable, text)


case("d01_run_keyword_if", "deprecated", "Run Keyword If", T + """Check Value
    ${x}=    Set Variable    5
    Run Keyword If    ${x} > 3    Log    big    ELSE    Log    small
    Run Keyword Unless    ${x} > 3    Log    not big
""")

case("d02_return_setting", "deprecated", "[Return] setting", T + """Use Kw
    ${v}=    Get Five
    Should Be Equal As Integers    ${v}    5

*** Keywords ***
Get Five
    ${r}=    Evaluate    2 + 3
    [Return]    ${r}
""")

case("d03_old_for_syntax", "error", ":FOR loop (RF<=3.1)", T + """Loop
    :FOR    ${i}    IN RANGE    3
    \\    Log    ${i}
""")

case("d04_exit_for_loop", "deprecated", "Exit For Loop / Continue For Loop", T + """Loop
    FOR    ${i}    IN RANGE    10
        Continue For Loop If    ${i} == 1
        Exit For Loop If    ${i} > 3
        Log    ${i}
        Run Keyword If    ${i} == 2    Exit For Loop
    END
""")

case("d05_with_name", "deprecated", "WITH NAME alias", """*** Settings ***
Library    Collections    WITH NAME    Coll

""" + T + """Alias
    ${l}=    Create List    a    b
    Coll.List Should Contain Value    ${l}    a
""")

case("d06_force_default_tags", "deprecated", "Force Tags / Default Tags", """*** Settings ***
Force Tags      smoke
Default Tags    regression

""" + T + """Tagged
    Log    x
""")

case("d07_single_space_args", "error", "single space between keyword and args", T + """Compare
    ${a}=    Set Variable    1
    Should Be Equal ${a}    1
""")

case("d08_bad_continuation", "error", "continuation marker without separator", T + """Long Call
    Log Many    first
    ...second    third
""")

case("d09_misaligned_continuation", "style", "misaligned ... continuation (valid)", T + """Long Call
    Log Many    first
  ...    second
        ...    third
""")

case("d10_set_variable_vs_var", "deprecated", "Set Variable/Create List instead of VAR", T + """Vars
    ${name}=    Set Variable    Bob
    ${items}=    Create List    a    b
    Set Test Variable    ${GREETING}    hi
    Log Many    ${name}    @{items}    ${GREETING}
""")

case("d11_assign_without_equals", "style", "${var} assignment without = (valid)", T + """Assign
    ${a}    Set Variable    1
    ${b}=    Set Variable    2
    ${c} =    Set Variable    3
    Log Many    ${a}    ${b}    ${c}
""")

case("d12_tabs", "style", "tab separators (valid)", T + "Tabs\n\tLog\thello\n    Log    world\n")

case("d13_if_missing_end", "error", "IF without END", T + """Branch
    ${x}=    Set Variable    1
    IF    ${x} == 1
        Log    one
    Log    after
""")

case("d14_singular_headers", "deprecated", "singular section headers", """*** Setting ***
Documentation    Old headers.

*** Test Case ***
Old Header
    Say Hi

*** Keyword ***
Say Hi
    Log    hi
""")

case("d15_invalid_header", "error", "invalid section header", """*** Steps ***
Step One
    Log    x
""")

case("d16_selenium_kw_browser_suite", "error", "Selenium keyword in Browser suite", """*** Settings ***
Library    Browser

""" + T + """Login
    New Page    https://example.org
    Input Text    id=user    bob
    Click Element    id=login
    Wait Until Page Contains    Welcome
""", runnable=False)

case("d17_return_from_keyword", "deprecated", "Return From Keyword", T + """Use Kw
    ${v}=    Pick    2
    Should Be Equal    ${v}    two

*** Keywords ***
Pick
    [Arguments]    ${n}
    Return From Keyword If    ${n} == 1    one
    Return From Keyword    two
""")

case("d18_lowercase_else", "error", "lowercase else / else if", T + """Branch
    ${x}=    Set Variable    1
    IF    ${x} == 2
        Log    two
    else
        Log    other
    END
""")

case("d19_unindented_for_body", "error", "FOR body not indented", T + """Loop
    FOR    ${i}    IN RANGE    2
    Log    ${i}
    END
""")

case("d20_tags_in_settings", "error", "test-level setting in Settings section", """*** Settings ***
Tags    smoke
Setup    Log    hi

""" + T + """T
    Log    x
""")

case("d21_return_setting_in_test", "error", "[Return] in test case", T + """T
    Log    x
    [Return]    1
""")

case("d22_unquoted_if_string", "runtime", "IF compares unquoted string", T + """Cond
    ${status}=    Set Variable    PASS
    IF    ${status} == PASS
        Log    ok
    END
""")

case("d23_setting_no_separator", "error", "[Documentation] glued to value", T + """T
    [Documentation]Checks things
    Log    x
""")

case("d24_old_set_variable_if", "deprecated", "Set Variable If", T + """T
    ${x}=    Set Variable    3
    ${size}=    Set Variable If    ${x} > 2    big    small
    Log    ${size}
""")

case("d25_browser_kw_args_wrong", "error", "Browser Click with Selenium-style args", """*** Settings ***
Library    Browser

""" + T + """T
    New Page    https://example.org
    Click    id=login    left    2    0.1    extra    more    args    too    many    xx
    Get Text    h1    should be    Welcome
""", runnable=False)

case("d26_try_without_except", "error", "TRY without EXCEPT/FINALLY", T + """T
    TRY
        Log    x
    END
""")

case("d27_var_glued_value", "error", "VAR with value glued to name", T + """T
    VAR    ${x}    1
    VAR    ${y}=2
    Log    ${x}
""")

case("d28_sleep", "style", "Sleep instead of wait (valid)", T + """T
    Sleep    2s
    Log    done
""")


def main() -> None:
    CASES.mkdir(parents=True, exist_ok=True)
    manifest = []
    for cid, (kind, cls, runnable, text) in C.items():
        path = CASES / f"{cid}.robot"
        path.write_text(text)
        manifest.append({"id": cid, "kind": kind, "cls": cls, "runnable": runnable,
                         "file": f"cases/{cid}.robot"})
    (ROOT / "manifest.json").write_text(json.dumps(manifest, indent=1))
    (ROOT / "robot.toml").write_text('paths = ["cases"]\noutput-dir = "../out/run2"\nconsole-colors = "off"\n')
    print(len(manifest), "cases")


if __name__ == "__main__":
    main()
