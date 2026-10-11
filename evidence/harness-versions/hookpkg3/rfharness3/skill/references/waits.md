# Waits and timeouts

WAITS AND TIMEOUTS   (verified on Browser 19.12 and 20.5)

Browser library:
- Element keywords (Click, Fill Text, Get Text ...) auto-wait for the ELEMENT (attached, visible, enabled) up to
  the browser timeout (default 10 s; Set Browser Timeout    20s).
- VALUES do not wait: a getter WITHOUT an assertion operator returns the current value at once
      ${t}=    Get Text    id=status          -> "Loading..."      ${n}=    Get Element Count    css=.row    -> 0
- A getter WITH an assertion operator retries only `retry_assertions_for` = 1 s by default (not 10 s!):
      Get Text    id=status    ==    Done          Get Element Count    css=.row    >=    3
- Slower async UI (spinner, search results, toast) -> wait with the full timeout:
      Wait For Condition    Text    id=status    contains    Done    timeout=15s
      Wait For Condition    Element Count    css=.row    ==    3
      Wait For Elements State    id=spinner    hidden    timeout=15s
      Wait For Elements State    css=.row >> nth=2    visible    timeout=15s
  or raise the retry for the suite/test: Set Retry Assertions For    10s   (Library    Browser    retry_assertions_for=10s)
- After navigation: Get Url    contains    /home   or   Wait For Load State    networkidle
- Do NOT add Sleep; use a condition/state wait instead.
SeleniumLibrary: Wait Until Element Is Visible    id:x    10s ; Wait Until Page Contains    text ;
                 Set Selenium Timeout    10s ; Set Selenium Implicit Wait (avoid mixing with explicit waits).
BuiltIn: Wait Until Keyword Succeeds    10s    1s    <keyword>    <args>
Hook runs (live session only -- never in your files or the plain robot run): element actions/getters use a SHORT
timeout (2.5 s; navigation and Wait* keywords keep the normal one). A not-found / not-visible / timeout failure is
re-checked ONCE with the normal timeout: "recheck: SLOW -- appeared after N s" -> the element is just slow: add
`Wait For Elements State    <sel>    visible    timeout=10s` before the line (the hook already re-ran it);
"recheck: MISSING" -> wrong selector / iframe / hidden element (.rf/state/latest/controls.txt).
A line that runs longer than the hook budget is reported as "still running"; its result comes with your next edit.
