*** Settings ***
Documentation    Test suite generated from session fileproc containing 1 test case for automation.
Library         OperatingSystem
Test Tags       automated    generated

*** Test Cases ***
File Processing Test
    [Documentation]    Tests OperatingSystem library file operations: creating directory, file with three lines, appending a fourth line, verifying content via Should Contain, and confirming file exists.
    Create Directory    /artifacts/fileproc
    Create File    /artifacts/fileproc/report.txt    line1
line2
line3

    Append To File    /artifacts/fileproc/report.txt    line4
    line1
line2
line3
line4 =    Get File    /artifacts/fileproc/report.txt
    Should Contain    line1
line2
line3
line4    line1    # Verify page contains 'line1
line2
line3
line4'
    Should Contain    line1
line2
line3
line4    line2    # Verify page contains 'line1
line2
line3
line4'
    Should Contain    line1
line2
line3
line4    line3    # Verify page contains 'line1
line2
line3
line4'
    Should Contain    line1
line2
line3
line4    line4    # Verify page contains 'line1
line2
line3
line4'
    File Should Exist    /artifacts/fileproc/report.txt
