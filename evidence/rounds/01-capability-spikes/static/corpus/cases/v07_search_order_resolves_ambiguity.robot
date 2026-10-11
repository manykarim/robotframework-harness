*** Settings ***
Library    LibA
Library    LibB

*** Test Cases ***
Step
    Set Library Search Order    LibA
    Do Thing    x
