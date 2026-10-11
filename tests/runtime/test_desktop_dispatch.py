"""Live-session dispatch of PlatynUI steps through rf_harness.runtime.desktop (rthooks.DesktopGuard): refused steps
are not run and their rf-mcp guidance reaches the feedback; other libraries' keywords never enter the chain."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from rf_harness.runtime import desktop, leanfmt, richfmt, rthooks


def _step(name: str, owner: str | None, args=("app:Application[@Name='Editor']//control:Button[@Name='OK']",),
          kw=None) -> rthooks.StepCtx:
    return rthooks.StepCtx(kw=kw, name=name, args=list(args), assign=[], owner=owner)


@pytest.fixture(autouse=True)
def _desktop_off(monkeypatch):
    monkeypatch.delenv("RFH_DESKTOP", raising=False)


def test_platynui_step_is_refused_by_default():
    ref = rthooks.DesktopGuard().pre(_step("Pointer Click", "PlatynUI.BareMetal"))
    assert ref["cls"] == "DESKTOP" and ref["rule"] == desktop.DESKTOP_DISABLED
    assert "RFH_DESKTOP=1" in ref["fix"] and "no input was sent" in ref["fix"]


def test_unowned_platynui_keyword_is_still_guarded():
    ref = rthooks.DesktopGuard().pre(_step("PlatynUI.BareMetal.Keyboard Type", None, args=("hello",)))
    assert ref and ref["rule"] == desktop.DESKTOP_DISABLED


@pytest.mark.parametrize(("name", "owner"), [("Get Attribute", "Browser"), ("Click", "Browser"),
                                             ("Log", "BuiltIn"), ("FOR", None), ("Open Shop", "shop"),
                                             ("Start Process", "Process")])
def test_other_steps_pass_untouched(name, owner):
    assert rthooks.DesktopGuard().pre(_step(name, owner, args=("x",))) is None


def test_allowed_step_that_needs_focus_is_refused_until_focus_is_wired(monkeypatch):
    plan = desktop.FocusPlan(required=True, bypassed=False, descriptor="app:Application[@Name='Editor']",
                             scope="app:Application[@Name='Editor']")
    monkeypatch.setattr(desktop, "evaluate_step", lambda *a, **k: desktop.Decision(allowed=True, focus=plan,
                                                                                   arguments=tuple(a[1])))
    ref = rthooks.DesktopGuard().pre(_step("Pointer Click", "PlatynUI.BareMetal"))
    assert ref["rule"] == "focus_not_wired" and "RFH_PLATYNUI_NO_FOCUS=1" in ref["fix"]


def test_allowed_step_gets_the_guard_arguments_and_warnings(monkeypatch):
    warning = {"type": "wayland_x11_input_blocked_risk", "message": "Wayland may block synthetic input"}
    monkeypatch.setattr(desktop, "evaluate_step", lambda *a, **k: desktop.Decision(
        allowed=True, focus=None, arguments=("gnome-text-editor", "env:GDK_BACKEND=x11"), warnings=(warning,)))
    kw = SimpleNamespace(args=("gnome-text-editor",))
    guard = rthooks.DesktopGuard()
    step = _step("Start Application", "PlatynUI.BareMetal", args=("gnome-text-editor",), kw=kw)
    assert guard.pre(step) is None
    assert kw.args == ("gnome-text-editor", "env:GDK_BACKEND=x11")
    rec: dict = {"status": "PASS"}
    guard.post(step, rec)
    assert rec["desktop_warnings"] == [warning] and "wayland_x11_input_blocked_risk" in guard.warned


def _refused_run() -> dict:
    ref = rthooks.DesktopGuard().pre(_step("Pointer Click", "PlatynUI.BareMetal"))
    return {"file": "tests/desk.robot", "ok": False, "ran": [
        {"line": 6, "status": "PASS", "kw": "Log"},
        {"line": 7, "status": "NOT RUN", "kw": "Pointer Click", "owner": "PlatynUI.BareMetal", "guard": ref,
         "msg": "refused before execution by the desktop probe: DESKTOP"}]}


@pytest.mark.parametrize("fmt", [leanfmt, richfmt])
def test_refusal_reaches_the_feedback(fmt):
    src = ["*** Test Cases ***", "T", "", "", "", "    Log    hi",
           "    Pointer Click    app:Application[@Name='Editor']//control:Button[@Name='OK']"]
    out, failed = fmt.live_out(_refused_run(), src, "claude", lambda _key: False)
    text = out.render(1200 if fmt is richfmt else 700)
    assert failed
    assert "L7 NOT RUN" in text and "verdict: DESKTOP_REFUSED (desktop_disabled)" in text and "RFH_DESKTOP=1" in text
    assert "NEXT: line 7 was refused by the desktop guard" in text
