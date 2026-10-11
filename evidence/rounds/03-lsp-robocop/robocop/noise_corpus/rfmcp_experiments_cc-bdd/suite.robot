*** Settings ***
Documentation    BDD-style specification of the lab greeting flow.
Library          Browser
Test Tags        bdd    web    lab    greeting
Suite Teardown    Close Browser

*** Test Cases ***
Greeting Flow
    [Documentation]    A user opens the lab page, greets as Robot, and sees the greeting.
    [Tags]    bdd    web    lab    greeting
    Given the lab page is open
    When I greet as Robot
    Then I see the greeting

*** Keywords ***
the lab page is open
    [Documentation]    Open the lab page in a headless Chromium browser.
    New Browser    chromium    headless=True    args=["--no-sandbox","--disable-dev-shm-usage","--disable-gpu"]
    New Page       file:///app/lab/index.html

I greet as Robot
    [Documentation]    Enter the name and click the greet button.
    Fill Text    id=name    Robot
    Click        id=greet

I see the greeting
    [Documentation]    The page should display the greeting "Hello, Robot!".
    ${greeting}=    Get Text    id=result
    Should Be Equal    ${greeting}    Hello, Robot!