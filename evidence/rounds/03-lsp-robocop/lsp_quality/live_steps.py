"""Growing live-file scenario: header + steps appended one Edit at a time.

Each step: (id, probe, lines-to-append-to-the-test-body, expect_static) where expect_static is
'clean' (valid RF; any static error is a FALSE POSITIVE) or a diagnostic code (planted error).
"""

HEADER = """*** Settings ***
Library    Browser
Library    RequestsLibrary
Resource    shop.resource

*** Test Cases ***
Live
"""

STEPS = [
    ("s01", "robot.toml [variables] + Browser start",
     ["    New Browser    chromium    headless=True", "    New Page    ${BASE_URL}"], "clean"),
    ("s02", "variable assigned in an earlier line (${x}=)",
     ["    ${title}=    Get Title", "    Should Be Equal    ${title}    Swag Labs"], "clean"),
    ("s03", "Set Test Variable, unescaped name",
     ["    Set Test Variable    ${user}    standard_user", "    Log    ${user}"], "clean"),
    ("s04", "Set Test Variable, escaped name \\${pw}",
     ["    Set Test Variable    \\${pw}    secret_sauce", "    Log    ${pw}"], "clean"),
    ("s05", "Set Suite Variable in body",
     ["    Set Suite Variable    ${SUITE_TOKEN}    abc", "    Log    ${SUITE_TOKEN}"], "clean"),
    ("s06", "VAR scope=SUITE (RF7)",
     ["    VAR    ${v}    1    scope=SUITE", "    Log    ${v}"], "clean"),
    ("s07", "variable only given as -v at helper start",
     ["    Log    ${CLI_VAR}"], "clean"),
    ("s08", "Set Suite Variable inside a resource keyword, used in test",
     ["    Create Booking Token", "    Log    ${TOKEN}"], "clean"),
    ("s09", "BDD prefixes + embedded-arg resource keywords",
     ["    Given The User Opens The Shop", "    When The User Logs In As \"standard_user\"",
      "    And The User Adds 2 Items To The Cart", "    Then The Cart Badge Should Show 2"], "clean"),
    ("s10", "extended variable syntax on Requests response",
     ["    ${resp}=    GET    ${API_URL}/booking    expected_status=200",
      "    ${id}=    Set Variable    ${resp.json()}[0][bookingid]",
      "    Create Session    booker    ${API_URL}",
      "    ${r}=    GET On Session    booker    /booking/${id}",
      "    Should Be Equal As Integers    ${r.status_code}    200"], "clean"),
    ("s11", "FOR block appended in two edits (part 1: header only)",
     ["    FOR    ${i}    IN RANGE    2"], "ModelError"),
    ("s12", "FOR block part 2 (body + END)",
     ["        Log    loop ${i}", "    END"], "clean"),
    ("s13", "planted: keyword typo", ["    Clik    id=login-button"], "KeywordNotFound"),
    ("s14", "planted: undefined variable", ["    Log    ${usrname}"], "VariableNotFound"),
    ("s15", "planted: missing argument", ["    Fill Text    id=user-name"], "DataError"),
]

# keywords section appended at the END of the file (exp: user keywords defined in the live file)
KEYWORDS_SECTION = """
*** Keywords ***
Live Helper
    [Arguments]    ${x}
    Log    live helper got ${x}
    RETURN    ${x}-done
"""
CALL_LIVE_HELPER = ["    ${h}=    Live Helper    42", "    Should Be Equal    ${h}    42-done"]

# Browser + SeleniumLibrary ambiguity (wt env only)
SELENIUM_HEADER = """*** Settings ***
Library    Browser
Library    SeleniumLibrary

*** Test Cases ***
Live
"""
SELENIUM_STEPS = [
    ("x01", "ambiguous Get Text (Browser+Selenium)", ["    Get Text    id=foo"], "MultipleKeywords"),
    ("x02", "Set Library Search Order Browser then Get Text",
     ["    Set Library Search Order    Browser", "    Get Text    id=foo"], "clean"),
    ("x03", "qualified Browser.Get Text", ["    Browser.Get Text    id=foo"], "clean"),
]
