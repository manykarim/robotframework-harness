"""The vendored rf-mcp hint engine (rf_harness.runtime.hints, rf-mcp 0.36.0 / c1a18eb) gives exactly rf-mcp's output,
and the live session uses it only with RFH_RFMCP_HINTS=1 (the measured prototype ran without it).

Expected values were generated once with rf-mcp's own venv
(`cd rf-mcp && uv run --no-sync python cases.py robotmcp.utils.hints`): the hint titles plus a sha256 over the whole
generate_hints() output (titles, messages, examples), so any drift from rf-mcp's engine fails here.
"""

from __future__ import annotations

import hashlib
import json

import pytest

from rf_harness.runtime import hints, rthooks

BROWSER = ["Browser", "BuiltIn"]
CASES = {
    "strict_mode": ("Click", ["button"], "Error: strict mode violation: locator('button') resolved to 3 elements:\n"
                    "    1) <button>A</button>\n    2) <button>B</button>", BROWSER),
    "arg_count": ("Fill Text", ["id=username"], "Keyword 'Browser.Fill Text' expected 2 to 4 arguments, got 1.", BROWSER),
    "intercepted": ("Click", ["id=gender-female"], "TimeoutError: locator.click: Timeout 2500ms exceeded.\nCall log:\n"
                    "  - waiting for locator('id=gender-female')\n"
                    "    - locator resolved to <input id=\"gender-female\" type=\"radio\"/>\n"
                    "  - attempting click action\n"
                    "    - <span class=\"ideal-radio\"></span> intercepts pointer events", BROWSER),
    "timeout_missing": ("Click", ["id=nope"], "TimeoutError: locator.click: Timeout 2500ms exceeded.\nCall log:\n"
                        "  - waiting for locator('id=nope')", BROWSER),
    "selenium_not_found": ("Page Should Contain Element", ["id=x"],
                           "Page should have contained element 'id=x' but did not.", ["SeleniumLibrary", "BuiltIn"]),
    "invalid_selector": ("Click", ["css=div[[x"],
                         "Error: locator.click: Unexpected token '[' while parsing css selector 'div[[x'", BROWSER),
}
# generated with rf-mcp 0.36.0 (robotmcp.utils.hints), see the module docstring
RFMCP = {
    "strict_mode": (["Selector matches multiple elements"],
                    "506f96d91176a48ec059dd4bcb3a789eb11818e97753c45c40f2eb458d4117d5"),
    "arg_count": ([], "4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945"),
    "intercepted": (["Click intercepted by overlapping element", "Element not found — inspect the page"],
                    "8ba63a3d43daeb2fcc57b7f5244bc3d6f721cbf32745d9ba7f3b29f7552337d8"),
    "timeout_missing": (["Element not found — inspect the page"],
                        "f86f6d23e0887d786a181b09bd4aed1cec3820a8cb8d8c89a7c9d327035d153b"),
    "selenium_not_found": (["Element not found — inspect the page"],
                           "93184e7920997cc3f64db1147307f8353d53135f0176f58f652ca803b0f9b741"),
    "invalid_selector": (["Invalid selector syntax"], "5fdb6f656d507a7531f374310763bd14ec4bc512571583d82bc62ad8fdd0fe7c"),
}


def _generate(name: str) -> list:
    kw, args, err, order = CASES[name]
    return hints.generate_hints(hints.HintContext(session_id="local", keyword=kw, arguments=list(args),
                                                  error_text=err, session_search_order=order))


@pytest.mark.parametrize("name", sorted(CASES))
def test_same_output_as_rf_mcp(name):
    out = _generate(name)
    titles, digest = RFMCP[name]
    assert [h.get("title") for h in out] == titles
    assert hashlib.sha256(json.dumps(out, sort_keys=True, default=str).encode()).hexdigest() == digest


def test_no_rf_mcp_import():
    from pathlib import Path

    for mod in (hints, rthooks):
        src = Path(mod.__file__).read_text(encoding="utf-8")
        assert "from robotmcp" not in src and "import robotmcp" not in src, mod.__name__


def _failed_click() -> tuple:
    kw, args, err, _ = CASES["strict_mode"]
    step = rthooks.StepCtx(kw=None, name=kw, args=list(args), assign=[], owner="Browser")
    return step, {"status": "FAIL", "msg": err}


def test_live_session_hints_are_off_by_default(monkeypatch):
    monkeypatch.delenv("RFH_RFMCP_HINTS", raising=False)
    h = rthooks.Hints()
    step, rec = _failed_click()
    h.post(step, rec)
    assert h._gen is None and "hints" not in rec


def test_live_session_hints_with_the_switch(monkeypatch):
    monkeypatch.setenv("RFH_RFMCP_HINTS", "1")
    h = rthooks.Hints()
    step, rec = _failed_click()
    h.post(step, rec)
    assert [x["title"] for x in rec["hints"]] == ["Selector matches multiple elements"]
    assert rec["hints"][0]["try"]                         # examples re-rendered as RF lines


def test_local_hints_apply_without_the_engine(monkeypatch):
    monkeypatch.delenv("RFH_RFMCP_HINTS", raising=False)
    kw, args, err, _ = CASES["intercepted"]
    rec = {"status": "FAIL", "msg": err}
    rthooks.Hints().post(rthooks.StepCtx(kw=None, name=kw, args=list(args), assign=[], owner="Browser"), rec)
    assert rec["hints"][0]["title"].startswith("another element covers the target")
