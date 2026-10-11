"""Corpus of realistic agent mistakes for the robotcode-output hint experiment.

Each entry is run in its own ``robotcode repl --plain`` session:
``preamble`` + ``steps`` (the LAST step is the mistake under test).

``agent_call`` is what the same agent would have sent to native rf-mcp's
``execute_step`` (keyword + raw argument list). ``libraries`` is the rf-mcp
session search order for that scenario (fed to HintContext.session_search_order).
"""

SEP = "    "


def L(*cells):
    return SEP.join(cells)


BROWSER_IMPORT = L("Import Library", "Browser", "timeout=5s")
SAUCE = [
    BROWSER_IMPORT,
    L("New Browser", "chromium", "headless=True"),
    L("New Page", "https://www.saucedemo.com"),
]
SAUCE_LOGGED = SAUCE + [
    L("Fill Text", '[data-test="username"]', "standard_user"),
    L("Fill Text", '[data-test="password"]', "secret_sauce"),
    L("Click", '[data-test="login-button"]'),
]
DEMOSHOP = [
    L("Import Library", "Browser", "timeout=15s"),
    L("New Browser", "chromium", "headless=True"),
    L("New Page", "https://demoshop.makrocode.de/?space=rfmcp-hints"),
    L("Set Browser Timeout", "5s"),
]
SHOP_LIB = str(__import__("pathlib").Path(__file__).resolve().parent / "libs" / "ShopHelpers.py")
BOOKER = [
    L("Import Library", "RequestsLibrary"),
    L("Import Library", "Collections"),
    L("Create Session", "rb", "https://restful-booker.herokuapp.com"),
]
BOOKER_AUTH = BOOKER + [
    L("&{creds}=", "Create Dictionary", "username=admin", "password=password123"),
    L("${resp}=", "POST On Session", "rb", "/auth", "json=${creds}"),
]
BUILTIN = [L("Import Library", "Collections")]

BROWSER_LIBS = ["Browser", "BuiltIn", "Collections", "String"]
REQ_LIBS = ["RequestsLibrary", "BuiltIn", "Collections", "String"]
BI_LIBS = ["BuiltIn", "Collections", "String"]


def M(id, title, category, preamble, steps, keyword, arguments, libraries, note=""):
    return {
        "id": id,
        "title": title,
        "category": category,
        "preamble": list(preamble),
        "steps": list(steps),
        "agent_call": {"keyword": keyword, "arguments": list(arguments)},
        "libraries": list(libraries),
        "note": note,
    }


CORPUS = [
    # ---------------- Browser / saucedemo ----------------
    M("M01", "Selector matches nothing (timeout)", "locator",
      SAUCE, [L("Click", '[data-test="login-btn"]')],
      "Click", ['[data-test="login-btn"]'], BROWSER_LIBS),
    M("M02", "Strict-mode violation (6 matches)", "locator",
      SAUCE_LOGGED, [L("Click", "button.btn_inventory")],
      "Click", ["button.btn_inventory"], BROWSER_LIBS),
    M("M03", "Click intercepted by modal overlay (demoshop login modal open)", "actionability",
      DEMOSHOP, [L("Click", '[data-test="login-button"]'), L("Sleep", "1s"),
                 L("Click", '[data-test="search-submit"]')],
      "Click", ['[data-test="search-submit"]'], BROWSER_LIBS),
    M("M04", "Element not visible / outside viewport (menu closed)", "actionability",
      SAUCE_LOGGED, [L("Click", "id=logout_sidebar_link")],
      "Click", ["id=logout_sidebar_link"], BROWSER_LIBS),
    M("M05", "Selenium-style id: locator in Browser", "locator",
      SAUCE, [L("Fill Text", "id:user-name", "standard_user")],
      "Fill Text", ["id:user-name", "standard_user"], BROWSER_LIBS),
    M("M06", "Selenium-style link= locator in Browser", "locator",
      SAUCE_LOGGED, [L("Click", "link=Sauce Labs Backpack")],
      "Click", ["link=Sauce Labs Backpack"], BROWSER_LIBS),
    M("M07", "Role-prefix misuse button=Login", "locator",
      SAUCE, [L("Click", "button=Login")],
      "Click", ["button=Login"], BROWSER_LIBS),
    M("M08", "Evaluate JavaScript with JS body as only arg", "keyword-shape",
      SAUCE, [L("Evaluate JavaScript", "() => { return document.title }")],
      "Evaluate JavaScript", ["() => { return document.title }"], BROWSER_LIBS),
    M("M09", "Keyword name typo (Clik)", "keyword-name",
      SAUCE, [L("Clik", '[data-test="login-button"]')],
      "Clik", ['[data-test="login-button"]'], BROWSER_LIBS),
    M("M10", "Wrong number of args (Fill Text w/o text)", "arguments",
      SAUCE, [L("Fill Text", '[data-test="username"]')],
      "Fill Text", ['[data-test="username"]'], BROWSER_LIBS),
    M("M11", "Non-existent named arg force=True on Click", "arguments",
      SAUCE, [L("Click", '[data-test="login-button"]', "force=True")],
      "Click", ['[data-test="login-button"]', "force=True"], BROWSER_LIBS),
    M("M12", "Non-existent named arg timeout= on Get Title", "arguments",
      SAUCE, [L("Get Title", "timeout=5s")],
      "Get Title", ["timeout=5s"], BROWSER_LIBS),
    M("M13", "Interacting before New Page (no page open)", "state",
      [BROWSER_IMPORT], [L("Click", '[data-test="login-button"]')],
      "Click", ['[data-test="login-button"]'], BROWSER_LIBS),
    M("M14", "Navigation timeout too short", "timeout",
      SAUCE, [L("Go To", "https://demoshop.makrocode.de/", "timeout=1ms")],
      "Go To", ["https://demoshop.makrocode.de/", "timeout=1ms"], BROWSER_LIBS),
    M("M15", "Browser assertion mismatch (Get Text ==)", "assertion",
      SAUCE_LOGGED, [L("Get Text", '[data-test="title"]', "==", "Product")],
      "Get Text", ['[data-test="title"]', "==", "Product"], BROWSER_LIBS),
    M("M16", "SeleniumLibrary keyword in Browser session (Input Text)", "keyword-name",
      SAUCE, [L("Input Text", "id=user-name", "standard_user")],
      "Input Text", ["id=user-name", "standard_user"], BROWSER_LIBS),
    M("M17", "Invalid XPath (unclosed bracket)", "locator",
      SAUCE, [L("Click", "xpath=//input[@id='user-name'")],
      "Click", ["xpath=//input[@id='user-name'"], BROWSER_LIBS),
    M("M18", "Keyword ambiguity (Browser + Screenshot: Take Screenshot)", "keyword-name",
      SAUCE, [L("Import Library", "Screenshot"), L("Take Screenshot")],
      "Take Screenshot", [], BROWSER_LIBS + ["Screenshot"]),
    M("M18b", "Keyword ambiguity (Browser + project library: Take Screenshot)", "keyword-name",
      SAUCE, [L("Import Library", SHOP_LIB), L("Take Screenshot")],
      "Take Screenshot", [], BROWSER_LIBS + ["ShopHelpers"]),
    M("M19", "Timeout on a wait keyword (element never appears)", "timeout",
      SAUCE, [L("Wait For Elements State", '[data-test="shopping-cart-badge"]', "visible", "timeout=500ms")],
      "Wait For Elements State", ['[data-test="shopping-cart-badge"]', "visible", "timeout=500ms"], BROWSER_LIBS),
    # ---------------- Browser / demoshop ----------------
    M("M20", "Strict-mode violation on demoshop add-to-cart", "locator",
      DEMOSHOP, [L("Click", '[data-test="add-to-cart-btn"]')],
      "Click", ['[data-test="add-to-cart-btn"]'], BROWSER_LIBS),
    M("M21", "Fill hidden field (login modal not opened)", "actionability",
      DEMOSHOP, [L("Fill Text", "id=auth-email", "jamie@flowlinesupply.com")],
      "Fill Text", ["id=auth-email", "jamie@flowlinesupply.com"], BROWSER_LIBS),
    M("M22", "Selenium css: prefix on demoshop", "locator",
      DEMOSHOP, [L("Click", 'css:[data-test="search-submit"]')],
      "Click", ['css:[data-test="search-submit"]'], BROWSER_LIBS),
    # ---------------- library / import ----------------
    M("M23", "Missing library import (New Page without Browser)", "import",
      BUILTIN, [L("New Page", "https://www.saucedemo.com")],
      "New Page", ["https://www.saucedemo.com"], BI_LIBS),
    M("M24", "Library not installed (SeleniumLibrary)", "import",
      BUILTIN, [L("Import Library", "SeleniumLibrary")],
      "Import Library", ["SeleniumLibrary"], BI_LIBS),
    # ---------------- RequestsLibrary / restful-booker ----------------
    M("M25", "Wrong expected_status (ping returns 201)", "api",
      BOOKER, [L("GET On Session", "rb", "/ping", "expected_status=200")],
      "GET On Session", ["rb", "/ping", "expected_status=200"], REQ_LIBS),
    M("M26", "404 without expected_status", "api",
      BOOKER, [L("GET On Session", "rb", "/booking/99999999")],
      "GET On Session", ["rb", "/booking/99999999"], REQ_LIBS),
    M("M27", "URL passed as session alias", "api",
      BOOKER, [L("GET On Session", "https://restful-booker.herokuapp.com", "/booking")],
      "GET On Session", ["https://restful-booker.herokuapp.com", "/booking"], REQ_LIBS),
    M("M28", "Relative path on sessionless GET", "api",
      BOOKER, [L("GET", "/booking")],
      "GET", ["/booking"], REQ_LIBS),
    M("M29", "Headers passed as string", "api",
      BOOKER + [L("&{creds}=", "Create Dictionary", "username=admin", "password=password123")],
      [L("POST On Session", "rb", "/auth", "json=${creds}", "headers=Content-Type: application/json")],
      "POST On Session", ["rb", "/auth", "json=${creds}", "headers=Content-Type: application/json"], REQ_LIBS),
    M("M30", "JSON body passed as quoted string", "api",
      BOOKER, [L("POST On Session", "rb", "/booking", 'json={"firstname": "Jim"}')],
      "POST On Session", ["rb", "/booking", 'json={"firstname": "Jim"}'], REQ_LIBS),
    M("M31", "Dict dot-access on response JSON", "variables",
      BOOKER_AUTH, [L("Log", "${resp.json().token}")],
      "Log", ["${resp.json().token}"], REQ_LIBS),
    M("M32", "Method not called: ${resp.json['token']}", "variables",
      BOOKER_AUTH, [L("Log", "${resp.json['token']}")],
      "Log", ["${resp.json['token']}"], REQ_LIBS),
    M("M33", "Query params passed as bare named arg", "api",
      BOOKER, [L("GET On Session", "rb", "/booking", "firstname=Sally")],
      "GET On Session", ["rb", "/booking", "firstname=Sally"], REQ_LIBS),
    M("M34", "Bad JSON path (missing key)", "api",
      BOOKER_AUTH, [L("Get From Dictionary", "${resp.json()}", "access_token")],
      "Get From Dictionary", ["${resp.json()}", "access_token"], REQ_LIBS),
    M("M35", "Status code int vs string in Should Be Equal", "assertion",
      BOOKER_AUTH, [L("Should Be Equal", "${resp.status_code}", "200")],
      "Should Be Equal", ["${resp.status_code}", "200"], REQ_LIBS),
    # ---------------- BuiltIn / Collections ----------------
    M("M36", "Variable not found (typo)", "variables",
      BUILTIN + [L("${username}=", "Set Variable", "jim")], [L("Log", "${usernme}")],
      "Log", ["${usernme}"], BI_LIBS),
    M("M37", "Evaluate with JSON true", "evaluate",
      BUILTIN, [L("Evaluate", '{"depositpaid": true}')],
      "Evaluate", ['{"depositpaid": true}'], BI_LIBS),
    M("M38", "Evaluate with ${var} substitution of a string", "evaluate",
      BUILTIN + [L("${name}=", "Set Variable", "Jim")], [L("Evaluate", "${name} == 'Jim'")],
      "Evaluate", ["${name} == 'Jim'"], BI_LIBS),
    M("M39", "Collections.Create List (wrong library)", "keyword-name",
      BUILTIN, [L("Collections.Create List", "a", "b")],
      "Collections.Create List", ["a", "b"], BI_LIBS),
    M("M40", "Dictionary keyword on a list", "arguments",
      BUILTIN + [L("${l}=", "Create List", "a", "b")], [L("Dictionary Should Contain Key", "${l}", "a")],
      "Dictionary Should Contain Key", ["${l}", "a"], BI_LIBS),
    M("M41", "Process-style dash arg with '=' (silently swallowed)", "process",
      BUILTIN + [L("Import Library", "Process")],
      [L("${r}=", "Run Process", "echo", "-env:UserInstallation=file:///tmp/lo"),
       L("Log To Console", "STDOUT=[${r.stdout}]")],
      "Run Process", ["echo", "-env:UserInstallation=file:///tmp/lo"], BI_LIBS + ["Process"],
      note="agent_call is the Run Process step (second-to-last); the mistake is silent"),
    M("M42", "Old-style :FOR loop", "syntax",
      BUILTIN, [L(":FOR", "${i}", "IN", "a", "b")],
      ":FOR", ["${i}", "IN", "a", "b"], BI_LIBS),
    M("M43", "Wrong args to Should Be Equal (1 arg)", "arguments",
      BUILTIN, [L("Should Be Equal", "a")],
      "Should Be Equal", ["a"], BI_LIBS),
]


if __name__ == "__main__":
    import json
    print(json.dumps({"count": len(CORPUS)}, indent=2))
