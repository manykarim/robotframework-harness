"""Harness-only behavior of ``rf_harness.runtime.desktop``: the RFH_DESKTOP gate,
the spec scenario "active desktop is protected", and the decision API contract.
Platform independent (display facts are injected)."""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

import pytest

from rf_harness.runtime import desktop
from rf_harness.runtime.desktop import (
    DESKTOP_DISABLED,
    DESKTOP_DISABLED_MESSAGE,
    ENV_VARIABLES,
    RFMCP_ENV_MAP,
    SessionFacts,
    desktop_enabled,
    evaluate_step,
    probe_context,
)
from rf_harness.runtime.desktop import focus as focus_mod

BTN = "/app:*[@Name='gnome-calculator']//control:Button[@Name='7']"
ACTIVE_GUARD_TEXT = (
    "bound display classified 'active': refusing desktop input to avoid leaking onto the user's active session."
)
DESKTOP_SESSION = SessionFacts(desktop_session=True)


def _ctx(env: dict, *, wm: bool | None, ownership: str | None = None, session: SessionFacts = DESKTOP_SESSION):
    return probe_context(
        env,
        session=session,
        platform="linux",
        is_windows=False,
        was_wayland=False,
        wm_probe=lambda _d: wm,
        ownership_probe=(lambda _e, _d: ownership) if ownership else None,
    )


ACTIVE = {"DISPLAY": ":0"}
ISOLATED = {"DISPLAY": ":99", "RFH_PLATYNUI_ISOLATED_DISPLAY": ":99"}


# --- feature gate --------------------------------------------------------------------


@pytest.mark.parametrize(
    ("value", "enabled"),
    [(None, False), ("0", False), ("", False), ("1", True), (" 1 ", True), ("true", False), ("yes", False)],
)
def test_desktop_enabled_only_for_exact_1(value, enabled):
    env = {} if value is None else {"RFH_DESKTOP": value}
    assert desktop_enabled(env) is enabled


def test_active_desktop_input_step_is_refused_by_default():
    """Spec scenario: an input step on the user's active desktop without an
    isolation opt-in is refused with rf-mcp's guidance (gate off by default)."""
    decision = evaluate_step("Pointer Click", [BTN], _ctx(ACTIVE, wm=True))
    assert decision.allowed is False
    assert decision.rule == DESKTOP_DISABLED
    assert decision.refusals == (DESKTOP_DISABLED, "platynui_active_desktop_guard")
    assert decision.reason == DESKTOP_DISABLED_MESSAGE
    # rf-mcp's guard text and isolation recipe are part of the guidance.
    assert ACTIVE_GUARD_TEXT in decision.guidance
    assert "RFH_PLATYNUI_ISOLATED_DISPLAY=:100" in decision.guidance
    assert "ESCAPE HATCH" in decision.guidance
    assert decision.hints[1]["isolation_recipe"]["recommended_mode"] == "visible"
    assert decision.safety == {
        "classification": "active",
        "enforcing": True,
        "allowed": False,
        "bypassed": False,
        "reason": decision.hints[1]["message"],
    }
    assert decision.focus is None  # nothing is prepared for dispatch


def test_active_desktop_still_refused_with_gate_open():
    decision = evaluate_step("Keyboard Type", [BTN, "7"], _ctx({**ACTIVE, "RFH_DESKTOP": "1"}, wm=True))
    assert decision.allowed is False
    assert decision.refusals == ("platynui_active_desktop_guard",)
    assert decision.reason.startswith(ACTIVE_GUARD_TEXT)
    assert decision.guidance.startswith(ACTIVE_GUARD_TEXT)
    assert "Xephyr" in decision.guidance


def test_isolated_display_needs_the_gate():
    gated = evaluate_step("Pointer Click", [BTN], _ctx(ISOLATED, wm=True, ownership="verified"))
    assert gated.allowed is False
    assert gated.refusals == (DESKTOP_DISABLED,)

    allowed = evaluate_step(
        "Pointer Click", [BTN], _ctx({**ISOLATED, "RFH_DESKTOP": "1"}, wm=True, ownership="verified")
    )
    assert allowed.allowed is True
    assert allowed.safety is not None and allowed.safety["classification"] == "isolated"
    assert allowed.focus == desktop.FocusPlan(
        required=True, bypassed=False, descriptor=BTN, scope="/app:*[@Name='gnome-calculator']"
    )


def test_uncorroborated_marker_is_refused_even_with_gate_open():
    decision = evaluate_step("Pointer Click", [BTN], _ctx({**ISOLATED, "RFH_DESKTOP": "1"}, wm=None))
    assert decision.allowed is False
    assert decision.safety is not None and decision.safety["classification"] == "unknown"


def test_rf_mcp_opt_in_names_are_not_honored():
    env = {**ACTIVE, "RFH_DESKTOP": "1", "ROBOTMCP_PLATYNUI_ALLOW_ACTIVE_DESKTOP": "1"}
    assert evaluate_step("Pointer Click", [BTN], _ctx(env, wm=True)).allowed is False
    env = {**ACTIVE, "RFH_DESKTOP": "1", "RFH_PLATYNUI_ALLOW_ACTIVE_DESKTOP": "1"}
    bypassed = evaluate_step("Pointer Click", [BTN], _ctx(env, wm=True))
    assert bypassed.allowed is True
    assert bypassed.safety is not None and bypassed.safety["bypassed"] is True


def test_gate_refuses_every_platynui_keyword_but_not_other_steps():
    ctx = _ctx(ISOLATED, wm=True, ownership="verified")
    for keyword in ("Query", "Get Attribute", "Close Window", "Take Screenshot", "PlatynUI.BareMetal.Highlight"):
        assert evaluate_step(keyword, ["/app:*"], ctx).refusals == (DESKTOP_DISABLED,), keyword
    assert evaluate_step("Log", ["hello"], ctx).allowed is True
    assert evaluate_step("Set Variable", ["x"], ctx).allowed is True


def test_gate_refuses_desktop_gui_launches(tmp_path):
    exe = tmp_path / "soffice"
    exe.write_text("#!/bin/sh\n")
    exe.chmod(0o755)
    env = {**ISOLATED, "PATH": str(tmp_path)}
    ctx = _ctx(env, wm=True, ownership="verified")
    assert evaluate_step("Start Process", [str(exe)], ctx).refusals == (DESKTOP_DISABLED,)
    assert evaluate_step("Start Process", ["bash", "-c", "true"], ctx).allowed is True

    opened = _ctx({**env, "RFH_DESKTOP": "1"}, wm=True, ownership="verified")
    launch = evaluate_step("Start Process", [str(exe), "--writer"], opened)
    assert launch.allowed is True
    assert launch.launch is not None and launch.launch["binary"] == "soffice"
    assert "GTK_A11Y" in launch.launch["a11y_backend"]
    assert "env:GTK_A11Y=atspi" in launch.arguments


# --- which steps the chain applies to ------------------------------------------------


def test_non_desktop_steps_are_not_probed():
    def boom(*_a, **_k):
        raise AssertionError("must not probe for non-desktop steps")

    original = desktop.decision.probe_context
    desktop.decision.probe_context = boom
    try:
        for keyword, session in (
            ("Query", SessionFacts(desktop_session=False)),
            ("Query", SessionFacts()),  # ambiguous name, unknown session (DatabaseLibrary has Query)
            ("Take Screenshot", SessionFacts()),
            ("Click", SessionFacts()),
            ("Pointer Click", SessionFacts(desktop_session=False)),
        ):
            decision = evaluate_step(keyword, ["SELECT 1"], session=session)
            assert decision.applies is False and decision.allowed is True, keyword
            assert decision.arguments == ("SELECT 1",)
    finally:
        desktop.decision.probe_context = original


@pytest.mark.parametrize(
    ("keyword", "session", "applies"),
    [
        ("Pointer Click", None, True),
        ("Keyboard Type", None, True),
        ("Close Window", None, True),
        ("Query", None, False),
        ("Get Attribute", None, False),
        ("PlatynUI.BareMetal.Query", None, True),
        ("PlatynUI.BareMetal.Pointer Click", False, True),
        ("Log", True, True),
        ("Log", None, False),
    ],
)
def test_is_desktop_step(keyword, session, applies):
    assert desktop.is_desktop_step(keyword, session) is applies


# --- warnings, focus plan and API shape ----------------------------------------------


def test_one_time_opt_in_warnings_are_surfaced():
    env = {
        **ISOLATED,
        "RFH_DESKTOP": "1",
        "RFH_PLATYNUI_ALLOW_PATH_DESCRIPTOR": "1",
        "RFH_PLATYNUI_ALLOW_CONTROL_WINDOW": "1",
    }
    ctx = _ctx(env, wm=True, ownership="verified")
    shot = evaluate_step("Take Screenshot", ["calc.png"], ctx)
    assert shot.allowed is True
    assert shot.warning_types == ("screenshot_path_descriptor_allowed",)
    window = evaluate_step("Query", ["/app:*[@Name='x']//control:Window"], ctx)
    assert window.warning_types == ("control_window_allowed",)
    warned = SessionFacts(desktop_session=True, warned=frozenset(window.warning_types))
    again = evaluate_step(
        "Query", ["/app:*[@Name='x']//control:Window"], _ctx(env, wm=True, ownership="verified", session=warned)
    )
    assert again.warnings == ()


def test_focus_bypass_is_planned_from_env():
    env = {**ISOLATED, "RFH_DESKTOP": "1", "RFH_PLATYNUI_NO_FOCUS": "1"}
    decision = evaluate_step("Keyboard Type", ["${None}", "x"], _ctx(env, wm=True, ownership="verified"))
    assert decision.focus == desktop.FocusPlan(required=False, bypassed=True, descriptor=None, scope=None)


def test_unfocused_typing_warning_is_once_per_session():
    warned: set[str] = set()
    first = focus_mod.FocusOutcome()
    first.warnings = [focus_mod.UNFOCUSED_TYPING_WARNING, "other"]
    focus_mod.drop_repeated_unfocused_typing(first, warned)
    assert first.warnings == [focus_mod.UNFOCUSED_TYPING_WARNING, "other"]
    second = focus_mod.FocusOutcome()
    second.warnings = [focus_mod.UNFOCUSED_TYPING_WARNING]
    focus_mod.drop_repeated_unfocused_typing(second, warned)
    assert second.warnings == []
    assert focus_mod.focus_hints(first)[0] == {
        "type": "platynui_focus_warning",
        "message": focus_mod.UNFOCUSED_TYPING_WARNING,
    }


def test_decision_and_context_are_json_serializable():
    ctx = _ctx(ACTIVE, wm=True)
    decision = evaluate_step("Pointer Click", [BTN], ctx)
    json.dumps(decision.to_dict())
    json.dumps(ctx.to_dict())
    assert ctx.to_dict()["isolation"] == "active"


def test_probe_context_is_side_effect_free():
    before = dict(os.environ)
    # pin the platform: the classification under test is the Linux/X11 one (Windows classifies as "windows")
    ctx = probe_context({"DISPLAY": ":0", "XDG_SESSION_TYPE": "wayland"}, platform="linux", is_windows=False,
                        probe_display=False)
    assert dict(os.environ) == before
    assert (ctx.isolation, ctx.isolation_source) == ("unknown", "none")
    assert ctx.was_wayland is True


def test_windows_active_desktop_allowed_unless_isolation_required():
    windows = probe_context({"RFH_DESKTOP": "1"}, session=DESKTOP_SESSION, platform="win32", is_windows=True)
    assert evaluate_step("Pointer Click", [BTN], windows).allowed is True
    strict = probe_context(
        {"RFH_DESKTOP": "1", "RFH_PLATYNUI_REQUIRE_ISOLATED": "1"},
        session=DESKTOP_SESSION,
        platform="win32",
        is_windows=True,
    )
    refused = evaluate_step("Pointer Click", [BTN], strict)
    assert refused.allowed is False
    assert "Xephyr" not in refused.guidance  # no Linux recipe on Windows


# --- env registry and standalone package ---------------------------------------------


def test_env_registry():
    assert all(name.startswith("RFH_") for name in ENV_VARIABLES)
    assert set(RFMCP_ENV_MAP.values()) <= set(ENV_VARIABLES)
    assert all(name.startswith("ROBOTMCP_") for name in RFMCP_ENV_MAP)
    assert ENV_VARIABLES["RFH_DESKTOP"][0] == "0"
    source = "\n".join(p.read_text() for p in Path(desktop.__file__).parent.glob("*.py"))
    for name in re.findall(r"\bRFH_[A-Z0-9_]+\b", source):
        assert name in ENV_VARIABLES, name


def test_package_does_not_depend_on_rf_mcp():
    pkg = Path(desktop.__file__).parent
    for path in pkg.glob("*.py"):
        text = path.read_text()
        assert not re.search(r"^\s*(from|import)\s+robotmcp\b", text, re.MULTILINE), path
    assert not any(name == "robotmcp" or name.startswith("robotmcp.") for name in sys.modules)
