*** Settings ***
Documentation     Reference solution (hidden from agents): configure + order a Luxury X5 SUV on the live car configurator.
Library           Browser
Suite Setup       New Browser    chromium    headless=True
Suite Teardown    Close Browser    ALL

*** Test Cases ***
Configured Luxury X5 SUV Can Be Ordered
    New Page    https://carconfig.makrocode.de/
    Click    xpath=//h4[normalize-space()='Luxury X5 SUV']/ancestor::div[.//a][1]//a
    Wait For Elements State    css=[data-testid=car-base-price]    visible
    # defaults (Hybrid, Metallic, 19") are applied asynchronously after load
    Get Text    css=[data-testid=total-price]    contains    67.600,00
    # option "radios"/"checkboxes" are styled divs identified by their title
    Click    css=[title^="Radio: Sportmotor 3.0L V6"]
    Click    css=[title^="Radio: Perleffekt-Lackierung"]
    Click    css=[title^='Radio: 20" Premium Felgen']
    Click    css=[title^="Checkbox: Leder-Ausstattung"]
    Click    css=[title^="Checkbox: Fahrassistenz-Paket Plus"]
    Click    css=[title^="Checkbox: Adaptive LED-Scheinwerfer"]
    # prices are rendered with a no-break space before the euro sign -> use contains
    Get Text    css=[data-testid=total-price]    contains    82.400,00
    Click    css=button:has-text("Jetzt kaufen")
    Wait For Elements State    text=Bestellung abschließen    visible
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
