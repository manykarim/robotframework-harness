"""Regenerate rfmcp_skill/guides/*.txt from rf-mcp's OWN guidance code, so the skill arm gets the same
knowledge the MCP arm gets from get_locator_guidance(...) -- plus a short curated header per topic whose
statements were verified live (verify/verify_cli.py) and corrections where rf-mcp's text is wrong.

  .venv/bin/python tools/gen_guides.py
Sources:
  browser   robotmcp.utils.rf_native_type_converter.RobotFrameworkNativeConverter.get_browser_locator_guidance
            (+ its _analyze_browser_error sections) + server instructions "COMMON LOCATOR PATTERNS"
  selenium  ...get_selenium_locator_guidance
  requests  robotmcp.utils.requests_guidance.build_requests_cookbook
  visual    robotmcp.utils.visual_guidance.build_visual_cookbook
  results / waits / quoting / debug / explore: curated (rf-mcp has no equivalent topic; explore/debug reuse the
           wording of rf-mcp's hints.py (click intercepted, outside viewport -> label) and intent_action docs
           (force only for overlays, select match=label, reactive forms + change event)); every Browser claim in
           them is executed by verify/widgets_claims.robot on Browser 19.12 and 20.5
"""
from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any

OUT = Path(__file__).resolve().parents[1] / "rfmcp_skill" / "guides"

# rf-mcp text -> correction (applied to the generated rf-mcp part). Each one was checked live.
CORRECTIONS = [
    # Set Selector Prefix needs the frame-piercing separator, otherwise it is just cascaded with `>>`
    ("Set Selector Prefix    id=content-frame\nClick    .submit-button",
     "Set Selector Prefix    id=content-frame >>>\nClick    .submit-button    (prefix MUST end with >>>; reset: Set Selector Prefix    ${EMPTY})"),
    ("First select the frame, then the element inside",
     "There is no 'select frame' step in Browser: put the frame selector in front, `<frame> >>> <inner>`"),
]
REGEX_CORRECTIONS = [
    (re.compile(r"there is no string\s+`role=` engine\.?"),
     "the role engine ALSO works as a selector string: role=button[name=\"Sign in\"] (verified live)."),
    (re.compile(r"Text exact: text=Login"), "Text substring (case-insensitive): text=Login ; exact: text=\"Login\""),
]
LOCAL = [  # MCP tool names -> local commands
    (re.compile(r"get_session_state\([^)]*\)"), "rfmcp state aria"),
    (re.compile(r"\bget_session_state\b"), "rfmcp state aria"),
    (re.compile(r"get_locator_guidance\(library=\"?'?(\w+)\"?'?\)"), r"rfmcp guide \1"),
    (re.compile(r"\bget_locator_guidance\b"), "rfmcp guide"),
    (re.compile(r"\bvisual_check\(\.\.\., return_image=true\)"), "(no inline-image path in the skill arm)"),
    (re.compile(r"\bvisual_check tool with the image-return option\b"), "(no inline-image option in the skill arm)"),
    (re.compile(r"\bvisual_check\b"), "rfmcp state screenshot"),
    (re.compile(r"\bintent_action\(\.\.\., nth=N\)"), "`>> nth=N` (zero-based)"),
    (re.compile(r"\(also via intent_action nth=2\)"), ""),
    (re.compile(r"ROBOTMCP_SCREENSHOT_DIR"), ".rf/state"),
]


def localize(s: str) -> str:
    for a, b in CORRECTIONS:
        s = s.replace(a, b)
    for rx, rep in REGEX_CORRECTIONS:
        s = rx.sub(rep, s)
    for rx, rep in LOCAL:
        s = rx.sub(rep, s)
    return s


def render(obj: Any, indent: int = 0) -> str:
    pad = "  " * indent
    if isinstance(obj, dict):
        out = []
        for k, v in obj.items():
            if k in ("success", "library"):
                continue
            if isinstance(v, (dict, list)):
                out.append(f"{pad}{k}:")
                out.append(render(v, indent + 1))
            else:
                out.append(f"{pad}{k}: {v}")
        return "\n".join(x for x in out if x)
    if isinstance(obj, list):
        out = []
        for v in obj:
            if isinstance(v, dict) and "keyword" in v:
                line = "    ".join([v["keyword"], *map(str, v.get("arguments", []))])
                if v.get("assign_to"):
                    line = "${%s}=    %s" % (v["assign_to"], line)
                out.append(f"{pad}- {line}" + (f"      # {v['note']}" if v.get("note") else ""))
            elif isinstance(v, (dict, list)):
                out.append(render(v, indent + 1))
            else:
                out.append(f"{pad}- {v}")
        return "\n".join(out)
    return f"{pad}{obj}"


def server_locator_patterns() -> str:
    src = Path(__import__("robotmcp").__file__).parent / "domains" / "instruction" / "value_objects.py"
    text = src.read_text()
    m = re.search(r"7\. COMMON LOCATOR PATTERNS.*?\n(.*?)\n\s*8\. ", text, re.S)
    return m.group(1).rstrip() if m else ""


HEAD_BROWSER = """\
BROWSER LIBRARY (Playwright) -- LOCATORS, IFRAMES, SHADOW DOM   [rfmcp guide browser]

VERIFIED CORE (checked live with rfmcp on Browser 19.12 and 20.5):
- Strategies: css (default, no prefix needed), id=, text=, xpath= (or start with // ), data-test=/data-testid=.
- IFRAMES: Browser has NO "select frame" keyword. Put the frame selector in front and pierce it with >>>
      Fill Text    id=editor-frame >>> id=title    Draft
      Click        iframe[name="payment"] >>> text=Submit order
  Several steps in one frame:  Set Selector Prefix    id=editor-frame >>>   ...   Set Selector Prefix    ${EMPTY}
  `rfmcp state aria` prints one section per iframe with the exact frame selector to prefix.
- SHADOW DOM: css=, text= and id= pierce OPEN shadow roots automatically -> write the inner selector as if
  there were no shadow root:  Click    css=#shadow-btn  /  Get Text    text=Shadow says hi
  xpath does NOT pierce shadow roots; css:light= / text:light= deliberately do not pierce; closed roots unreachable.
- ROLE selectors work too: role=button[name="Sign in"] (exact accessible name; case-sensitive).
- STRICT MODE: a selector matching >1 element fails. Make it unique, or pick one: `css=.item >> nth=0` (zero-based).
- A cell STARTING with # is an RF comment: write `\\#submit`, `css=#submit` or `id=submit`.
- Before acting on an unknown page: `rfmcp state aria` (roles/names/text), then build a selector.
  ARIA lines like `button "Sign in"` are NOT selectors -> use text="Sign in" / css=button >> text=Sign in.
- Element keywords auto-wait up to the browser timeout (default 10 s) for the ELEMENT; values do not
  (getters with an operator retry only 1 s -> rfmcp guide waits). The rfmcp probe refuses a step early:
  NOT_FOUND (nothing matched after 1.5 s, 5 s in `run`; inside an iframe -> prints the `frame >>> selector` fix),
  NOT_VISIBLE (hidden styled input -> prints the label to click), COVERED (overlay/cookie banner -> close it).
- Custom widgets, dropdowns, dates, dialogs, new tabs, cookie banners: rfmcp guide explore.

--- rf-mcp get_locator_guidance(library="browser") (same content the MCP arm receives) ---
"""

HEAD_SELENIUM = """\
SELENIUMLIBRARY -- LOCATORS AND FRAMES   [rfmcp guide selenium]

VERIFIED CORE:
- Strategies: id:x / name:x / css:x / xpath:x / link:Text / partial link:Te (= works too: id=x).
  A bare value matches id or name only; bare `//...` is xpath.
- IFRAMES: Select Frame    id:frame-id   ...   Unselect Frame   (no >>> in SeleniumLibrary).
- SHADOW DOM: not pierced by css/xpath; use Browser library, or Execute Javascript returning the element.
- Selenium is not strict: with several matches it silently uses the FIRST one.

--- rf-mcp get_locator_guidance(library="selenium") ---
"""

HEAD_REQUESTS = """\
REQUESTSLIBRARY -- API TESTING   [rfmcp guide requests]

VERIFIED CORE:
- Create Session    api    http://127.0.0.1:8000        (alias + base URL)
- ${resp}=    GET On Session    api    /users.json    expected_status=200
- Status Should Be    200    ${resp}
- ${data}=    Set Variable    ${resp.json()}            (outside Evaluate: ${resp.json()}; inside Evaluate: $resp.json())
- Should Be Equal As Strings    ${resp.json()}[0][name]    Ann
- ${resp}=    POST On Session    api    /items    json=${body}    (json= for JSON bodies, NOT data=)
- ${resp}=    GET On Session    api    /missing    expected_status=404     (non-2xx without failing)
- `rfmcp doc "POST On Session"` shows the real parameters (alias, url, data, json, expected_status, msg, **kwargs).

--- rf-mcp get_locator_guidance(library="requests") (same content the MCP arm receives) ---
"""

HEAD_VISUAL = """\
VISUAL CHECKS / SCREENSHOTS   [rfmcp guide visual]

- `rfmcp state screenshot` saves a PNG under .rf/state/ and prints its path; read the image only if your model
  is multimodal. Prefer Get Text / Get Attribute / Get Element States when the value is in the DOM.

--- rf-mcp get_locator_guidance(library="visual") ---
"""

RESULTS = """\
RESULTS / output.xml ANALYSIS   [rfmcp guide results]

Run:
  robot -d results tests/                      # or: robotcode robot -d results tests/
  robot -d results -t "Login*" -i smoke tests/ # select by test name / tag;  --dryrun = syntax/keyword check only
  Exit code = number of failed tests (0 = all passed). Files: results/output.xml, log.html, report.html.

Inspect a finished run WITHOUT re-running (robotcode results; -o selects the file, default from robot.toml):
  robotcode results summary -o results/output.xml            # counts + overall status
  robotcode results show --failed -o results/output.xml      # one line per failed test: name, path:line, message
  robotcode results log "*Login*" -o results/output.xml      # keyword tree of matching tests (args, messages)
  robotcode results stats --by tag -o results/output.xml     # aggregate by tag/suite/status
  robotcode results diff old/output.xml new/output.xml       # status changes between runs
  robotcode --format json results summary -o results/output.xml   # machine-readable
  NOTE: `-o` belongs AFTER the subcommand (robotcode results show -o FILE).

Custom analysis with Robot Framework's API (no extra packages):
  python - <<'PY'
  from robot.api import ExecutionResult, ResultVisitor
  res = ExecutionResult("results/output.xml")
  s = res.statistics.total
  print("passed", s.passed, "failed", s.failed, "skipped", s.skipped)
  class Failed(ResultVisitor):
      def visit_test(self, test):
          if test.status == "FAIL":
              print(test.full_name, "|", test.message.splitlines()[0] if test.message else "", "|", test.elapsed_time)
  res.visit(Failed())
  for t in res.suite.all_tests:               # every test: name, status, tags, elapsed
      print(t.name, t.status, list(t.tags), t.elapsed_time.total_seconds())
  PY
  Keyword level: walk test.body (kw.name, kw.status, kw.args, kw.message, kw.elapsed_time; nested kw.body).
  Merge/re-report: rebot --merge -d merged a/output.xml b/output.xml ; rebot --output NONE --log log2.html output.xml
"""

WAITS = """\
WAITS AND TIMEOUTS   [rfmcp guide waits]   (verified on Browser 19.12 and 20.5)

Browser library:
- Element keywords (Click, Fill Text, Get Text ...) auto-wait for the ELEMENT (attached, visible, enabled) up to
  the browser timeout (default 10 s; Set Browser Timeout    20s).
- VALUES do not wait: a getter WITHOUT an assertion operator returns the current value at once
      ${t}=    Get Text    id=status          -> "Loading..."      ${n}=    Get Element Count    css=.row    -> 0
- A getter WITH an assertion operator retries only `retry_assertions_for` = 1 s by default (not 10 s!):
      Get Text    id=status    ==    Done          Get Element Count    css=.row    >=    3
- Slower async UI (spinner, search results, toast) -> wait with the full timeout:
      Wait For Condition    Text    id=status    contains    Done    timeout=15s
      Wait For Condition    Element Count    css=.row    ==    3
      Wait For Elements State    id=spinner    hidden    timeout=15s
      Wait For Elements State    css=.row >> nth=2    visible    timeout=15s
  or raise the retry for the suite/test: Set Retry Assertions For    10s   (Library    Browser    retry_assertions_for=10s)
- After navigation: Get Url    contains    /home   or   Wait For Load State    networkidle
- Do NOT add Sleep; use a condition/state wait instead.
SeleniumLibrary: Wait Until Element Is Visible    id:x    10s ; Wait Until Page Contains    text ;
                 Set Selenium Timeout    10s ; Set Selenium Implicit Wait (avoid mixing with explicit waits).
BuiltIn: Wait Until Keyword Succeeds    10s    1s    <keyword>    <args>
rfmcp: a single call returns after 25 s with {"status":"running","job":N}; then `rfmcp wait N`.
  The rfmcp probe refuses a Browser element step when nothing matches after 1.5 s (`step`) / 5 s (`run`, later lines
  of one `step`): page still loading -> repeat the call, or add --no-guard.
"""

DEBUG = """\
DEBUGGING AN EXISTING FAILING SUITE   [rfmcp guide debug]

RULES: fix the TEST code (locators, waits, imports, keyword usage, test data handling). Keep every test and the
intent of every assertion: never delete or skip tests, never loosen/remove assertions (== -> contains, Run Keyword
And Ignore Error, deleting a check). Change an expected literal only if the app clearly renamed it, and say so.

1. Run it as is and read the failures (no helper needed for this):
     robot -d results path/suite.robot
     robotcode results show --failed -o results/output.xml          # test, file:line, message
     robotcode results log "*Test Name*" -o results/output.xml      # keyword tree: failing step + args
   Classify by message: timeout / "waiting for locator" on a selector -> locator (or element hidden/covered);
   "should be/contain" with an intermediate value ("Loading...", 0, empty) -> missing wait; "No keyword with name" ->
   import/typo; ModuleNotFoundError / "does not exist" on an import -> import path (PORTABLE below).
2. Static problems: rfmcp check path/suite.robot   (works without the helper)
3. Reproduce live; the helper stops AT the failing line and keeps the page open (teardowns are not run):
     rfmcp run path/suite.robot --test "Test Name"        # Suite Setup + setup + body until the first failure
   A failure inside a user keyword is reported on the calling test line (`failed_in` = the inner keyword).
   NOT RUN + guard NOT_FOUND / NOT_VISIBLE / COVERED = the selector matches nothing / a hidden element / an
   element under an overlay -> `fix` says what to do.
4. Look at the page in that state: rfmcp state controls (fields/buttons, ids, data-test, hidden inputs),
   rfmcp state aria (texts, roles, iframes), rfmcp state url, rfmcp state screenshot.
5. Try the candidate fix right there: rfmcp step 'Click    data-test=submit'  /  rfmcp step 'Wait For Condition ...'
6. Edit the file (or the .resource with the keyword; it is re-imported automatically), then continue:
     rfmcp run path/suite.robot --test "Test Name"        # resumes at the fixed line
     Changed a line that already ran? --lines A-B re-runs those lines, --rebase accepts them, or rfmcp stop + run.
   A live re-run of a WAIT fix is weak evidence (the page has finished loading meanwhile): the final run decides.
7. Fix every failing test, then the proof: robot -d results path/suite.robot  (fresh browser, all tests).
   rfmcp stop.

Typical fixes (Browser library):
- stale locator -> pick a stable one from rfmcp state controls: data-test=..., id=..., role=button[name="Save"],
  text="Save"; avoid long CSS chains / nth-child / generated ids.
- missing wait -> a getter without operator does not wait, with operator it retries only 1 s:
      Wait For Condition    Text    id=status    contains    Saved    timeout=15s
      Wait For Elements State    id=spinner    hidden    timeout=15s       (never Sleep; see rfmcp guide waits)
- element covered (cookie banner, modal): close it first; force=True would click the overlay instead.
- hidden styled radio/checkbox, custom dropdown, dialogs, new tabs, dates: rfmcp guide explore
- element inside an iframe: `id=frame >>> id=field` (rfmcp guide browser)
- PORTABLE: the suite must pass with plain `robot <file>`: Library    ${CURDIR}/../lib/MyLib.py (by path, never
  -P / PYTHONPATH / robot.toml); `rfmcp check` flags imports that only the helper/robotcode resolve.
API suites: rfmcp run ... stops at the failing request; inspect with rfmcp vars resp or
  rfmcp step 'Log    ${resp.json()}    console=True' (rfmcp guide requests).
"""

EXPLORE = """\
EXPLORING AN UNKNOWN LIVE PAGE + CUSTOM WIDGETS   [rfmcp guide explore]   (verified on Browser 19.12 and 20.5)

Open it and LOOK before writing any selector:
  rfmcp step 'Import Library    Browser' 'New Browser    chromium    headless=True' 'New Page    https://app.example'
  rfmcp state controls   # every field/button/link: label, id, name, data-test, hidden?, native/custom, => selector
  rfmcp state aria       # texts, roles, accessible names, one section per iframe
Look again after every click that changes the page. Read messages from the page (Get Text) instead of guessing.

Selectors, most stable first: data-test=x / data-testid=x > id=x (not generated ones like id=r12, ember34) >
  role=textbox[name="E-mail"] / role=button[name="Save"] (name = label / aria-label / text) > text="Save" >
  short attribute CSS input[name="email"] > xpath. Avoid long CSS chains, nth-child, generated class names.
  By label/placeholder: ${e}=    Get Element By    Label    E-mail   then   Fill Text    ${e}    me@x.org

Cookie banner / overlay: close it first (Click    text=Accept all). The rfmcp probe reports COVERED. A click that
  fails with "intercepts pointer events" is covered too; Click With Options ... force=True does NOT help (the click
  lands on the overlay, passes, and nothing happens).

Styled radio / checkbox (the real <input> is hidden, a label/span is drawn instead): Check Checkbox / Click on the
  input waits for visibility and fails (rfmcp probe: NOT_VISIBLE + the label to click). Click the visible label:
      Click    label[for="opt-yes"]         Click    label:has(#newsletter)         Click    text=Round trip
  Assert on the input (works while hidden): Get Checkbox State    id=opt-yes    ==    checked

Dropdowns:
  native <select> (aria: combobox WITH option children; controls: "native select"):
      Select Options By    id=country    label    Germany          (or value    de  /  index    2)
      Get Selected Options    id=country    label    ==    Germany  (attribute BEFORE the operator)
  custom dropdown (button/div, role=combobox/listbox; Select Options By fails "Element is not a <select> element"):
      Click    id=country-picker    ->  rfmcp state aria  ->  Click    role=option[name="Germany"]   (or text=Germany)
      Get Text    id=country-picker    ==    Germany

Dates (add `Library    DateTime`): never hard-code a date that expires.
      ${d}=    Get Current Date    increment=7 days    result_format=%Y-%m-%d       # today + 7
      ${r}=    Add Time To Date    ${d}    14 days    result_format=%m/%d/%Y         # from another date
  <input type=date>: Fill Text    id=start    ${d}   with %Y-%m-%d (shown localized). Text fields: the format of
  their placeholder/label (%d.%m.%Y, %m/%d/%Y ...). Calendar pop-ups: try Fill Text on the input first; else open it
  and click the day (rfmcp state aria).

JavaScript alert/confirm/prompt: without a handler they are DISMISSED (confirm() -> false, nothing happens).
      Handle Future Dialogs    action=accept    prompt_input=My text   # ONCE per page, BEFORE the click; stays active
      ${p}=    Promise To    Wait For Alert    action=accept    text=Delete item?   /  Click ...  /  Wait For    ${p}
  One handler per page: a 2nd Handle Future Dialogs (Browser 19.x) or mixing it with Wait For Alert -> two handlers
  -> the Playwright process crashes and every later test fails. Different answers on one page: one
  `Promise To    Wait For Alert` per dialog (accept/dismiss, prompt_input=...) and no Handle Future Dialogs there.
  In-page modals (role=dialog) are normal elements.

New tab / popup:  Click    text=Help   ->   ${prev}=    Switch Page    NEW   ...   Switch Page    ${prev}

Async UI: values do not wait; assertion operators retry only 1 s -> Wait For Condition    Text    id=status
  contains    Done    timeout=15s / Wait For Elements State    id=spinner    hidden    timeout=15s (rfmcp guide waits).
Form ignores a filled value ("required" while text is shown): Fill Text fires `input` but not `change`; leave the
  field: Press Keys    id=email    Tab
"""

QUOTING = """\
SHELL QUOTING FOR rfmcp step   [rfmcp guide quoting]

- One RF line per argument string; separate keyword and arguments with 4 spaces (2+ works, one space does not).
- Wrap the line in SINGLE quotes: rfmcp step 'Fill Text    id=user    ${USER}'   (${...} stays literal for RF)
- Line contains a single quote, or several lines (FOR/IF blocks)? Use a QUOTED heredoc (the quotes around RF
  stop the shell from touching $ { } \\ ):
    rfmcp step - <<'RF'
    ${n}=    Get Element Count    css=.row
    IF    ${n} > 2
        Log    many rows
    END
    RF
- Never double-quote cells that contain ${...} or $var (the shell expands them).
- Escape RF specials as in a .robot file: \\# for a literal #, ${EMPTY} for empty strings, ${SPACE} for spaces.
- One rfmcp call at a time, never in parallel or in the background: the session is shared and serialized.
- For longer flows prefer writing the .robot file with your edit tool and `rfmcp run FILE --new`: no quoting at all.
"""


def main() -> int:
    from robotmcp.utils.requests_guidance import build_requests_cookbook
    from robotmcp.utils.rf_native_type_converter import RobotFrameworkNativeConverter
    from robotmcp.utils.visual_guidance import build_visual_cookbook

    c = RobotFrameworkNativeConverter()
    OUT.mkdir(parents=True, exist_ok=True)
    br = c.get_browser_locator_guidance()
    for err in ("strict mode violation: resolved to 2 elements", "element not found waiting for selector timeout",
                "shadow root", "iframe frame"):
        for k, v in c._analyze_browser_error(err, "Click").items():
            br.setdefault(k, v)
    browser = HEAD_BROWSER + localize(render(br)) + "\n\n--- rf-mcp server instructions: COMMON LOCATOR PATTERNS ---\n" \
        + localize(server_locator_patterns()) + "\n"
    files = {
        "browser.txt": browser,
        "selenium.txt": HEAD_SELENIUM + localize(render(c.get_selenium_locator_guidance())) + "\n",
        "requests.txt": HEAD_REQUESTS + localize(render(build_requests_cookbook())) + "\n",
        "visual.txt": HEAD_VISUAL + localize(render(build_visual_cookbook())) + "\n",
        "results.txt": RESULTS,
        "debug.txt": DEBUG,
        "explore.txt": EXPLORE,
        "waits.txt": WAITS,
        "quoting.txt": QUOTING,
    }
    for name, text in files.items():
        (OUT / name).write_text(text)
        print(f"{name}: {len(text)} chars")
    return 0


if __name__ == "__main__":
    sys.exit(main())
