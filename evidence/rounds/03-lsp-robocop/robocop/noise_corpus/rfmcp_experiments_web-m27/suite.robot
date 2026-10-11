*** Settings ***
Documentation    Test suite generated from session lab_session containing 1 test case for automation.
Library         Browser
Test Tags       automated    generated

*** Test Cases ***
Robot Greeting Test
    [Documentation]    Test case that performs click action.
    New Page    file:///app/lab/index.html
    Fill Text    id=name    Robot
    Click    id=greet    # Click on id=greet
    Get Text    id=result
    [Teardown]    Close Browser    
