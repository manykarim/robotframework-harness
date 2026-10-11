#!/usr/bin/env python3
"""Journey-evidence grader: did the graded robot run really drive the user journey?

Runs under the grading venv (needs robot.api). Parses the output.xml of the `robot_pass` grading run
(robot executed with --loglevel TRACE so every keyword logs its RESOLVED arguments and return value)
and checks, per scenario spec:

  confirm  every regex in spec["confirm"] was READ FROM THE PAGE by a passing Browser keyword
  values   every regex in spec["values"]  was READ FROM THE PAGE by a passing Browser keyword
  inputs   >= spec["min_inputs"] distinct selectors driven by passing Browser input keywords
           (Fill/Type Text, Fill/Type Secret, Select Options By, (Un)Check Checkbox, Click,
           Click With Options, Press Keys, Clear Text, Upload File By Selector, Keyboard Input) AND
           every data token in spec["data"] appears in the values those keywords entered
  nav      every New Page / Go To / New Persistent Context / Open Browser URL matches
           spec["allowed_urls"]; no JavaScript navigation (location=..., window.open, pushState);
           no BuiltIn assertion compared a confirm/value target that was never read from the page
           (hard-coded assertion target)

"Read from the page" = evidence of a PASSING Browser read keyword:
  * its logged page content (INFO messages such as "Text: '...'" and the TRACE "Return: ..."), for
    Get Text/Property/Attribute/..., Wait For Condition, Evaluate JavaScript (the latter only when
    the JS source does not itself contain the target, i.e. `return "Sending e-mail success!"` is
    not page evidence);
  * or its own resolved arguments, when passing proves the page state: Get Text/Property/... with a
    positive assertion operator (==, contains, matches, ...) or a selector that must resolve, and
    Wait For Elements State with a positive state (visible/attached/enabled/...).
  Get Page Source is never evidence (scripts/templates contain texts that are not rendered).

Usage: journey_evidence.py <output.xml> <spec.json>   -> prints one JSON object
"""
from __future__ import annotations

import ast
import json
import re
import sys

from robot.api import ExecutionResult

INPUT_KW = {"fill text", "type text", "fill secret", "type secret", "select options by", "deselect options",
            "check checkbox", "uncheck checkbox", "click", "click with options", "press keys", "clear text",
            "upload file by selector", "keyboard input", "tap", "set checkbox"}
TYPED_KW = {"fill text", "type text", "fill secret", "type secret", "select options by", "press keys",
            "keyboard input"}
SECRET_KW = {"fill secret", "type secret"}
SECRET_MARK = "<<fillsecret>>"
# read keywords whose passing proves the page state described by their own arguments
READ_ARGS_KW = {"get text", "get property", "get attribute", "get classes", "get style", "get select options",
                "get selected options", "get checkbox state", "get title", "get url", "get element"}
READ_ASSERT_ONLY_KW = {"get element states", "get element count", "get elements",   # args only with a positive
                       "wait for condition"}                                        # assertion operator
READ_RETURN_KW = READ_ARGS_KW | READ_ASSERT_ONLY_KW | {"wait for elements state", "wait for condition",
                                                      "wait for function", "evaluate javascript"}
NO_EVIDENCE_KW = {"get page source"}
NAV_KW = {"new page", "go to", "new persistent context", "open browser"}
ASSERT_KW = {"should be equal", "should be equal as strings", "should be equal as numbers",
             "should be equal as integers", "should contain", "should match", "should match regexp",
             "should start with", "should end with", "should be true", "should contain any"}
NEG_OPS = re.compile(r"(?i)^(!=|not contains|inequal|should not be|not equal|does not contain)$|AssertionOperator\.("
                     r"inequal|not_contains|NotEqual)")
POS_OPS = re.compile(r"(?i)^(==|\*=|\^=|\$=|\$|equal|equals|should be|contains|starts|should start with|ends|"
                     r"should end with|matches|validate|then|evaluate|>|>=|<|<=|greater than|less than)$|"
                     r"AssertionOperator\.(equal|contains|starts|ends|matches|validate|then|greater|less)")
NEG_STATES = re.compile(r"(?i)\b(hidden|detached|disabled|readonly|unchecked|defocused|deselected)\b")
JS_NAV = re.compile(r"(?i)(location\s*(\.href)?\s*=(?!=)|location\.(assign|replace)\s*\(|window\.open\s*\(|"
                    r"history\.(push|replace)State)")


def _kwname(kw) -> str:
    return (kw.name or "").strip().lower()


def _owner(kw) -> str:
    return (getattr(kw, "owner", None) or getattr(kw, "libname", None) or "").strip()


def _split_items(s: str) -> list[str]:
    """Split the body of an RF `Arguments: [ a | b | c ]` trace message on ' | ' outside quotes."""
    items, cur, q, i = [], [], None, 0
    while i < len(s):
        c = s[i]
        if q:
            cur.append(c)
            if c == "\\" and i + 1 < len(s):
                cur.append(s[i + 1])
                i += 2
                continue
            if c == q:
                q = None
        elif c in "'\"":
            q = c
            cur.append(c)
        elif s.startswith(" | ", i):
            items.append("".join(cur))
            cur = []
            i += 3
            continue
        else:
            cur.append(c)
        i += 1
    if cur or items:
        items.append("".join(cur))
    return [x.strip() for x in items]


def _lit(x: str) -> str:
    x = x.strip()
    if x[:1] in "'\"" or x[:2] in ("b'", 'b"'):
        try:
            v = ast.literal_eval(x)
            return v.decode(errors="replace") if isinstance(v, bytes) else str(v)
        except Exception:
            return x
    return x


def resolved_args(kw) -> tuple[list[str], dict[str, str], bool]:
    """(positional, named, from_trace). Falls back to the unresolved output.xml args without TRACE."""
    for m in kw.body:
        if getattr(m, "type", "") == "MESSAGE" and m.level == "TRACE" and m.message.startswith("Arguments: ["):
            body = m.message[len("Arguments: ["):].rstrip()
            body = body[:-1] if body.endswith("]") else body
            body = body.strip()
            pos, named = [], {}
            if body:
                for it in _split_items(body):
                    mm = re.match(r"^([A-Za-z_]\w*)=(.*)$", it, re.S)
                    if mm and it[:1] not in "'\"":
                        named[mm.group(1)] = _lit(mm.group(2))
                    else:
                        pos.append(_lit(it))
            return pos, named, True
    pos, named = [], {}
    for a in kw.args:
        a = str(a)
        mm = re.match(r"^([A-Za-z_]\w*)=(.*)$", a, re.S)
        if mm:
            named[mm.group(1)] = mm.group(2)
        else:
            pos.append(a)
    return pos, named, False


def _decode(s: str) -> str:
    s = (s.replace("\\n", "\n").replace("\\t", " ").replace("\\xa0", " ").replace("\\u202f", " ")
         .replace("\\'", "'").replace('\\"', '"').replace("\\\\", "\\"))
    return s.replace("\xa0", " ").replace(" ", " ")


def page_messages(kw) -> list[str]:
    out = []
    for m in kw.body:
        if getattr(m, "type", "") != "MESSAGE" or m.message.startswith("Arguments: ["):
            continue
        if m.level in ("INFO", "TRACE", "DEBUG") and not m.message.startswith(("Assertion polling", "Click options",
                                                                               "Clicked element", "Fill text")):
            out.append(_decode(m.message))
    return out


def _norm(s: str) -> str:
    return re.sub(r"[\s_\-]+", "", s.lower())


def walk(item):
    """All keyword result objects (incl. setup/teardown, inside FOR/IF/TRY/WHILE/GROUP), in execution order."""
    for b in getattr(item, "body", []) or []:
        t = getattr(b, "type", "")
        if t == "MESSAGE":
            continue
        if t in ("KEYWORD", "SETUP", "TEARDOWN"):
            yield b
        yield from walk(b)
    for attr in ("setup", "teardown"):
        k = getattr(item, attr, None)
        if k is not None and getattr(k, "name", None) and getattr(k, "type", "") in ("SETUP", "TEARDOWN") \
                and item.__class__.__name__ in ("TestCase", "TestSuite"):
            yield k
            yield from walk(k)


def all_keywords(suite):
    for k in walk(suite):          # suite setup/teardown
        yield k
    for s in suite.suites:
        yield from all_keywords(s)
    for t in suite.tests:
        yield from walk(t)


def evaluate(xml: str, spec: dict) -> dict:
    res = ExecutionResult(xml)
    kws = list(all_keywords(res.suite))
    browser = [k for k in kws if _owner(k) == "Browser"]
    passing = [k for k in browser if k.status == "PASS"]
    traced = any(resolved_args(k)[2] for k in browser[:5]) if browser else False

    # ---- evidence read from the page
    evidence: list[tuple[str, str]] = []           # (keyword, text)
    for k in passing:
        n = _kwname(k)
        if n in NO_EVIDENCE_KW or n not in READ_RETURN_KW:
            continue
        pos, named, _ = resolved_args(k)
        argtxt = _decode(" ".join(pos + [f"{a}={b}" for a, b in named.items()]))
        if n == "evaluate javascript":
            for msg in page_messages(k):
                evidence.append((n + ":return", msg + "\x00JS:" + argtxt))   # JS source kept to exclude literals
            continue
        if n != "wait for elements state":        # its log line echoes the selector, not page content
            evidence += [(n + ":return", msg) for msg in page_messages(k)]
        ops = [p for p in pos[1:]] + list(named.values())
        neg = any(NEG_OPS.search(str(o).strip()) for o in ops)
        if n == "wait for elements state":
            if not neg and not NEG_STATES.search(" ".join(str(p) for p in pos[1:2] + [named.get("state", "")])):
                evidence.append((n + ":args", argtxt))
        elif n in READ_ARGS_KW:
            if not neg:
                evidence.append((n + ":args", argtxt))
        elif n in READ_ASSERT_ONLY_KW:
            pos_op = any(POS_OPS.search(str(o).strip()) for o in ops)
            if pos_op and not neg and not re.search(r"(?i)(^|\s)0(\s|$)|detached|hidden", " ".join(str(o) for o in ops)):
                evidence.append((n + ":args", argtxt))

    def read_hits(rx: str) -> list[str]:
        r = re.compile(rx, re.S)
        hits = []
        for src, txt in evidence:
            if src == "evaluate javascript:return":
                ret, _, js = txt.partition("\x00JS:")
                if r.search(ret) and not r.search(js):
                    hits.append(src)
            elif r.search(txt):
                hits.append(src)
        return hits

    def part_read(key: str) -> dict:
        pats = spec.get(key) or []
        found = {p: read_hits(p) for p in pats}
        missing = [p for p, h in found.items() if not h]
        return {"ok": not missing, "missing": missing,
                "hits": {p: sorted(set(h))[:4] for p, h in found.items() if h}}

    confirm = part_read("confirm")
    values = part_read("values")

    # ---- form inputs driven by the run
    selectors, typed_vals, all_vals = set(), [], []
    for k in passing:
        n = _kwname(k)
        pos, named, _ = resolved_args(k)
        if n in INPUT_KW:
            if n == "keyboard input":
                sel = "keyboard:" + (pos[1] if len(pos) > 1 else "")
            else:
                sel = pos[0] if pos else named.get("selector", "")
            selectors.add(re.sub(r"\s+", " ", str(sel)).strip())
            vals = [str(v) for v in pos[1:]] + [str(v) for v in named.values()]
            all_vals += [str(sel)] + vals
            if n in TYPED_KW:
                typed_vals += vals
            if n in SECRET_KW:
                typed_vals.append(SECRET_MARK)
                all_vals.append(SECRET_MARK)
        elif n == "evaluate javascript":              # programmatic value setting counts as entered data
            vals = [str(v) for v in pos] + [str(v) for v in named.values()]
            typed_vals += vals
            all_vals += vals
    typed_n = [_norm(_decode(v)) for v in typed_vals]
    all_n = [_norm(_decode(v)) for v in all_vals]
    missing_data = []
    for tok in spec.get("data") or []:
        if isinstance(tok, dict):
            alts, scope, exact = tok.get("any", []), tok.get("scope", "typed"), tok.get("exact", False)
        else:
            alts, scope, exact = list(tok), "typed", False
        pool = all_n if scope == "all" else typed_n
        ok = any((_norm(a) == v) if exact else (_norm(a) in v) for a in alts for v in pool)
        if not ok:
            missing_data.append(alts[0])
    min_inputs = int(spec.get("min_inputs", 0))
    inputs = {"ok": len(selectors) >= min_inputs and not missing_data, "distinct": len(selectors),
              "min": min_inputs, "missing_data": missing_data}

    # ---- anti-shortcut: navigation + hard-coded assertion targets
    allowed = [re.compile(a, re.I) for a in spec.get("allowed_urls") or []]
    bad_urls, js_nav, nav_urls = [], [], []
    for k in browser:                      # failing navigations count too (an attempted deep link)
        n = _kwname(k)
        pos, named, _ = resolved_args(k)
        if n in NAV_KW:
            url = named.get("url") if n in ("new persistent context", "open browser") and "url" in named else \
                (pos[0] if pos and n != "new persistent context" else named.get("url", ""))
            url = str(url or "").strip()
            if not url or url.lower() in ("about:blank", "none"):
                continue
            nav_urls.append(url)
            if allowed and not any(a.search(url) for a in allowed):
                bad_urls.append(url)
        elif n == "evaluate javascript":
            src = " ".join(str(v) for v in pos + list(named.values()))
            if JS_NAV.search(src):
                js_nav.append(src[:120])
    unread = set(confirm["missing"]) | set(values["missing"])
    hardcoded = []
    for k in kws:
        if _owner(k) != "BuiltIn" or k.status != "PASS" or _kwname(k) not in ASSERT_KW:
            continue
        pos, named, _ = resolved_args(k)
        txt = _decode(" ".join(str(v) for v in pos))
        for p in unread:
            if re.search(p, txt, re.S):
                hardcoded.append(f"{k.name}: {p}")
    nav = {"ok": not bad_urls and not js_nav and not hardcoded, "bad_urls": bad_urls[:5], "js_nav": js_nav[:3],
           "hardcoded_asserts": sorted(set(hardcoded))[:5], "urls": sorted(set(nav_urls))[:6]}
    return {"confirm": confirm, "values": values, "inputs": inputs, "nav": nav, "trace": traced,
            "browser_keywords": len(browser), "passing_browser_keywords": len(passing)}


def main() -> None:
    xml, spec_path = sys.argv[1], sys.argv[2]
    with open(spec_path, encoding="utf-8") as f:
        spec = json.load(f)
    try:
        out = evaluate(xml, spec)
    except Exception as exc:          # never crash the grader
        out = {"error": f"{type(exc).__name__}: {exc}"}
    print(json.dumps(out))


if __name__ == "__main__":
    main()
