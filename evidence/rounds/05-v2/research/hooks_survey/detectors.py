#!/usr/bin/env python3
"""Prototype detectors for RF guidance hooks (stdlib only, < 1 ms each).

1. weakening_findings(before, after)  -> assertion-weakening / test-deletion guard
   (PreToolUse on Write/Edit/apply_patch of *.robot / *.resource, debug tasks).
2. LoopDetector                        -> repeated identical failure signature
   (PostToolUse / PostToolUseFailure on Bash robot|repl and on hook-run steps).
3. bash_guard(cmd)                     -> PreToolUse Bash policy (env mutation,
   PYTHONPATH workarounds, huge-artifact reads, REPL launch hints).

Run `python3 detectors.py` for the unit-style examples.
"""
import re, hashlib, json

# --------------------------------------------------------------------------
# 1. assertion-weakening / test-deletion detector
# --------------------------------------------------------------------------
SECTION_RX = re.compile(r"^\*{1,3}\s*([A-Za-z ]+?)\s*\*{0,3}\s*$")
SEP = re.compile(r"\s{2,}|\t")
ASSERT_KW = re.compile(
    r"^(Should\b|Wait Until\b|Page Should\b|Element Should\b|Element Text Should\b|"
    r"Title Should\b|Location Should\b|Checkbox Should\b|List Selection Should\b|"
    r"Textfield (Value )?Should\b|Table .*Should\b|Status Should Be|Request Should Be|"
    r"Response Should|Dictionary Should|List Should|Lists Should|Length Should|"
    r"Variable Should|Keyword Should|Get \w[\w ]*|Wait For Elements State|Check\b|Verify\b|Assert\b)",
    re.I)
# Browser Get* keywords only assert when an assertion operator is passed.
BROWSER_OPS = {"==", "!=", "<", ">", "<=", ">=", "*=", "^=", "$=", "$", "validate", "then",
               "equal", "equals", "should be", "inequal", "should not be", "less than",
               "greater than", "contains", "not contains", "starts", "ends", "matches",
               "evaluate"}
WEAK_OP = {"==": {"*=", "contains", "^=", "starts", "$=", "ends", "matches", "!=", "not contains"},
           "should be": {"contains", "*="}, "equal": {"contains", "*="}}
STRONG_TO_WEAK_KW = [("Should Be Equal", "Should Contain"), ("Should Be Equal As Strings", "Should Contain"),
                     ("Should Be Equal As Numbers", "Should Be True"), ("Should Contain", "Should Not Be Empty"),
                     ("Element Text Should Be", "Element Should Contain"), ("Title Should Be", "Get Title")]
SWALLOW = re.compile(r"Run Keyword And (Ignore Error|Return Status|Warn On Failure)|"
                     r"Run Keyword And Expect Error\s{2,}\*", re.I)
SKIP = re.compile(r"^(Skip|Skip If|Pass Execution|Pass Execution If|No Operation)\b", re.I)
SKIP_TAG = re.compile(r"robot:(skip|exclude|skip-on-failure)", re.I)


def _cells(line):
    return [c for c in SEP.split(line.strip()) if c != ""]


def parse_tests(text):
    """Return {test_name: [body cells-lists]} for *** Test Cases *** / Tasks and
    {kw_name: [...]} for *** Keywords *** (prefixed 'kw:')."""
    out, section, cur = {}, None, None
    for raw in text.replace("\r\n", "\n").split("\n"):
        m = SECTION_RX.match(raw)
        if m:
            name = m.group(1).strip().lower()
            section = "test" if name.startswith(("test case", "task")) else ("kw" if name.startswith("keyword") else None)
            cur = None
            continue
        if section is None or not raw.strip() or raw.lstrip().startswith("#"):
            continue
        if not raw[0].isspace():
            cur = ("" if section == "test" else "kw:") + raw.strip().split("  ")[0]
            out[cur] = []
            continue
        if cur is not None:
            cells = _cells(raw)
            if cells and cells[0] == "..." and out[cur]:
                out[cur][-1].extend(cells[1:])
            elif cells:
                out[cur].append(cells)
    return out


def _strip_assign(cells):
    i = 0
    while i < len(cells) and re.match(r"^[$@&]\{.*\}\s*=?$", cells[i]):
        i += 1
    return cells[i:]


def is_assertion(cells):
    c = _strip_assign(cells)
    if not c:
        return False
    kw = c[0]
    if re.match(r"^Get \w", kw, re.I):  # Browser getter: assertion only with operator
        return any(a.strip().lower() in BROWSER_OPS for a in c[1:4])
    if kw.upper() in ("IF", "ELSE", "END", "FOR", "TRY", "EXCEPT", "FINALLY", "WHILE", "VAR", "RETURN"):
        return False
    return bool(ASSERT_KW.match(kw))


def _assert_sig(cells):
    c = _strip_assign(cells)
    return (c[0].lower(), c[1] if len(c) > 1 else "")


def _secs(v):
    m = re.match(r"^\s*(\d+(?:\.\d+)?)\s*(ms|s|sec|seconds?|min|minutes?)?\s*$", v.strip(), re.I)
    if not m:
        return 0
    n, u = float(m.group(1)), (m.group(2) or "s").lower()
    return n / 1000 if u == "ms" else n * 60 if u.startswith("min") else n


def weakening_findings(before, after):
    """Compare two versions of a .robot file; return list of findings
    {sev: block|warn, rule, test, detail}. 'block' = deny in debug tasks."""
    b, a = parse_tests(before), parse_tests(after)
    f = []
    for name in b:
        if name.startswith("kw:"):
            continue
        if name not in a:
            f.append({"sev": "block", "rule": "test-deleted", "test": name,
                      "detail": "test case removed (or renamed)"})
    for name, body_a in a.items():
        body_b = b.get(name)
        if body_b is None:
            continue
        n_b = sum(is_assertion(x) for x in body_b)
        n_a = sum(is_assertion(x) for x in body_a)
        if n_a < n_b:
            f.append({"sev": "block" if not name.startswith("kw:") else "warn", "rule": "assertions-removed",
                      "test": name, "detail": f"{n_b} -> {n_a} assertions"})
        # newly swallowed failures
        sw_b = sum(bool(SWALLOW.search("  ".join(x))) for x in body_b)
        sw_a = sum(bool(SWALLOW.search("  ".join(x))) for x in body_a)
        if sw_a > sw_b:
            f.append({"sev": "block", "rule": "failure-swallowed", "test": name,
                      "detail": "Run Keyword And Ignore Error/Return Status added"})
        tryex_b = sum(1 for x in body_b if x and x[0] == "EXCEPT")
        tryex_a = sum(1 for x in body_a if x and x[0] == "EXCEPT")
        if tryex_a > tryex_b:
            f.append({"sev": "warn", "rule": "try-except-added", "test": name,
                      "detail": "new TRY/EXCEPT: make sure EXCEPT re-raises or asserts"})
        sk_b = sum(bool(SKIP.match(x[0])) for x in body_b if x)
        sk_a = sum(bool(SKIP.match(x[0])) for x in body_a if x)
        tag_a = sum(bool(SKIP_TAG.search("  ".join(x))) for x in body_a)
        tag_b = sum(bool(SKIP_TAG.search("  ".join(x))) for x in body_b)
        if sk_a > sk_b or tag_a > tag_b:
            f.append({"sev": "block", "rule": "skip-added", "test": name,
                      "detail": "Skip/Pass Execution/No Operation/robot:skip added"})
        # changed expected values / weaker operator on the same keyword+locator
        sigs_b = {}
        for x in body_b:
            if is_assertion(x):
                sigs_b.setdefault(_assert_sig(x), []).append(_strip_assign(x))
        for x in body_a:
            if not is_assertion(x):
                continue
            c = _strip_assign(x)
            olds = sigs_b.get(_assert_sig(x))
            if not olds or c in olds:
                continue
            old = olds[0]
            old_ops = [t.lower() for t in old[2:4] if t.lower() in BROWSER_OPS]
            new_ops = [t.lower() for t in c[2:4] if t.lower() in BROWSER_OPS]
            if old_ops and new_ops and new_ops[0] in WEAK_OP.get(old_ops[0], set()):
                f.append({"sev": "warn", "rule": "operator-weakened", "test": name,
                          "detail": f"{c[0]} {c[1]}: '{old_ops[0]}' -> '{new_ops[0]}'"})
            elif old[2:] != c[2:]:
                strip_t = lambda xs: [t for t in xs if not t.lower().startswith("timeout=")]
                tsec = lambda xs: max([_secs(t.split("=", 1)[1]) for t in xs if t.lower().startswith("timeout=")] or [0])
                if strip_t(old[2:]) == strip_t(c[2:]) and tsec(c[2:]) > tsec(old[2:]):
                    f.append({"sev": "warn", "rule": "timeout-raised", "test": name,
                              "detail": f"{c[0]} {c[1]}: timeout {tsec(old[2:]) or 'default'}s -> {tsec(c[2:])}s"})
                else:
                    f.append({"sev": "warn", "rule": "expected-value-changed", "test": name,
                              "detail": f"{c[0]} {c[1]}: {old[2:]} -> {c[2:]}"})
        kws_b = {_strip_assign(x)[0] for x in body_b if _strip_assign(x)}
        kws_a = {_strip_assign(x)[0] for x in body_a if _strip_assign(x)}
        for strong, weak in STRONG_TO_WEAK_KW:
            if strong in kws_b and strong not in kws_a and weak in kws_a and weak not in kws_b:
                f.append({"sev": "warn", "rule": "assert-keyword-weakened", "test": name,
                          "detail": f"{strong} -> {weak}"})
    return f


# --------------------------------------------------------------------------
# 2. repeated-failure loop detector
# --------------------------------------------------------------------------
FAIL_LINE = re.compile(r"(\|\s*FAIL\s*\||\[ FAIL \]|^FAIL\b|Error: |TimeoutError|No keyword with name|"
                       r"Element .* not|did not|should (be|contain)|Expected)", re.I)


def failure_signature(output):
    """Normalise the failure lines of a robot / repl / hook output into a short
    hash. Numbers, durations, temp paths and ids are masked so that 'same
    selector timed out again' collides while a different selector does not."""
    lines = []
    for ln in output.replace("\r", "").split("\n"):
        if not FAIL_LINE.search(ln):
            continue
        ln = re.sub(r"/[\w./-]+/", "/P/", ln)
        ln = re.sub(r"\b\d+(\.\d+)?\s*(ms|s|sec|seconds?)\b", "T", ln)
        ln = re.sub(r"\b\d+\b", "N", ln)
        ln = re.sub(r"\s+", " ", ln).strip()
        lines.append(ln[:200])
    if not lines:
        return None
    return hashlib.sha1("\n".join(sorted(set(lines))[:6]).encode()).hexdigest()[:12], lines[0]


class LoopDetector:
    """Feed tool outputs; fires once per signature when it repeats `threshold`
    times without an intervening different signature for that target, or when
    the same file is edited `edit_threshold` times while failures persist."""

    def __init__(self, threshold=3, edit_threshold=8):
        self.threshold, self.edit_threshold = threshold, edit_threshold
        self.counts, self.fired, self.edits_since_green = {}, set(), {}

    def on_output(self, output):
        sig = failure_signature(output)
        if sig is None:
            if re.search(r"\|\s*PASS\s*\||\b0 failed\b", output):
                self.counts.clear(); self.edits_since_green.clear()
            return None
        h, first = sig
        self.counts[h] = self.counts.get(h, 0) + 1
        if self.counts[h] >= self.threshold and h not in self.fired:
            self.fired.add(h)
            return {"rule": "same-failure-repeated", "count": self.counts[h], "failure": first,
                    "message": (f"The same failure has now occurred {self.counts[h]}x: '{first[:140]}'. "
                                "Stop editing blindly: inspect the live state first (robot-debug pause on "
                                "failure, or Grep .rf/state/latest/page.html / aria.yaml for the element), "
                                "then change one thing.")}
        return None

    def on_edit(self, path):
        if not path.endswith((".robot", ".resource")) or not self.counts:
            return None
        n = self.edits_since_green[path] = self.edits_since_green.get(path, 0) + 1
        if n == self.edit_threshold:
            return {"rule": "edit-churn", "count": n, "path": path,
                    "message": f"{path} edited {n}x since the last green run while failures persist; "
                               "re-read the failing step's docs (.rf/docs) and the captured page before the next edit."}
        return None


# --------------------------------------------------------------------------
# 3. Bash command guard
# --------------------------------------------------------------------------
BASH_RULES = [
    ("env-mutation", "deny",
     r"(^|[;&|]\s*|\s)(pip3?|python3? -m pip|uv pip)\s+install\b|\buv\s+(add|sync)\b|"
     r"\b(rfbrowser|python3? -m Browser\.entry)\s+(init|install)\b|\bplaywright\s+install\b|\bnpx\s+playwright\s+install\b",
     "Do not install packages or browsers: the venv and Playwright browsers are provisioned and shared. "
     "If an import fails, report it (run `robotcode libdoc <Lib> version` to check)."),
    ("pythonpath-workaround", "deny",
     r"(\brobot(code)?\b[^\n;&|]*\s(-P|--pythonpath)\s)|\bPYTHONPATH=",
     "Don't patch the import path ad hoc; the suite must run with the plain project command. "
     "Fix the import (relative `Resource ../resources/x.resource`) or add `python-path` to robot.toml."),
    ("huge-artifact-read", "rewrite_hint",
     r"\b(cat|less|more|head -n ?\d{4,}|sed -n '1,\d{4,}p')\b[^\n;&|]*(output\.xml|log\.html|report\.html|page\.html|\.rf/state/[^ ]*source)",
     "That file is large. Use `robotcode results show/log -o <output.xml>` for failures, or "
     "`grep -n -m 20 '<text>' <file>` / Read with offset+limit."),
    ("repl-launch", "context",
     r"\brobotcode\b[^\n]*\b(repl|robot-debug)\b",
     "<format card injected here>"),
    ("shell-sleep-poll", "context",
     r"(^|[;&|]\s*)sleep\s+([3-9]|\d{2,})\b",
     "Avoid fixed sleeps; in RF use Wait For Elements State / Wait Until ... with an explicit timeout."),
]


def bash_guard(cmd):
    hits = []
    for rid, action, rx, msg in BASH_RULES:
        if re.search(rx, cmd):
            hits.append({"rule": rid, "action": action, "message": msg})
    return hits


# --------------------------------------------------------------------------
# unit-style examples
# --------------------------------------------------------------------------
BEFORE = """*** Settings ***
Library    Browser

*** Test Cases ***
Order Total Is Correct
    New Page    http://localhost:8000/shop.html
    Click    id=add
    Get Text    id=total    ==    42.00 EUR
    Should Be Equal    ${status}    PAID
    Element Text Should Be    id=msg    Thank you

Login Works
    Fill Text    id=user    bob
    Get Url    ==    http://localhost:8000/home

*** Keywords ***
Check Cart
    Get Element Count    css=.item    ==    3
"""


def _run_examples():
    ok = 0
    cases = [
        ("unchanged", BEFORE, set()),
        ("delete test", BEFORE.replace("Login Works\n    Fill Text    id=user    bob\n    Get Url    ==    http://localhost:8000/home\n", ""), {"test-deleted"}),
        ("remove assertion", BEFORE.replace("    Should Be Equal    ${status}    PAID\n", ""), {"assertions-removed"}),
        ("wrap ignore error", BEFORE.replace("    Should Be Equal    ${status}    PAID",
                                             "    Run Keyword And Ignore Error    Should Be Equal    ${status}    PAID"),
         {"failure-swallowed"}),
        ("operator weakened", BEFORE.replace("Get Text    id=total    ==    42.00 EUR", "Get Text    id=total    *=    EUR"),
         {"operator-weakened"}),
        ("expected changed", BEFORE.replace("==    42.00 EUR", "==    41.00 EUR"), {"expected-value-changed"}),
        ("skip added", BEFORE.replace("    Click    id=add\n", "    Skip    flaky\n    Click    id=add\n"), {"skip-added"}),
        ("legit locator fix", BEFORE.replace("Click    id=add", "Click    css=button#add-to-cart"), set()),
        ("legit wait added", BEFORE.replace("    Click    id=add\n", "    Wait For Elements State    id=add    visible    timeout=10s\n    Click    id=add\n"), set()),
        ("timeout raised", BEFORE.replace("Get Text    id=total    ==    42.00 EUR", "Get Text    id=total    ==    42.00 EUR    timeout=30s").replace("Get Url    ==    http://localhost:8000/home", "Get Url    ==    http://localhost:8000/home"), {"timeout-raised"}),
        ("kw assertion removed", BEFORE.replace("    Get Element Count    css=.item    ==    3\n", "    Log    skipped\n"), {"assertions-removed"}),
        ("strong->weak kw", BEFORE.replace("Element Text Should Be    id=msg    Thank you", "Element Should Contain    id=msg    Thank"),
         {"assert-keyword-weakened"}),
    ]
    for name, after, want in cases:
        got = {x["rule"] for x in weakening_findings(BEFORE, after)}
        good = bool(want <= got and (want or not got))
        ok += good
        print(f"[{'ok' if good else 'XX'}] weakening: {name:22s} -> {sorted(got)}")

    det = LoopDetector()
    outs = ["Order Total | FAIL |\nTimeoutError: locator('id=totl') 10000ms exceeded",
            "Order Total | FAIL |\nTimeoutError: locator('id=totl') 10000ms exceeded",
            "Order Total | FAIL |\nTimeoutError: locator('id=totl') 9999ms exceeded"]
    fired = [det.on_output(o) for o in outs]
    good = fired[0] is None and fired[1] is None and fired[2] and fired[2]["rule"] == "same-failure-repeated"
    ok += bool(good); print(f"[{'ok' if good else 'XX'}] loop: same selector timeout x3 fires on 3rd")
    det2 = LoopDetector()
    outs2 = ["X | FAIL |\nTimeoutError: locator('id=a') exceeded", "X | FAIL |\nTimeoutError: locator('id=b') exceeded",
             "X | FAIL |\nTimeoutError: locator('id=c') exceeded"]
    good = all(det2.on_output(o) is None for o in outs2)
    ok += good; print(f"[{'ok' if good else 'XX'}] loop: different selectors never fire")
    det3 = LoopDetector()
    det3.on_output(outs[0]); det3.on_output("X | PASS |"); r = det3.on_output(outs[0]); r2 = det3.on_output(outs[0])
    good = r is None and r2 is None
    ok += good; print(f"[{'ok' if good else 'XX'}] loop: green run resets counter")

    bcases = [("pip install robotframework-browser", {"env-mutation"}),
              ("cd ws && rfbrowser init chromium", {"env-mutation"}),
              ("uv add robotframework-requests", {"env-mutation"}),
              ("robot -P lib tests/", {"pythonpath-workaround"}),
              ("PYTHONPATH=. robot tests", {"pythonpath-workaround"}),
              ("robot --outputdir out tests/x.robot", set()),
              ("cat out/output.xml", {"huge-artifact-read"}),
              ("grep -n FAIL out/output.xml | head", set()),
              ("robotcode repl --plain --no-history -d out <<'RF'\nLibrary  Browser\nRF", {"repl-launch"}),
              ("echo 'pip install x' > notes.txt", set()),  # quoted data: not flagged
              ("sleep 5 && curl localhost:8000", {"shell-sleep-poll"})]
    for cmd, want in bcases:
        got = {x["rule"] for x in bash_guard(cmd)}
        good = got == want
        ok += good
        print(f"[{'ok' if good else 'XX'}] bash: {cmd[:48]:48s} -> {sorted(got)}")
    total = 12 + 3 + len(bcases)
    print(f"{ok}/{total} examples as expected")
    return ok, total


if __name__ == "__main__":
    _run_examples()
