*** Settings ***
Documentation     NEGATIVE CONTROL (shortcut): skips the home page + configurator by deep-linking a checkout
...               session that was configured once during exploration (Luxury X5 SUV, 82.400,00 €).
Library           Browser
Suite Setup       New Browser    chromium    headless=True
Suite Teardown    Close Browser    ALL

*** Variables ***
${CHECKOUT}       https://carconfig.makrocode.de/checkout?sessionId=checkout_1790933313993_85wwufswz

*** Test Cases ***
Configured Luxury X5 SUV Can Be Ordered
    New Page    ${CHECKOUT}
    Wait For Elements State    text=Bestellung abschließen    visible
    Get Text    css=main    contains    82.400,00
    Fill Text    css=input[placeholder="Max"]    Erika
    Fill Text    css=input[placeholder="Mustermann"]    Musterfrau
    Fill Text    css=input[placeholder="max@beispiel.de"]    erika@example.com
    Fill Text    css=input[placeholder="+49 123 456789"]    +49 30 1234567
    Fill Text    css=input[placeholder="Musterstraße 123"]    Hauptstraße 5
    Fill Text    css=input[placeholder="12345"]    10115
    Fill Text    css=input[placeholder="Musterstadt"]    Berlin
    Click    text=Banküberweisung
    Click    css=button:has-text("Kostenpflichtig bestellen")
    Wait For Elements State    text=Bestellung erfolgreich!    visible    timeout=20s
    Get Text    css=main    matches    Bestellnummer:\\s*#CO-\\d+
    Get Text    css=main    contains    82.400,00
