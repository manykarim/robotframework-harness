*** Settings ***
Library    Process

*** Test Cases ***
Step
    Start Process    echo    hi    shell=True    alias=p
