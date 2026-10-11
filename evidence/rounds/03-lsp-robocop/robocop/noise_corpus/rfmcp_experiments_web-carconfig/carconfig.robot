*** Settings ***
Documentation    Test suite generated from session f9f66b6b-078a-4f46-8ce3-01e58a02735b containing 1 test case for web automation.
Library         Browser
Library         Screenshot
Library         String
Test Tags       smoke    configuration    carconfig    automated    generated    web

*** Test Cases ***
Car Configurator E2E Test
    [Documentation]    Tests the car configurator at https://carconfig.makrocode.de/ by selecting engine, interior, and comfort options, then verifying the price summary updates correctly.
    [Tags]    carconfig    smoke    configuration
    ${browser_id} =    New Browser    headless=True    args=['--no-sandbox']
    New Context
    ${page_id} =    New Page
    Go To    https://carconfig.makrocode.de/
    Go To    https://carconfig.makrocode.de/configurator?carId=cmkykdtf600053epejeouv53s
    ${initial_total} =    Get Text    [data-testid="total-price"]
    Click    [data-testid="option-radio-cmkykdtgp000b3epe1y2j79mq"]    # Click on [data-testid="option-radio-cmkykdtgp000b3epe1y2j79mq"]
    Click    [data-testid="option-checkbox-cmkykdti6000m3epe46ato0d4"]    # Click on [data-testid="option-checkbox-cmkykdti6000m3epe46ato0d4"]
    Click    [data-testid="option-checkbox-cmkykdtiq000z3epeeqfcgkyg"]    # Click on [data-testid="option-checkbox-cmkykdtiq000z3epeeqfcgkyg"]
    ${updated_total} =    Get Text    [data-testid="total-price"]        \n
    ${updated_total_clean} =    Strip String    ${updated_total}
    ${updated_total_normalized} =    Replace String    ${updated_total}          
    Should Be Equal    ${updated_total_normalized}    61.000,00 €
    ${header_total} =    Get Text    [data-testid="header-total-price"]       
    ${summary_text} =    Get Text    h3:has-text("Preisberechnung") + div
    Should Contain    ${summary_text}    Sportmotor 3.0L V6    # Verify page contains '${summary_text}'
    Should Contain    ${summary_text}    Leder-Ausstattung    # Verify page contains '${summary_text}'
    Should Contain    ${summary_text}    Panorama-Schiebedach    # Verify page contains '${summary_text}'
    Take Screenshot    /artifacts/carconfig.png    fullPage=True
    [Teardown]    Close Browser    
