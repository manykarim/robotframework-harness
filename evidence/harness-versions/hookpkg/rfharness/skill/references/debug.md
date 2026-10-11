# Debugging an existing failing suite

RULES: fix the TEST code (locators, waits, imports, keyword usage, test data handling). Keep every test and the
intent of every assertion: never delete or skip tests, never loosen/remove assertions (== -> contains, Run Keyword
And Ignore Error, deleting a check). Change an expected literal only if the app clearly renamed it, and say so.

1. Run it as is: `robot -d results path/suite.robot`. The hook attaches, from output.xml:
   - one line per failed test: name, file:line, failing keyword, message;
   - a LIVE REPRODUCTION of the first failing test: re-run from the top in the hook's session, stopped AT the failing
     line with the page left open; page summary (title, url, controls with suggested selectors); full state in
     .rf/state/controls.txt, aria.yaml, source.html, screenshot.png.
   More detail without re-running: `robotcode results show --failed -o results/output.xml`,
   `robotcode results log "*Test Name*" -o results/output.xml` (keyword tree with arguments).
2. Classify by message: timeout / "waiting for locator" / NOT_FOUND -> locator (or element hidden/covered: NOT_VISIBLE,
   COVERED with the fix); "should be/contain" with an intermediate value ("Loading...", 0, empty) -> missing wait;
   "No keyword with name" -> import/typo; ModuleNotFoundError / "does not exist" on an import -> import path.
3. Fix the failing line with your edit tool (or the .resource keyword it calls). The hook re-runs it right away, in the
   page that is still open, and continues to the end of the test or the next failure. A failure inside a user keyword
   is reported on the calling test line (`failed inside: <keyword>`): fix the keyword, the failed line re-runs.
4. Editing a line of another failing test runs that test (from its setup). Changing a line that already passed
   restarts that test from the top.
5. A live re-run of a WAIT fix is weak evidence (the page has finished loading meanwhile): the plain run decides.
6. Fix every failing test, then the proof: `robot -d results path/suite.robot` (fresh browser, all tests). After a
   green run the hook records the suite as verified; at the end of your turn a gate asks for this run if a test file
   changed since its last green plain run.

Typical fixes (Browser library):
- stale locator -> pick a stable one from .rf/state/controls.txt: data-test=..., id=..., role=button[name="Save"],
  text="Save"; avoid long CSS chains / nth-child / generated ids.
- missing wait -> a getter without operator does not wait, with operator it retries only 1 s:
      Wait For Condition    Text    id=status    contains    Saved    timeout=15s
      Wait For Elements State    id=spinner    hidden    timeout=15s       (never Sleep; references/waits.md)
- element covered (cookie banner, modal): close it first; force=True would click the overlay instead.
- hidden styled radio/checkbox, custom dropdown, dialogs, new tabs, dates: references/explore.md
- element inside an iframe: `id=frame >>> id=field` (references/browser.md)
- PORTABLE: the suite must pass with plain `robot <file>`: Library    ${CURDIR}/../lib/MyLib.py (by path, never
  -P / PYTHONPATH / robot.toml).
API suites: the reproduction stops at the failing request; the message shows status/body. Log values with
  `Log    ${resp.json()}` lines while debugging (references/requests.md).
