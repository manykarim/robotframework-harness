*** Settings ***
Documentation     Every Browser-library claim made in `rfmcp guide explore` / `rfmcp guide debug`, checked against
...               verify/site/widgets.html. Run with plain robot (Browser 19.12 and 20.5 must both pass):
...               robot -d "$(mktemp -d)" verify/widgets_claims.robot    (Browser writes playwright-log.txt + browser/ into -d)
Library           Browser
Library           DateTime
Suite Setup       New Browser    chromium    headless=True
Test Setup        Open Form

*** Variables ***
${URL}            file://${CURDIR}/site/widgets.html

*** Test Cases ***
Overlay Blocks Clicks Until Dismissed
    Set Browser Timeout    2s    scope=Test
    ${err}=    Run Keyword And Expect Error    *intercepts pointer events*    Click    id=traveller
    Click    text=Accept all
    Wait For Elements State    id=consent    detached
    Click    id=traveller

Label Role Placeholder And Test Id Selectors
    Click    text=Accept all
    Fill Text    role=textbox[name="Traveller name"]    Ann
    Get Property    id=traveller    value    ==    Ann
    ${e}=    Get Element By    Label    Traveller name
    Fill Text    ${e}    Bea
    Get Text    id=traveller    ==    Bea
    Fill Text    data-test=traveller    Cy
    Get Text    data-test=traveller    ==    Cy
    ${p}=    Get Element By    Placeholder    name@example.com
    Fill Text    ${p}    a@b.c
    Get Property    css=input[placeholder="name@example.com"]    value    ==    a@b.c
    Get Text    role=button[name="Send request"]    ==    Send request
    Get Element Count    role=button[name="send request"]    ==    0    # role name: exact, case-sensitive
    Fill Text    role=textbox[name="E-mail"]    x@y.z    # aria-label is the accessible name too
    ${m}=    Get Element By    Label    E-mail
    Get Property    ${m}    value    ==    x@y.z
    Get Property    data-testid=email    value    ==    x@y.z

Styled Radio With Hidden Input Needs Its Label
    Click    text=Accept all
    Set Browser Timeout    2s    scope=Test
    Run Keyword And Expect Error    *    Check Checkbox    id=trip-round
    Run Keyword And Expect Error    *    Click    role=radio[name="Round trip"]
    Click    label[for="trip-round"]
    Get Checkbox State    id=trip-round    ==    checked
    Get Element States    id=trip-round    contains    checked
    Click    text=One way
    Get Checkbox State    id=trip-one    ==    checked
    Get Checkbox State    id=trip-round    ==    unchecked

Hidden Checkbox Inside Label
    Click    text=Accept all
    Set Browser Timeout    2s    scope=Test
    Run Keyword And Expect Error    *    Check Checkbox    id=insurance
    Click    label:has(#insurance)
    Get Checkbox State    id=insurance    ==    checked
    Click    text=Add travel insurance
    Get Checkbox State    id=insurance    ==    unchecked

Native Select
    Click    text=Accept all
    Select Options By    id=dest    label    Oslo
    Get Selected Options    id=dest    label    ==    Oslo
    Select Options By    id=dest    value    rom
    Get Selected Options    id=dest    value    ==    rom
    Get Selected Options    id=dest    label    ==    Rome
    Select Options By    id=dest    index    1
    Get Selected Options    id=dest    label    ==    Berlin

Custom Dropdown Is Clicked Not Selected
    Click    text=Accept all
    Set Browser Timeout    2s    scope=Test
    ${err}=    Run Keyword And Expect Error    *    Select Options By    id=travel-class    label    Business
    Log To Console    \nSelect Options By on a custom dropdown: ${err}
    Click    id=travel-class
    Click    role=option[name="Business"]
    Get Text    id=travel-class    ==    Business
    Get Element States    id=travel-class-list    contains    hidden

Date Fields Relative To Today
    Click    text=Accept all
    ${dep}=    Get Current Date    increment=7 days    result_format=%Y-%m-%d
    Fill Text    id=depart    ${dep}
    Get Property    id=depart    value    ==    ${dep}
    ${now}=    Get Current Date
    ${back}=    Add Time To Date    ${now}    14 days    result_format=%m/%d/%Y
    Fill Text    id=ret    ${back}
    Get Text    id=ret    ==    ${back}
    ${from_dep}=    Add Time To Date    ${dep}    7 days    result_format=%m/%d/%Y
    Should Be Equal    ${from_dep}    ${back}

Full Request With Async Result
    Fill Valid Request
    Click    id=send-request
    ${now_text}=    Get Text    id=status
    Should Be Equal    ${now_text}    Processing...    # a getter WITHOUT an operator does not wait
    ${n}=    Get Element Count    css=#results li
    Should Be Equal As Integers    ${n}    0
    # an assertion operator retries only `retry_assertions_for` (default 1 s) -- the result needs 2 s:
    Run Keyword And Expect Error    *should contain*    Get Text    id=status    contains    Request confirmed
    Wait For Condition    Text    id=status    contains    Request confirmed    timeout=10s
    Get Text    id=status    contains    insurance yes
    Wait For Elements State    id=spinner    hidden    timeout=10s
    Get Element Count    css=#results li    ==    3
    Wait For Condition    Element Count    css=#results li    ==    3
    Wait For Condition    Text    id=status    contains    round
    Get Text    id=status    contains    round

Validation Message Is Read From The Page
    Click    text=Accept all
    Click    id=send-request
    Get Text    id=status    ==    Missing: name, trip type, destination, class, departure

JavaScript Dialogs
    Click    text=Accept all
    Click    id=reset-form
    Get Text    id=status    ==    Reset cancelled    # unhandled confirm() is dismissed
    Handle Future Dialogs    action=accept
    Click    id=reset-form
    Get Text    id=status    ==    Form reset
    Click    id=reset-form    # the handler stays active for later dialogs on this page
    Get Text    id=status    ==    Form reset

JavaScript Prompt
    # one Handle Future Dialogs per page (Browser 19.x adds a 2nd handler instead of replacing it -> crash)
    Click    text=Accept all
    Handle Future Dialogs    action=accept    prompt_input=Weekly
    Click    id=save-tpl
    Get Text    id=status    ==    Template saved: Weekly

JavaScript Dialog Via Promise
    # NOT on a page that already has Handle Future Dialogs: both handle the dialog -> Playwright process crash
    Click    text=Accept all
    ${promise}=    Promise To    Wait For Alert    action=accept    text=Reset the form?
    Click    id=reset-form
    Wait For    ${promise}
    Get Text    id=status    ==    Form reset

Different Answers Via One Promise Per Dialog
    Click    text=Accept all
    ${p}=    Promise To    Wait For Alert    action=dismiss
    Click    id=reset-form
    Wait For    ${p}
    Get Text    id=status    ==    Reset cancelled
    ${p}=    Promise To    Wait For Alert    action=accept    prompt_input=Daily
    Click    id=save-tpl
    Wait For    ${p}
    Get Text    id=status    ==    Template saved: Daily

New Tab From Link
    Click    text=Accept all
    Click    id=help-link
    ${previous}=    Switch Page    NEW
    Get Title    ==    Help
    Get Text    id=help-text    contains    Fill in all fields
    Switch Page    ${previous}
    Get Title    ==    Travel request

Change Event After Fill
    Click    text=Accept all
    Evaluate JavaScript    id=traveller    (el) => el.addEventListener("change", () => el.dataset.changed = "yes")
    Fill Text    id=traveller    Ann
    ${changed}=    Evaluate JavaScript    id=traveller    (el) => el.dataset.changed || "no"
    Should Be Equal    ${changed}    no    # Fill Text fires `input`, not `change`
    Press Keys    id=traveller    Tab
    Get Attribute    id=traveller    data-changed    ==    yes

Slow Async Result With Longer Assertion Retry
    Fill Valid Request
    Set Retry Assertions For    10s    scope=Test
    Click    id=send-request
    Get Text    id=status    contains    Request confirmed
    Get Element Count    css=#results li    ==    3

Spinner Wait Then Plain Getter
    Fill Valid Request
    Click    id=send-request
    Wait For Elements State    id=spinner    hidden    timeout=10s
    ${status}=    Get Text    id=status
    Should Start With    ${status}    Request confirmed
    Wait For Elements State    css=#results li >> nth=2    visible    timeout=10s

*** Keywords ***
Open Form
    New Page    ${URL}

Fill Valid Request
    Click    text=Accept all
    Fill Text    id=traveller    Ann
    Click    text=Round trip
    Click    text=Add travel insurance
    Select Options By    id=dest    label    Oslo
    Click    id=travel-class
    Click    role=option[name="First"]
    ${dep}=    Get Current Date    increment=3 days    result_format=%Y-%m-%d
    Fill Text    id=depart    ${dep}
    ${back}=    Get Current Date    increment=10 days    result_format=%m/%d/%Y
    Fill Text    id=ret    ${back}
