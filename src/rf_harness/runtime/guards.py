"""Cheap guiding guards (STDLIB ONLY, imported by hook.py):

  bash_guard      deny `pip install` / `uv pip install` / `playwright install` / `rfbrowser init` into the shared venv,
                  `robot -P` / `--pythonpath` / `PYTHONPATH=... robot` portability workarounds, `cat` of huge files
  read_guard      Read/view of huge output.xml / log.html / page source -> Grep / `robotcode results` / controls.txt
  suite_guard     edit of a suite that existed at session start: a test removed/renamed, fewer assertions, new
                  failure-hiding constructs (Run Keyword And Ignore Error, Skip, Pass Execution, robot:skip, ...) -> deny
  loop tracking   the same test step failing >= 3x -> a focused hint (controls.txt, frame >>>, waits, keyword doc)
  project_context short UserPromptSubmit note: installed libraries + versions, robot.toml, resources, existing tests
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

TEST_HDR = re.compile(r"^\*+\s*(test\s*cases?|tasks?)\s*\**\s*$", re.I)
ANY_HDR = re.compile(r"^\*+\s*\w")

# ------------------------------------------------------------------------------------------------ bash
_INSTALL = re.compile(r"(?:^|[\s;&|(])(?:(?:\S*/)?pip3?|(?:\S*/)?python3?(?:\.\d+)?\s+-m\s+pip|uv\s+pip|pipx)\s+install\b"
                      r"|(?:^|[\s;&|(])uv\s+(?:add|sync)\b"
                      r"|(?:^|[\s;&|(])(?:npx\s+)?playwright\s+install\b"
                      r"|(?:^|[\s;&|(])(?:\S*/)?rfbrowser\s+(?:init|install|clean-node)\b"
                      r"|(?:^|[\s;&|(])npm\s+(?:i|install|ci)\b")
_ROBOT_CMD = re.compile(r"(?:^|[\s;&|(])(?:(?:\S*/)?robot|(?:\S*/)?robotcode(?:\s+--?\S+(?:\s+[^-\s]\S*)?)*\s+(?:robot|run)"
                        r"|python3?(?:\.\d+)?\s+-m\s+robot)(?=\s|$)")
_PP_FLAG = re.compile(r"(?:^|\s)(?:-P|--pythonpath)(?:\s|=)")
_PP_ENV = re.compile(r"(?:^|[\s;&|(])(?:export\s+)?PYTHONPATH=")
_CAT = re.compile(r"^\s*(?:cat|less|more)\s+(\S+)\s*$")

BIG_EXT = (".xml", ".html", ".htm", ".log", ".json", ".txt", ".yaml")
BIG_NAMES = ("output.xml", "log.html", "report.html", "source.html", "output.json")


def _seg_has_robot(seg: str) -> bool:
    return bool(_ROBOT_CMD.search(" " + seg))


def bash_guard(cmd: str, cwd: Path) -> Optional[Tuple[str, str]]:
    """-> (kind, reason) to deny, or None."""
    if not cmd:
        return None
    if _INSTALL.search(cmd):
        return ("install", "Installing packages/browsers is not allowed here: Robot Framework, Browser (with its "
                "Chromium), SeleniumLibrary, RequestsLibrary and robotcode are already installed in the shared "
                "environment, and changing it breaks other runs. Use what is installed (installed libraries and "
                "versions: .rf/docs/README.txt; keyword names: grep -i '<words>' .rf/docs/*.md). Nothing was run.")
    for seg in re.split(r"&&|\|\||;|\n|\|", cmd):
        if not _seg_has_robot(seg):
            continue
        if _PP_FLAG.search(seg) or _PP_ENV.search(seg) or (_PP_ENV.search(cmd) and "export" in cmd):
            return ("pythonpath", "`robot -P/--pythonpath` and PYTHONPATH are portability workarounds: the final suite "
                    "must pass with a plain `robot <file>` from the project root. Import project code by path "
                    "instead: `Library    ${CURDIR}/../lib/MyLib.py`, `Resource    ${CURDIR}/common.resource`, "
                    "`Variables    ${CURDIR}/vars.py`. Nothing was run.")
    m = _CAT.match(cmd)
    if m:
        p = Path(os.path.expanduser(m.group(1)))
        p = p if p.is_absolute() else cwd / p
        r = read_guard(str(p), None, None)
        if r:
            return r
    return None


def read_guard(path: str, limit: Any, offset: Any) -> Optional[Tuple[str, str]]:
    if not path or limit or offset:
        return None
    p = Path(path)
    try:
        size = p.stat().st_size
    except OSError:
        return None
    name = p.name.lower()
    big = (name in BIG_NAMES and size > 60_000) or (name.endswith(BIG_EXT) and size > 250_000)
    if not big:
        return None
    kb = size // 1024
    if name.startswith("output") and name.endswith((".xml", ".json")):
        tip = (f"`robotcode results summary -o {path}` / `robotcode results show --failed -o {path}` (failures with "
               "messages) or Grep for the test/keyword name")
    elif name in ("log.html", "report.html"):
        tip = "the matching output.xml via `robotcode results show --failed -o <dir>/output.xml`, or Grep"
    elif "state" in path or name == "source.html":
        tip = ("`.rf/state/latest/controls.txt` (every control with a suggested selector) or Grep the source for an "
               "id/text")
    else:
        tip = "Grep for what you need, or Read it with offset/limit"
    return ("bigread", f"{p.name} is {kb} KB -- reading it whole floods your context. Use {tip}. Nothing was read.")


# ------------------------------------------------------------------------------------------------ suite guard
_ASSERT = re.compile(r"(?:^|\s{2,}|\t)(?:[\w ]*\bShould\b[\w ]*|Wait For Condition|Wait Until [\w ]+|Status Should Be|"
                     r"Get [\w ]+?\s{2,}\S.*?\s{2,}(?:==|!=|<=|>=|<|>|\*=|\^=|\$=|contains|not contains|equal|"
                     r"should be|starts|ends|matches|validate|then|inequal|less than|greater than)(?=\s{2,}|\s*$))",
                     re.I)
_HIDE = re.compile(r"(?:^|\s{2,}|\t)(Run Keyword And Ignore Error|Run Keyword And Return Status|Run Keyword And "
                   r"Warn On Failure|Skip(?: If)?|Pass Execution(?: If)?|Set Tags\s{2,}robot:skip|robot:skip|"
                   r"robot:exclude|No Operation|Run Keyword And Expect Error)(?=\s{2,}|\s*$|\t)", re.I)
_WEAK_OPS = {"*=", "contains", "^=", "starts", "$=", "ends", "!=", "not contains", "matches", "validate", "then"}
_STRONG_OPS = {"==", "equal", "equals", "should be"}


def suite_info(text: str) -> Dict[str, Any]:
    tests: List[str] = []
    asserts = hides = 0
    section = ""
    for line in text.splitlines():
        if ANY_HDR.match(line):
            section = "tests" if TEST_HDR.match(line) else line.lower()
            continue
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        body = line.split("    #")[0]
        if section == "tests" and not line[0].isspace():
            tests.append(line.strip().split("  ")[0])
            continue
        if section in ("tests",) or "keyword" in section or "setting" in section:
            if _ASSERT.search(body):
                asserts += 1
            for _ in _HIDE.finditer(body):
                hides += 1
    return {"tests": tests, "asserts": asserts, "hides": hides}


def suite_guard(orig: Dict[str, Any], new_text: str) -> List[str]:
    """problems of the proposed content compared with the suite as it was at session start."""
    if not orig or not orig.get("tests"):
        return []
    n = suite_info(new_text)
    probs = []
    gone = [t for t in orig["tests"] if t not in n["tests"]]
    if gone:
        probs.append(f"test(s) removed or renamed: {', '.join(gone[:4])} -- keep every test with its exact name")
    if n["asserts"] < orig["asserts"]:
        probs.append(f"fewer assertions than the original suite ({n['asserts']} < {orig['asserts']}) -- keep every "
                     "check; fix the selector/wait instead (a stronger wait or a corrected locator is fine)")
    if n["hides"] > orig["hides"]:
        probs.append("new failure-hiding construct (Run Keyword And Ignore Error / Return Status, Skip, Pass "
                     "Execution, TRY/EXCEPT, robot:skip) -- the test must really pass, not be silenced")
    return probs


def suite_guard_split(orig: Dict[str, Any], new_text: str) -> Tuple[List[str], List[str]]:
    """v3: (certain, uncertain) problems. Certain = a test removed/renamed or a NEW failure-hiding construct (the
    task's checks fail for sure) -> refused; uncertain = fewer assertions by the regex count -> one-line warning."""
    probs = suite_guard(orig, new_text)
    certain = [p for p in probs if p.startswith(("test(s) removed", "new failure-hiding"))]
    return certain, [p for p in probs if p not in certain]


def _cells(line: str) -> List[str]:
    return [c for c in re.split(r"\s{2,}|\t", line.split("    #")[0].strip()) if c]


def edit_findings(cur: Optional[str], new: str, existing: bool) -> Tuple[Optional[str], List[str]]:
    """wait-strategy + tampering soft rules on an RF edit -> (deny reason for a NEW Sleep (deny once), warnings)."""
    import difflib

    old = cur or ""
    warns: List[str] = []
    deny = None
    sleep_re = re.compile(r"(?:^|\s{2,}|\t)Sleep(?:\s{2,}|\t)", re.I)
    if len(sleep_re.findall(new)) > len(sleep_re.findall(old)) and re.search(r"Library\s{2,}(Browser|SeleniumLibrary)", new):
        deny = ("a new `Sleep` makes the test slow and still flaky. Wait for the condition instead: "
                "`Wait For Elements State    <sel>    visible    timeout=10s`, `Wait For Condition    Text    <sel>    "
                "contains    <text>    timeout=10s` (SeleniumLibrary: `Wait Until Element Is Visible    <loc>    10s`). "
                "Nothing was written.")
    tmo_re = re.compile(r"Set (?:Browser|Selenium) Timeout|Set Selenium Implicit Wait|Set Retry Assertions For", re.I)
    if len(tmo_re.findall(new)) > len(tmo_re.findall(old)):
        warns.append("timeout setting added: first check the element exists (.rf/state/latest/controls.txt, "
                     "`Get Element Count    <sel>` -> 0 means wrong locator/iframe, not timing); prefer one explicit "
                     "wait before the step over a global timeout")
    if new.count("force=True") > old.count("force=True"):
        warns.append("force=True clicks whatever is on top (an overlay) and skips actionability checks: close the "
                     "overlay / click the visible label instead")
    if len(re.findall(r"Execute JavaScript|Evaluate JavaScript", new)) > len(re.findall(r"Execute JavaScript|Evaluate "
                                                                                         r"JavaScript", old)):
        warns.append("JavaScript actions bypass what a user can do: use Click/Fill Text on a real selector")
    if not existing or cur is None:
        return deny, warns
    if len(re.findall(r"^\s+EXCEPT\b", new, re.M)) > len(re.findall(r"^\s+EXCEPT\b", old, re.M)):
        warns.append("new TRY/EXCEPT in an existing suite: make sure it does not swallow a failing check")
    a, b = old.splitlines(), new.splitlines()
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
        if tag != "replace":
            continue
        for x, y in zip(a[i1:i2], b[j1:j2], strict=False):
            cx, cy = _cells(x), _cells(y)
            if not cx or not cy or not _ASSERT.search(x):
                continue
            if cx[0].lower() == "should be equal" and cy[0].lower().startswith("should contain"):
                warns.append(f"assertion weakened: `{cx[0]}` -> `{cy[0]}` -- keep the exact check unless the app "
                             "really changed")
            elif len(cx) >= 4 and len(cy) >= 4 and cx[0] == cy[0] and cx[1] == cy[1]:
                if cx[2].lower() in _STRONG_OPS and cy[2].lower() in _WEAK_OPS:
                    warns.append(f"assertion operator weakened: `{cx[2]}` -> `{cy[2]}` in `{cx[0]}    {cx[1]}`")
                elif cx[2] == cy[2] and cx[3:] != cy[3:]:
                    warns.append(f"expected value changed: `{' '.join(cx[3:])[:50]}` -> `{' '.join(cy[3:])[:50]}`"
                                 " -- only if the requirement/app really changed (say so)")
            elif cx[0] == cy[0] and cx[0].lower().startswith("should") and cx[1:] != cy[1:] and len(cx) == len(cy) \
                    and cx[1] == cy[1]:
                warns.append(f"expected value changed in `{cx[0]}`: `{' '.join(cx[2:])[:50]}` -> "
                             f"`{' '.join(cy[2:])[:50]}` -- only if the requirement/app really changed")
    return deny, list(dict.fromkeys(warns))[:3]


def missing_keywords_header(text: str, names: List[str]) -> Optional[str]:
    """`No keyword with name 'X'` where X is defined in the file without a *** Keywords *** header."""
    if re.search(r"^\*+\s*Keywords?\s*\**\s*$", text, re.I | re.M):
        return None
    for n in names:
        m = re.search(r"^" + re.escape(n) + r"\s*$", text, re.M | re.I)
        if m:
            ln = text[:m.start()].count("\n") + 1
            return (f"root cause: the file has no `*** Keywords ***` section header, so '{n}' (line {ln}) is read as a "
                    "TEST CASE, not a keyword -- add `*** Keywords ***` on the line above it")
    return None


# ------------------------------------------------------------------------------------------------ loops
def loop_key(file: str, test: Optional[str], kw: str) -> str:
    return f"{file}|{test or ''}|{re.sub(r'[ _]', '', (kw or '').lower())}"


def loop_hint(n: int, where: str, kw: str, owner: Optional[str], sel: Optional[str]) -> str:
    kwf = f".rf/docs/kw/{(owner or 'Browser')}.{kw.replace(' ', '_')}.md" if kw else ".rf/docs/kw/"
    s = (f"LOOP: {where} ({kw}) has now failed {n} times. Stop varying the line blindly:\n"
         "  1. read .rf/state/latest/controls.txt (every control with a suggested `=>` selector; iframe content is "
         "listed with its `frame >>> ` prefix) and .rf/state/latest/aria.yaml;\n"
         "  2. inside an iframe? -> `id=<frame> >>> <selector>`; appears late? -> add `Wait For Elements State    "
         f"{sel or '<sel>'}    visible    timeout=10s` before it; covered/hidden? -> close the overlay / click the label;\n"
         f"  3. check the keyword's arguments in {kwf}.")
    return s


# ------------------------------------------------------------------------------------------------ prompt context
_DISTS = [("robotframework", "Robot Framework"), ("robotframework_browser", "Browser"),
          ("robotframework_seleniumlibrary", "SeleniumLibrary"), ("robotframework_requests", "RequestsLibrary"),
          ("robotcode", "robotcode"), ("robotframework_robocop", "robocop")]


def installed_versions(py: str = sys.executable) -> List[str]:
    out = []
    venv = Path(py).parent.parent
    for sp in venv.glob("lib/python3*/site-packages"):
        names = {}
        for d in sp.glob("*.dist-info"):
            n, _, v = d.name[:-len(".dist-info")].rpartition("-")
            names[n.lower().replace("-", "_")] = v
        for key, label in _DISTS:
            if key in names:
                out.append(f"{label} {names[key]}")
        break
    return out


def project_context(root: Path, rf_files: List[Path]) -> str:
    parts = []
    vers = installed_versions()
    if vers:
        parts.append("installed: " + ", ".join(vers))
    toml = root / "robot.toml"
    if toml.is_file():
        try:
            t = " ".join(l.strip() for l in toml.read_text().splitlines() if l.strip() and not l.startswith("#"))
            parts.append("robot.toml: " + t[:160])
        except OSError:
            pass
    res = [os.path.relpath(f, root) for f in rf_files if f.suffix == ".resource"][:8]
    if res:
        parts.append("resources: " + ", ".join(res))
    tests = []
    for f in rf_files:
        if f.suffix != ".robot":
            continue
        try:
            info = suite_info(f.read_text(errors="replace"))
        except OSError:
            continue
        if info["tests"]:
            tests.append(f"{os.path.relpath(f, root)} ({len(info['tests'])}: {', '.join(info['tests'][:3])}"
                         + (", ..." if len(info["tests"]) > 3 else "") + ")")
    if tests:
        parts.append("suites: " + "; ".join(tests[:6]))
    libs = [p.name for p in root.glob("lib*/*.py")][:5] + [p.name for p in root.glob("resources/*.py")][:3]
    if libs:
        parts.append("python libs (import by ${CURDIR} path): " + ", ".join(libs))
    if not parts:
        return ""
    return "Robot Framework project context (hook): " + " | ".join(parts)
