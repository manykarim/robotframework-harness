*** Settings ***
Resource    common.resource

*** Test Cases ***
Step
    Given The User Is Logged In
    When The User Adds 3 Items To The Cart
    Then The Cart Should Contain "Backpack"
    And Login As    bob
