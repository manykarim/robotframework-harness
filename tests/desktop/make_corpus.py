"""Record rf-mcp's desktop guard decisions into ``tests/desktop/corpus.json``.

This is the ONLY place rf-mcp is imported. Run it with rf-mcp's environment:

    cd /home/many/workspace/rf-mcp && uv run --no-sync python \\
        /home/many/workspace/robotframework-ai-engineering/tests/desktop/make_corpus.py

``RFMCP_ROOT`` overrides the rf-mcp checkout. The harness tests
(``test_desktop_parity.py``) replay the JSON against
``rf_harness.runtime.desktop`` without importing rf-mcp. Inputs are recorded in
rf-mcp's own terms (``ROBOTMCP_*`` env names, rf-mcp text); the tests apply the
documented renames (see ``desktop_fakes.normalize_text`` / ``map_env_keys``).

Recorded functions (module paths under ``robotmcp.components.execution``):
``desktop_display_safety`` (classify_bound_display_detailed, _marker_ownership_status,
evaluate_safety, build_isolation_recipe, allow_opt_in, warn_mode, require_isolated),
``desktop_execution_signals`` (keyword predicates, is_unscoped_locator, screenshot and
control:Window detectors, wayland_input_warning, input_effect_hint, steering_confidence*),
``platynui_focus`` (normalize_keyword, extract_descriptor, app_scope_of, is_unscoped,
env switches, pid_in_aut_lineage, PlatynUIFocusManager.ensure_focused),
``desktop_launch_env`` (build_desktop_launch_env, is_desktop_gui_launch,
gui_launch_overrides, resolve_executable), ``desktop_guidance`` (crib, signature
compression), ``keyword_executor.KeywordExecutor`` guard methods (the pre-dispatch chain)
and ``plugins.builtin.platynui_plugin`` (ensure_x11_session_env, _record_session_origin).
"""

from __future__ import annotations

import datetime
import hashlib
import json
import os
import subprocess
import sys
import types
from contextlib import contextmanager
from pathlib import Path
from typing import Any
from unittest import mock

HERE = Path(__file__).resolve().parent
RFMCP_ROOT = Path(os.environ.get("RFMCP_ROOT", "/home/many/workspace/rf-mcp")).resolve()
sys.path.insert(0, str(RFMCP_ROOT / "src"))
sys.path.insert(0, str(HERE))

import desktop_fakes as fx  # noqa: E402
from robotmcp.components.execution import desktop_display_safety as dds  # noqa: E402
from robotmcp.components.execution import desktop_execution_signals as sig  # noqa: E402
from robotmcp.components.execution import desktop_guidance as dg  # noqa: E402
from robotmcp.components.execution import desktop_launch_env as dle  # noqa: E402
from robotmcp.components.execution import platynui_focus as pf  # noqa: E402
from robotmcp.components.execution.keyword_executor import KeywordExecutor  # noqa: E402
from robotmcp.plugins.builtin import platynui_plugin as pp  # noqa: E402

M = "ROBOTMCP_PLATYNUI_ISOLATED_DISPLAY"
X = "ROBOTMCP_PLATYNUI_ISOLATED_XPID"
ALLOW = "ROBOTMCP_PLATYNUI_ALLOW_ACTIVE_DESKTOP"
GUARD = "ROBOTMCP_PLATYNUI_SAFETY_GUARD"
REQ = "ROBOTMCP_PLATYNUI_REQUIRE_ISOLATED"
RECIPE = "<isolation_recipe>"

SOURCE_FILES = (
    "src/robotmcp/components/execution/desktop_display_safety.py",
    "src/robotmcp/components/execution/desktop_execution_signals.py",
    "src/robotmcp/components/execution/desktop_launch_env.py",
    "src/robotmcp/components/execution/desktop_guidance.py",
    "src/robotmcp/components/execution/platynui_focus.py",
    "src/robotmcp/components/execution/keyword_executor.py",
    "src/robotmcp/plugins/builtin/platynui_plugin.py",
)


# --- helpers -------------------------------------------------------------------


@contextmanager
def patched(obj: Any, name: str, value: Any):
    missing = object()
    old = getattr(obj, name, missing)
    setattr(obj, name, value)
    try:
        yield
    finally:
        if old is missing:
            delattr(obj, name)
        else:
            setattr(obj, name, old)


@contextmanager
def os_environ(env: dict[str, str] | None):
    if env is None:
        yield
        return
    with mock.patch.dict(os.environ, env, clear=True):
        yield


def constant(value: Any):
    """A stand-in function that ignores its arguments and returns ``value``."""

    def _fn(*_args: Any, **_kwargs: Any) -> Any:
        return value

    return _fn


def jsonable(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {str(k): jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [jsonable(v) for v in obj]
    if isinstance(obj, (set, frozenset)):
        return sorted(jsonable(v) for v in obj)
    return obj


def strip_recipe(obj: Any, recipe: dict) -> Any:
    """Replace every full isolation recipe with a sentinel (the recipe has its own case)."""
    if isinstance(obj, dict):
        if obj == recipe:
            return RECIPE
        return {k: strip_recipe(v, recipe) for k, v in obj.items()}
    if isinstance(obj, list):
        return [strip_recipe(v, recipe) for v in obj]
    return obj


@contextmanager
def display_probes(wm: Any, ownership: str | None, is_windows: bool):
    with patched(dds, "_ewmh_wm_present", lambda _d: wm), patched(dds, "_is_windows", lambda: is_windows):
        if ownership is None:
            yield
        else:
            with patched(dds, "_marker_ownership_status", lambda _e, _d: ownership):
                yield


class Recorder:
    def __init__(self, ph: fx.Placeholders) -> None:
        self.ph = ph
        self.cases: list[dict] = []
        self.recipe = dds.build_isolation_recipe()

    def add(self, kind: str, case_id: str, inputs: dict, expected: Any) -> None:
        ids = {c["id"] for c in self.cases}
        assert case_id not in ids, case_id
        self.cases.append(
            {
                "id": case_id,
                "kind": kind,
                "input": inputs,
                "expected": strip_recipe(self.ph.unsubst(jsonable(expected)), self.recipe),
            }
        )


# --- A/B/C: classification, ownership, safety ------------------------------------

CLASSIFY_CASES = [
    ("marker_verified_wm_present", {"DISPLAY": ":99", M: ":99"}, True, "verified", False),
    ("marker_verified_no_wm", {"DISPLAY": ":99", M: ":99"}, False, "verified", False),
    ("marker_verified_probe_failed", {"DISPLAY": ":99", M: ":99"}, None, "verified", False),
    ("marker_absent_no_wm", {"DISPLAY": ":99", M: ":99"}, None, "absent", False),
    ("marker_absent_wm_active", {"DISPLAY": ":99", M: ":99"}, True, "absent", False),
    ("marker_absent_wm_false", {"DISPLAY": ":99", M: ":99"}, False, "absent", False),
    ("marker_invalid_wm_active", {"DISPLAY": ":99", M: ":99"}, True, "invalid", False),
    ("marker_invalid_no_wm", {"DISPLAY": ":99", M: ":99"}, False, "invalid", False),
    ("marker_invalid_probe_failed", {"DISPLAY": ":99", M: ":99"}, None, "invalid", False),
    ("marker_list_comma", {"DISPLAY": ":99", M: ":98, :99"}, True, "verified", False),
    ("marker_list_space", {"DISPLAY": ":99", M: ":98 :99"}, True, "verified", False),
    ("marker_other_display_wm_active", {"DISPLAY": ":99", M: ":98"}, True, "verified", False),
    ("marker_other_display_no_wm", {"DISPLAY": ":99", M: ":98"}, False, "verified", False),
    ("marker_without_display", {M: ":99"}, True, "verified", False),
    ("marker_empty", {"DISPLAY": ":0", M: ""}, True, "verified", False),
    ("display_whitespace_marker", {"DISPLAY": " :99 ", M: ":99"}, None, "verified", False),
    ("no_marker_wm_true", {"DISPLAY": ":0"}, True, None, False),
    ("no_marker_wm_false", {"DISPLAY": ":0"}, False, None, False),
    ("no_marker_probe_failed", {"DISPLAY": ":0"}, None, None, False),
    ("no_display", {}, True, None, False),
    ("empty_display", {"DISPLAY": ""}, True, None, False),
    ("wayland_only", {"WAYLAND_DISPLAY": "wayland-0", "XDG_SESSION_TYPE": "wayland"}, None, None, False),
    ("windows_console", {"DISPLAY": ":99", M: ":99"}, True, "verified", True),
    ("windows_no_display", {}, None, None, True),
    # Real ownership probe (fake Xvfb processes via placeholders).
    ("real_xpid_verified", {"DISPLAY": ":99", M: ":99", X: "{XVFB_99_PID}"}, None, None, False),
    ("real_xpid_verified_wm_present", {"DISPLAY": ":99", M: ":99", X: "{XVFB_99_PID}"}, True, None, False),
    ("real_xpid_other_display", {"DISPLAY": ":99", M: ":99", X: "{XVFB_98_PID}"}, False, None, False),
    ("real_xpid_other_display_wm", {"DISPLAY": ":99", M: ":99", X: "{XVFB_98_PID}"}, True, None, False),
    ("real_xpid_self_not_xserver", {"DISPLAY": ":99", M: ":99", X: "{SELF_PID}"}, None, None, False),
    ("real_xpid_garbage", {"DISPLAY": ":99", M: ":99", X: "abc"}, None, None, False),
    ("real_xpid_zero", {"DISPLAY": ":99", M: ":99", X: "0"}, True, None, False),
    ("real_xpid_negative", {"DISPLAY": ":99", M: ":99", X: "-5"}, None, None, False),
    ("real_xpid_dead", {"DISPLAY": ":99", M: ":99", X: "2147480000"}, None, None, False),
    ("real_xpid_blank", {"DISPLAY": ":99", M: ":99", X: "  "}, True, None, False),
    ("real_xpid_no_marker", {"DISPLAY": ":99", X: "{XVFB_99_PID}"}, True, None, False),
]

OWNERSHIP_CASES = [
    ("no_xpid", {}, ":99"),
    ("not_a_pid", {X: "not-a-pid"}, ":99"),
    ("zero", {X: "0"}, ":99"),
    ("negative", {X: "-1"}, ":99"),
    ("dead_pid", {X: "2147480000"}, ":99"),
    ("self_pid", {X: "{SELF_PID}"}, ":99"),
    ("xvfb_match", {X: "{XVFB_99_PID}"}, ":99"),
    ("xvfb_match_whitespace", {X: " {XVFB_99_PID} "}, ":99"),
    ("xvfb_other_display", {X: "{XVFB_98_PID}"}, ":99"),
    ("xvfb_no_display", {X: "{XVFB_99_PID}"}, None),
    ("xvfb_display_padded", {X: "{XVFB_99_PID}"}, " :99 "),
]

SAFETY_CASES = [
    # id, env, wm, ownership, is_windows, session_opt_in
    ("active_refused", {"DISPLAY": ":0"}, True, None, False, False),
    ("unknown_bare_x_refused", {"DISPLAY": ":0"}, False, None, False, False),
    ("unknown_probe_failed_refused", {"DISPLAY": ":0"}, None, None, False, False),
    ("no_display_refused", {}, None, None, False, False),
    ("isolated_allowed", {"DISPLAY": ":99", M: ":99"}, True, "verified", False, False),
    ("marker_unverified_refused", {"DISPLAY": ":99", M: ":99"}, None, "absent", False, False),
    ("env_opt_in_1", {"DISPLAY": ":0", ALLOW: "1"}, True, None, False, False),
    ("env_opt_in_true", {"DISPLAY": ":0", ALLOW: "true"}, True, None, False, False),
    ("env_opt_in_yes_upper_padded", {"DISPLAY": ":0", ALLOW: " YES "}, False, None, False, False),
    ("env_opt_in_0_refused", {"DISPLAY": ":0", ALLOW: "0"}, True, None, False, False),
    ("env_opt_in_on_refused", {"DISPLAY": ":0", ALLOW: "on"}, True, None, False, False),
    ("session_opt_in", {"DISPLAY": ":0"}, True, None, False, True),
    ("warn_mode", {"DISPLAY": ":0", GUARD: "warn"}, True, None, False, False),
    ("warn_mode_upper", {"DISPLAY": ":0", GUARD: " WARN "}, None, None, False, False),
    ("guard_enforce_value", {"DISPLAY": ":0", GUARD: "enforce"}, True, None, False, False),
    ("warn_and_opt_in", {"DISPLAY": ":0", GUARD: "warn", ALLOW: "1"}, True, None, False, False),
    ("isolated_warn_mode", {"DISPLAY": ":99", M: ":99", GUARD: "warn"}, True, "verified", False, False),
    ("isolated_opt_in", {"DISPLAY": ":99", M: ":99", ALLOW: "1"}, True, "verified", False, False),
    ("windows_default_allowed", {}, None, None, True, False),
    ("windows_require_isolated", {REQ: "1"}, None, None, True, False),
    ("windows_require_isolated_true", {REQ: "TRUE"}, None, None, True, False),
    ("windows_require_isolated_0", {REQ: "0"}, None, None, True, False),
    ("windows_require_with_opt_in", {REQ: "1", ALLOW: "1"}, None, None, True, True),
    ("linux_require_isolated_ignored", {"DISPLAY": ":0", REQ: "1"}, True, None, False, False),
]


def record_display(rec: Recorder) -> None:
    for case_id, env, wm, ownership, windows in CLASSIFY_CASES:
        with display_probes(wm, ownership, windows):
            out = dds.classify_bound_display_detailed(rec.ph.subst(env))
        rec.add("classify", case_id, {"env": env, "wm": wm, "ownership": ownership, "is_windows": windows}, out)
    for case_id, env, display in OWNERSHIP_CASES:
        out = dds._marker_ownership_status(rec.ph.subst(env), display)
        rec.add("ownership", case_id, {"env": env, "display": display}, out)
    for case_id, env, wm, ownership, windows, session_opt_in in SAFETY_CASES:
        session = types.SimpleNamespace(platynui_allow_active_desktop=session_opt_in)
        with display_probes(wm, ownership, windows):
            out = dds.evaluate_safety(session, rec.ph.subst(env))
        rec.add(
            "safety",
            case_id,
            {"env": env, "wm": wm, "ownership": ownership, "is_windows": windows, "session_opt_in": session_opt_in},
            out,
        )
    rec.cases.append(
        {"id": "isolation_recipe", "kind": "recipe", "input": {}, "expected": dds.build_isolation_recipe()}
    )


# --- E: the executor's pre-dispatch guard chain ---------------------------------

WARNED_FLAGS = {
    "unscoped_desktop_locator_allowed": "desktop_unscoped_warned",
    "screenshot_path_descriptor_allowed": "desktop_path_descriptor_warned",
    "control_window_allowed": "desktop_control_window_warned",
    "wayland_x11_input_blocked_risk": "desktop_wayland_warned",
}


def rf_step(case: dict, ph: fx.Placeholders) -> dict:
    """rf-mcp's pre-dispatch desktop block, in the executor's order."""
    keyword = case["keyword"]
    args = ph.subst(case.get("args", []))
    env = ph.subst(case.get("env", {}))
    sess = case.get("session", {})
    warned = set(sess.get("warned", []))
    desktop = sess.get("desktop_session", True)
    session = types.SimpleNamespace(
        is_desktop_session=lambda: desktop,
        platynui_allow_active_desktop=sess.get("allow_active_desktop", False),
        platynui_allow_unscoped=sess.get("allow_unscoped", False),
        platynui_allow_path_descriptor=sess.get("allow_path_descriptor", False),
        platynui_allow_control_window=sess.get("allow_control_window", False),
        platynui_no_sanitize=sess.get("no_sanitize", False),
        desktop_aut_pid=None,
        **{flag: (wtype in warned) for wtype, flag in WARNED_FLAGS.items()},
    )
    app = sess.get("aut_app_name")
    ex = KeywordExecutor.__new__(KeywordExecutor)
    with (
        os_environ(env),
        display_probes(case.get("wm"), case.get("ownership"), case.get("is_windows", False)),
        patched(sys, "platform", case.get("platform", "linux")),
        patched(KeywordExecutor, "_infer_session_app_name", staticmethod(lambda _s: app)),
        patched(pp, "_WAYLAND_ORIGIN", bool(case.get("was_wayland", False))),
    ):
        if desktop is not True:
            return {
                "applies": False,
                "allowed": True,
                "refusal": None,
                "safety": None,
                "warnings": [],
                "arguments": args,
            }
        safety = ex._platynui_safety_guard(session, keyword)
        refusal = None
        if safety is not None and not safety["allowed"]:
            # Inline refusal payload copied from KeywordExecutor._execute_keyword_inner.
            hint = {"type": "platynui_active_desktop_guard", "message": safety["reason"]}
            if safety.get("isolation_recipe"):
                hint["isolation_recipe"] = safety["isolation_recipe"]
            refusal = {
                "success": False,
                "error": safety["reason"],
                "keyword": keyword,
                "platynui_safety": {"classification": safety["classification"], "enforcing": safety["enforcing"]},
                "hints": [hint],
            }
        if refusal is None:
            for guard in (
                lambda: ex._screenshot_path_guard(keyword, args),
                lambda: ex._unscoped_locator_guard(session, keyword, args),
                lambda: ex._screenshot_signature_guard(session, keyword, args),
                lambda: ex._control_window_guard(session, keyword, args),
            ):
                refusal = guard()
                if refusal is not None:
                    break
        safety_out = None
        if safety is not None:
            safety_out = {k: safety.get(k) for k in ("classification", "enforcing", "allowed", "bypassed", "reason")}
        if refusal is not None:
            return {
                "applies": True,
                "allowed": False,
                "refusal": refusal,
                "safety": safety_out,
                "warnings": [],
                "arguments": args,
            }
        warnings = [
            w
            for w in (
                getattr(session, "_pending_unscoped_hint", None),
                getattr(session, "_pending_path_descriptor_hint", None),
                getattr(session, "_pending_control_window_hint", None),
            )
            if w
        ]
        # Post-execution block: once per session for interaction keywords.
        if sig.is_interaction_keyword(keyword) and not session.desktop_wayland_warned:
            wh = sig.wayland_input_warning(keyword)
            if wh:
                warnings.append(wh)
        dispatched = ex._maybe_resolve_desktop_executable(session, keyword, args)
        dispatched = ex._maybe_sanitize_desktop_launch(session, keyword, dispatched)
        return {
            "applies": True,
            "allowed": True,
            "refusal": None,
            "safety": safety_out,
            "warnings": warnings,
            "arguments": dispatched,
        }


BTN = "/app:*[@Name='gnome-calculator']//control:Button[@Name='7']"
ISO = {"DISPLAY": ":99", M: ":99"}
LAUNCH_PATH = {"PATH": "{EXE_DIR}", "DISPLAY": ":99", M: ":99"}
SNAPPY = {
    "PATH": "{EXE_DIR}",
    "DISPLAY": ":99",
    "LD_LIBRARY_PATH": "/snap/core20/current/lib/x86_64-linux-gnu:/usr/lib/x86_64-linux-gnu",
    "GTK_PATH": "/snap/code/current/gtk:/usr/lib/gtk",
    "GIO_MODULE_DIR": "/snap/code/current/gio",
    "XDG_DATA_DIRS": "/var/lib/snapd/desktop:/usr/share:/snap/foo/share",
    "LD_PRELOAD": "/snap/core20/current/lib/libfoo.so",
    "GTK_EXE_PREFIX": "/snap/code/current/usr",
    "FONTCONFIG_FILE": "/etc/fonts/fonts.conf",
    "QT_PLUGIN_PATH": "/snap/qt/current/plugins:/usr/lib/qt/plugins",
    "WAYLAND_DISPLAY": "wayland-0",
}


def _s(**kw: Any) -> dict:
    return kw


STEP_CASES: list[dict] = [
    # Active-desktop safety guard (pointer/keyboard input).
    _s(id="pointer_click_active_refused", keyword="Pointer Click", args=[BTN], env={"DISPLAY": ":0"}, wm=True),
    _s(id="pointer_click_bare_x_refused", keyword="Pointer Click", args=[BTN], env={"DISPLAY": ":0"}, wm=False),
    _s(id="pointer_click_probe_failed_refused", keyword="Pointer Click", args=[BTN], env={"DISPLAY": ":0"}, wm=None),
    _s(id="pointer_click_no_display_refused", keyword="Pointer Click", args=[BTN], env={}, wm=None),
    _s(
        id="pointer_click_isolated_allowed", keyword="Pointer Click", args=[BTN], env=ISO, wm=True, ownership="verified"
    ),
    _s(
        id="pointer_click_real_xvfb_allowed",
        keyword="Pointer Click",
        args=[BTN],
        env={**ISO, X: "{XVFB_99_PID}"},
        wm=True,
    ),
    _s(
        id="pointer_click_stale_xpid_refused",
        keyword="Pointer Click",
        args=[BTN],
        env={**ISO, X: "{XVFB_98_PID}"},
        wm=True,
    ),
    _s(id="pointer_click_marker_unverified_refused", keyword="Pointer Click", args=[BTN], env=ISO, wm=None),
    _s(id="keyboard_type_active_refused", keyword="Keyboard Type", args=[BTN, "hello"], env={"DISPLAY": ":0"}, wm=True),
    _s(
        id="keyboard_type_at_focus_active_refused",
        keyword="Keyboard Type",
        args=["${None}", "hello"],
        env={"DISPLAY": ":0"},
        wm=True,
    ),
    _s(
        id="keyboard_press_active_refused",
        keyword="Keyboard Press",
        args=["${None}", "<Ctrl>"],
        env={"DISPLAY": ":0"},
        wm=True,
    ),
    _s(
        id="keyboard_release_active_refused",
        keyword="Keyboard Release",
        args=["${None}", "<Ctrl>"],
        env={"DISPLAY": ":0"},
        wm=True,
    ),
    _s(id="pointer_press_active_refused", keyword="Pointer Press", args=[BTN], env={"DISPLAY": ":0"}, wm=True),
    _s(id="pointer_release_active_refused", keyword="Pointer Release", args=[BTN], env={"DISPLAY": ":0"}, wm=True),
    _s(id="pointer_move_to_active_refused", keyword="Pointer Move To", args=[BTN], env={"DISPLAY": ":0"}, wm=True),
    _s(
        id="pointer_multi_click_active_refused",
        keyword="Pointer Multi Click",
        args=[BTN, "2"],
        env={"DISPLAY": ":0"},
        wm=True,
    ),
    _s(
        id="prefixed_pointer_click_active_refused",
        keyword="PlatynUI.BareMetal.Pointer Click",
        args=[BTN],
        env={"DISPLAY": ":0"},
        wm=True,
    ),
    _s(
        id="snake_case_keyboard_type_active_refused",
        keyword="keyboard_type",
        args=[BTN, "x"],
        env={"DISPLAY": ":0"},
        wm=True,
    ),
    _s(
        id="pointer_click_env_opt_in_bypassed",
        keyword="Pointer Click",
        args=[BTN],
        env={"DISPLAY": ":0", ALLOW: "1"},
        wm=True,
    ),
    _s(
        id="pointer_click_session_opt_in_bypassed",
        keyword="Pointer Click",
        args=[BTN],
        env={"DISPLAY": ":0"},
        wm=True,
        session={"allow_active_desktop": True},
    ),
    _s(
        id="pointer_click_warn_mode", keyword="Pointer Click", args=[BTN], env={"DISPLAY": ":0", GUARD: "warn"}, wm=True
    ),
    _s(
        id="pointer_click_windows_allowed",
        keyword="Pointer Click",
        args=[BTN],
        env={},
        is_windows=True,
        platform="win32",
    ),
    _s(
        id="pointer_click_windows_require_isolated_refused",
        keyword="Pointer Click",
        args=[BTN],
        env={REQ: "1"},
        is_windows=True,
        platform="win32",
    ),
    # Not covered by rf-mcp's active-desktop guard (only pointer/keyboard are).
    _s(id="query_active_not_guarded", keyword="Query", args=[BTN], env={"DISPLAY": ":0"}, wm=True),
    _s(
        id="close_window_active_not_guarded",
        keyword="Close Window",
        args=["/app:*[@Name='x']//control:Frame"],
        env={"DISPLAY": ":0"},
        wm=True,
    ),
    _s(
        id="activate_window_active_not_guarded",
        keyword="Activate Window",
        args=["/app:*[@Name='x']//control:Frame"],
        env={"DISPLAY": ":0"},
        wm=True,
    ),
    _s(id="focus_active_not_guarded", keyword="Focus", args=[BTN], env={"DISPLAY": ":0"}, wm=True),
    _s(id="log_in_desktop_session", keyword="Log", args=["hello"], env={"DISPLAY": ":0"}, wm=True),
    # Unscoped-locator guardrail.
    _s(
        id="query_unscoped_refused",
        keyword="Query",
        args=["//control:Paragraph"],
        env=ISO,
        wm=True,
        ownership="verified",
    ),
    _s(
        id="query_unscoped_app_rewrite",
        keyword="Query",
        args=["//control:Paragraph"],
        env=ISO,
        session={"aut_app_name": "soffice"},
    ),
    _s(id="query_unscoped_wildcard", keyword="Query", args=["//*"], env=ISO),
    _s(id="query_bare_wildcard", keyword="Query", args=["*"], env=ISO),
    _s(id="query_descendant_axis", keyword="Query", args=["descendant::control:Button"], env=ISO),
    _s(id="query_padded_unscoped", keyword="Query", args=["  //control:Edit  "], env=ISO),
    _s(id="evaluate_unscoped_refused", keyword="Evaluate", args=["//control:Button"], env=ISO),
    _s(id="prefixed_query_unscoped", keyword="PlatynUI.BareMetal.Query", args=["//control:Button"], env=ISO),
    _s(id="query_scoped_allowed", keyword="Query", args=["/app:*[@Name='soffice']//control:Paragraph"], env=ISO),
    _s(id="query_count_allowed", keyword="Query", args=["count(//control:Paragraph)"], env=ISO),
    _s(id="query_relative_allowed", keyword="Query", args=["control:Button[@Name='OK']"], env=ISO),
    _s(id="query_no_args", keyword="Query", args=[], env=ISO),
    _s(
        id="query_unscoped_env_opt_in",
        keyword="Query",
        args=["//control:Paragraph"],
        env={**ISO, "ROBOTMCP_PLATYNUI_ALLOW_UNSCOPED": "1"},
    ),
    _s(
        id="query_unscoped_session_opt_in",
        keyword="Query",
        args=["//control:Paragraph"],
        env=ISO,
        session={"allow_unscoped": True},
    ),
    _s(
        id="query_unscoped_opt_in_already_warned",
        keyword="Query",
        args=["//control:Paragraph"],
        env={**ISO, "ROBOTMCP_PLATYNUI_ALLOW_UNSCOPED": "yes"},
        session={"warned": ["unscoped_desktop_locator_allowed"]},
    ),
    _s(
        id="query_unscoped_opt_in_0_refused",
        keyword="Query",
        args=["//control:Paragraph"],
        env={**ISO, "ROBOTMCP_PLATYNUI_ALLOW_UNSCOPED": "0"},
    ),
    _s(id="get_attribute_unscoped_not_guarded", keyword="Get Attribute", args=["//control:Edit", "Name"], env=ISO),
    # Screenshot path + descriptor-slot guards.
    _s(id="screenshot_relative_path_in_descriptor", keyword="Take Screenshot", args=["calc.png"], env=ISO),
    _s(id="screenshot_abs_outside_roots", keyword="Take Screenshot", args=["/var/rfh-shots/calc.png"], env=ISO),
    _s(
        id="screenshot_named_outside_roots",
        keyword="Take Screenshot",
        args=["filename=/var/rfh-shots/calc.png"],
        env=ISO,
    ),
    _s(id="screenshot_named_in_tmp", keyword="Take Screenshot", args=["filename={TMP}/calc.png"], env=ISO),
    _s(id="screenshot_descriptor_and_tmp_path", keyword="Take Screenshot", args=[BTN, "{TMP}/calc.png"], env=ISO),
    _s(id="screenshot_tmp_path_in_descriptor", keyword="Take Screenshot", args=["{TMP}/calc.png"], env=ISO),
    _s(id="screenshot_explicit_descriptor_path", keyword="Take Screenshot", args=["descriptor=calc.jpg"], env=ISO),
    _s(
        id="screenshot_extra_dir_allowed",
        keyword="Take Screenshot",
        args=["filename={SHOT_DIR}/a.png"],
        env={**ISO, "ROBOTMCP_SCREENSHOT_DIR": "{SHOT_DIR}"},
    ),
    _s(
        id="screenshot_outside_with_extra_dir",
        keyword="Take Screenshot",
        args=["filename=/opt/rfh/a.png"],
        env={**ISO, "ROBOTMCP_SCREENSHOT_DIR": "{SHOT_DIR}"},
    ),
    _s(id="screenshot_traversal_out_of_tmp", keyword="Take Screenshot", args=["filename={TMP}/../etc/x.png"], env=ISO),
    _s(
        id="screenshot_path_descriptor_env_opt_in",
        keyword="Take Screenshot",
        args=["calc.png"],
        env={**ISO, "ROBOTMCP_PLATYNUI_ALLOW_PATH_DESCRIPTOR": "1"},
    ),
    _s(
        id="screenshot_path_descriptor_session_opt_in_warned",
        keyword="Take Screenshot",
        args=["calc.png"],
        env=ISO,
        session={"allow_path_descriptor": True, "warned": ["screenshot_path_descriptor_allowed"]},
    ),
    _s(id="screenshot_embed", keyword="Take Screenshot", args=["EMBED"], env=ISO),
    _s(id="screenshot_templated", keyword="Take Screenshot", args=["run-{index}.png"], env=ISO),
    _s(id="screenshot_no_args", keyword="Take Screenshot", args=[], env=ISO),
    # Linux control:Window guard.
    _s(
        id="query_control_window_linux",
        keyword="Query",
        args=["/app:*[@Name='gnome-calculator']//control:Window"],
        env=ISO,
    ),
    _s(id="set_root_control_window_linux", keyword="Set Root", args=["/app:*[@Name='x']//control:Window"], env=ISO),
    _s(
        id="get_attribute_control_window_linux",
        keyword="Get Attribute",
        args=["/app:*[@Name='x']//control:window", "Name"],
        env=ISO,
    ),
    _s(
        id="pointer_click_control_window_isolated",
        keyword="Pointer Click",
        args=["/app:*[@Name='x']//control:Window//control:Button"],
        env=ISO,
        wm=True,
        ownership="verified",
    ),
    _s(
        id="query_control_window_windows",
        keyword="Query",
        args=["/app:*[@Name='x']//control:Window"],
        env={},
        is_windows=True,
        platform="win32",
    ),
    _s(
        id="query_control_window_darwin",
        keyword="Query",
        args=["/app:*[@Name='x']//control:Window"],
        env=ISO,
        platform="darwin",
    ),
    _s(
        id="query_control_window_env_opt_in",
        keyword="Query",
        args=["/app:*[@Name='x']//control:Window"],
        env={**ISO, "ROBOTMCP_PLATYNUI_ALLOW_CONTROL_WINDOW": "true"},
    ),
    _s(
        id="query_control_window_session_opt_in_warned",
        keyword="Query",
        args=["/app:*[@Name='x']//control:Window"],
        env=ISO,
        session={"allow_control_window": True, "warned": ["control_window_allowed"]},
    ),
    _s(id="query_control_frame_allowed", keyword="Query", args=["/app:*[@Name='x']//control:Frame"], env=ISO),
    _s(
        id="take_screenshot_control_window_not_guarded",
        keyword="Take Screenshot",
        args=["/app:*[@Name='x']//control:Window"],
        env=ISO,
    ),
    # Wayland input warning (once per session, interaction keywords only).
    _s(
        id="pointer_click_isolated_was_wayland",
        keyword="Pointer Click",
        args=[BTN],
        env=ISO,
        ownership="verified",
        was_wayland=True,
    ),
    _s(
        id="pointer_click_isolated_was_wayland_warned",
        keyword="Pointer Click",
        args=[BTN],
        env=ISO,
        ownership="verified",
        was_wayland=True,
        session={"warned": ["wayland_x11_input_blocked_risk"]},
    ),
    _s(
        id="keyboard_press_isolated_was_wayland",
        keyword="Keyboard Press",
        args=["${None}", "<Ctrl>"],
        env=ISO,
        ownership="verified",
        was_wayland=True,
    ),
    _s(
        id="pointer_press_isolated_was_wayland",
        keyword="Pointer Press",
        args=[BTN],
        env=ISO,
        ownership="verified",
        was_wayland=True,
    ),
    _s(id="query_was_wayland", keyword="Query", args=[BTN], env=ISO, was_wayland=True),
    _s(
        id="pointer_click_isolated_x11_origin",
        keyword="Pointer Click",
        args=[BTN],
        env=ISO,
        ownership="verified",
        was_wayland=False,
    ),
    # Launch hardening (resolve executable + sanitize + a11y overlay).
    _s(id="start_process_gui_abs", keyword="Start Process", args=["{EXE_DIR}/soffice", "--writer"], env=LAUNCH_PATH),
    _s(id="start_process_gui_bare_resolved", keyword="Start Process", args=["soffice", "--writer"], env=LAUNCH_PATH),
    _s(id="start_process_known_gnome", keyword="Start Process", args=["gnome-calculator"], env=LAUNCH_PATH),
    _s(id="start_process_snap_contaminated", keyword="Start Process", args=["mousepad"], env=SNAPPY),
    _s(
        id="start_process_snap_no_sanitize",
        keyword="Start Process",
        args=["mousepad"],
        env=SNAPPY,
        session={"no_sanitize": True},
    ),
    _s(
        id="start_process_gtk_a11y_preset",
        keyword="Start Process",
        args=["someapp"],
        env={**LAUNCH_PATH, "GTK_A11Y": "1"},
    ),
    _s(id="start_process_bash_not_gui", keyword="Start Process", args=["bash", "-c", "echo hi"], env=LAUNCH_PATH),
    _s(
        id="start_process_xdotool_resolved_not_gui",
        keyword="Start Process",
        args=["xdotool", "key", "a"],
        env=LAUNCH_PATH,
    ),
    _s(id="start_process_author_env", keyword="Start Process", args=["soffice", "env:FOO=bar"], env=LAUNCH_PATH),
    _s(id="start_process_env_first", keyword="Start Process", args=["env:FOO=bar", "soffice"], env=LAUNCH_PATH),
    _s(id="start_process_unresolvable", keyword="Start Process", args=["nope-binary-xyz"], env=LAUNCH_PATH),
    _s(id="run_process_gui", keyword="Process.Run Process", args=["{EXE_DIR}/someapp"], env=LAUNCH_PATH),
    _s(id="start_process_no_display", keyword="Start Process", args=["{EXE_DIR}/soffice"], env={"PATH": "{EXE_DIR}"}),
    _s(id="start_process_no_args", keyword="Start Process", args=[], env=LAUNCH_PATH),
    # Non-desktop session: the whole desktop block is skipped.
    _s(
        id="non_desktop_pointer_click",
        keyword="Pointer Click",
        args=[BTN],
        env={"DISPLAY": ":0"},
        wm=True,
        session={"desktop_session": False},
    ),
    _s(
        id="non_desktop_query_unscoped",
        keyword="Query",
        args=["//control:Button"],
        env={},
        session={"desktop_session": False},
    ),
    _s(
        id="non_desktop_start_process",
        keyword="Start Process",
        args=["{EXE_DIR}/soffice"],
        env=LAUNCH_PATH,
        session={"desktop_session": False},
    ),
]


def record_steps(rec: Recorder) -> None:
    for case in STEP_CASES:
        inputs = {k: v for k, v in case.items() if k != "id"}
        rec.add("step", case["id"], inputs, rf_step(case, rec.ph))


# --- F: pure function calls -------------------------------------------------------

S, F, L, D, G = (
    "desktop_execution_signals",
    "platynui_focus",
    "desktop_launch_env",
    "desktop_display_safety",
    "desktop_guidance",
)
RFH_MODULE = {S: "signals", F: "focus", L: "launch_env", D: "safety", G: "guidance"}
RFH_NAME = {"_compress_arg": "compress_arg", "_compress_signature": "compress_signature"}
RF_MODULES = {S: sig, F: pf, L: dle, D: dds, G: dg}

KW_SAMPLE = [
    "Query",
    "Evaluate",
    "PlatynUI.BareMetal.Query",
    "platynui.baremetal.evaluate",
    "Pointer Click",
    "pointer multi click",
    "Pointer Press",
    "Pointer Release",
    "Pointer Move To",
    "Keyboard Type",
    "Keyboard Press",
    "Keyboard Release",
    "PlatynUI.BareMetal.Keyboard Type",
    "keyboard_type",
    "Pointer-Click",
    "Click",
    "Type Text",
    "Set Root",
    "Get Attribute",
    "Take Screenshot",
    "Close Window",
    "Activate Window",
    "Start Process",
    "Process.Run Process",
    "Run",
    "  start process  ",
    "",
]

UNSCOPED_SAMPLE = [
    None,
    123,
    "",
    "   ",
    "//control:Paragraph",
    "  //control:Button",
    "//*",
    "*",
    "descendant::control:Button",
    "Descendant-Or-Self::control:Edit",
    "/app:*[@Name='soffice']//control:Paragraph",
    "/app:*",
    "control:Button[@Name='OK']",
    ".//control:Edit",
    "count(//control:Paragraph)",
    "COUNT(//control:Button)",
    "string(//control:Label)",
    "number(//x)",
    "boolean(//x)",
    "child::control:Frame",
    "(//control:Button)[1]",
    "/x//y",
]

SCREENSHOT_ARGS = [
    ["/artifacts/x.png"],
    ["descriptor=/x.png"],
    ["a_descriptor", "/x.png"],
    ["filename=/x.png"],
    ["EMBED"],
    ["run-{index}.png"],
    ["a_descriptor"],
    ["X.JPEG"],
    ["shot.jpg", "filename=/y.png"],
    ["rect=1,2,3,4", "/x.png"],
    ["filename=EMBED"],
    [],
    [None, "/x.png"],
    ["descriptor=EMBED"],
    ["/x.gif"],
]

DESCRIPTOR_SAMPLE = [
    ("Pointer Click", ["/app:*[@Name='x']//control:Button[@Name='7']"]),
    ("Pointer Click", ["button=left"]),
    ("Pointer Click", ["/app:*//control:Button[@Name='7']"]),
    ("Pointer Click", []),
    ("Pointer Click", ["   "]),
    ("Pointer Click", [123]),
    ("Keyboard Type", ["None", "hello"]),
    ("Keyboard Type", ["${None}", "hello"]),
    ("Keyboard Type", ["", "hello"]),
    ("Keyboard Type", ["  NONE ", "hello"]),
    ("Keyboard Type", ["/app:*[@Name='x']//control:Edit", "hello"]),
    ("Keyboard Press", ["<Ctrl+A>"]),
    ("Close Window", ["/app:*[@Name='x']//control:Frame"]),
    ("Move Window", ["x=5"]),
    ("Query", ["/app:*"]),
    ("Get Attribute", ["/app:*", "Name"]),
    ("PlatynUI.BareMetal.Activate Window", ["/app:*[@Name='x']"]),
    ("Pointer Click", ["[@Name='a=b']"]),
    ("Pointer Click", ["my-arg=1"]),
]

SCOPE_SAMPLE = [
    "/app:*[@Name='X']//control:Button",
    "/app:*[@Name='X']",
    "//control:Button",
    "control:Button",
    "",
    "  /app:*[@Name='Y']//control:Edit  ",
    "/app:*[@Name='Z']/control:Frame",
    "control:Frame//control:Button",
    "/x//y",
]

FLAG_VALUES = ["1", "true", "TRUE", " yes ", "0", "false", "no", "on", "", "warn", " WARN ", "enforce"]


def _calls() -> list[tuple[str, str, list, dict, dict | None]]:
    """(module, function, args, kwargs, os_environ)."""
    out: list[tuple[str, str, list, dict, dict | None]] = []
    for kw in KW_SAMPLE:
        for fn in (
            "is_query_keyword",
            "is_interaction_keyword",
            "is_tree_resolving_keyword",
            "is_launch_keyword",
            "is_screenshot_keyword",
        ):
            out.append((S, fn, [kw], {}, None))
        for fn in ("normalize_keyword", "is_interaction_keyword"):
            out.append((F, fn, [kw], {}, None))
    out.append((F, "normalize_keyword", [None], {}, None))
    for xp in UNSCOPED_SAMPLE:
        out.append((S, "is_unscoped_locator", [xp], {}, None))
    for args in SCREENSHOT_ARGS:
        for kw in ("Take Screenshot", "PlatynUI.BareMetal.Take Screenshot", "Query"):
            out.append((S, "screenshot_request_path", [kw, args], {}, None))
            out.append((S, "screenshot_path_in_descriptor_slot", [kw, args], {}, None))
    for kw in (
        "Query",
        "Evaluate",
        "Set Root",
        "Get Attribute",
        "Pointer Click",
        "Keyboard Type",
        "Take Screenshot",
        "Close Window",
        "Activate Window",
        "Pointer Press",
    ):
        for args in (
            ["/app:*[@Name='x']//control:Window"],
            ["/app:*[@Name='x']//CONTROL:WINDOW"],
            ["/app:*[@Name='x']//control:Frame"],
            ["Name", "/app:*//control:Window"],
            [None],
            [],
        ):
            out.append((S, "control_window_locator", [kw, args], {}, None))
    for kw in ("Keyboard Type", "Pointer Click", "Query", "Pointer Press"):
        for success in (True, False):
            for before, after in ((5, 5), (5, 6), (None, 5), (5, None), ("a", "a")):
                kwargs = {"keyword": kw, "success": success, "state_before": before, "state_after": after}
                out.append((S, "input_effect_hint", [], kwargs, None))
                for vf in (True, False, None):
                    for wr in (False, True):
                        out.append(
                            (S, "steering_confidence", [], {**kwargs, "verified_focus": vf, "wayland_risk": wr}, None)
                        )
    for value in FLAG_VALUES:
        out.append((S, "steering_confidence_mode", [{"ROBOTMCP_PLATYNUI_STEERING_CONFIDENCE": value}], {}, None))
        out.append((F, "focus_disabled_by_env", [{"ROBOTMCP_PLATYNUI_NO_FOCUS": value}], {}, None))
        out.append((F, "highlight_disabled_by_env", [{"ROBOTMCP_PLATYNUI_HIGHLIGHT": value}], {}, None))
        out.append((D, "allow_opt_in", [{ALLOW: value}], {}, None))
        out.append((D, "warn_mode", [{GUARD: value}], {}, None))
        out.append((D, "require_isolated", [{REQ: value}], {}, None))
    for empty in ("steering_confidence_mode", "focus_disabled_by_env", "highlight_disabled_by_env"):
        out.append((S if empty.startswith("steering") else F, empty, [{}], {}, None))
    for fn in ("allow_opt_in", "warn_mode", "require_isolated"):
        out.append((D, fn, [{}], {}, None))
    for kw, args in DESCRIPTOR_SAMPLE:
        out.append((F, "extract_descriptor", [kw, args], {}, None))
    for desc in SCOPE_SAMPLE:
        out.append((F, "app_scope_of", [desc], {}, None))
        out.append((F, "is_unscoped", [desc], {}, None))
    # Launch environment.
    snap_parent = {k: v for k, v in SNAPPY.items() if k not in ("DISPLAY", "WAYLAND_DISPLAY")}
    exe_path = {"PATH": "{EXE_DIR}"}
    for exe in ("gnome-calculator", "mousepad", "/snap/firefox/123/usr/bin/firefox", ""):
        for sanitize in (True, False):
            out.append(
                (
                    L,
                    "build_desktop_launch_env",
                    [exe],
                    {
                        "parent_env": snap_parent,
                        "display_env": {"DISPLAY": ":99", "WAYLAND_DISPLAY": ""},
                        "sanitize": sanitize,
                    },
                    exe_path,
                )
            )
    out.append(
        (
            L,
            "build_desktop_launch_env",
            ["gnome-calculator"],
            {"parent_env": {"LD_LIBRARY_PATH": "/usr/lib", "PATH": "/usr/bin"}, "display_env": {"DISPLAY": ":99"}},
            exe_path,
        )
    )
    out.append(
        (
            L,
            "build_desktop_launch_env",
            ["gnome-calculator"],
            {
                "parent_env": {"WAYLAND_DISPLAY": "wayland-0", "PATH": "/usr/bin"},
                "display_env": {"DISPLAY": ":99", "WAYLAND_DISPLAY": ""},
            },
            exe_path,
        )
    )
    out.append(
        (
            L,
            "build_desktop_launch_env",
            ["gnome-calculator"],
            {
                "parent_env": {
                    "FONTCONFIG_PATH": "/snap/x/fonts: /etc/fonts",
                    "LOCPATH": "/snap/core/locale",
                    "GIO_EXTRA_MODULES": "",
                    "GTK_EXE_PREFIX": "/usr",
                    "FONTCONFIG_FILE": "/snap/x/fonts.conf",
                },
                "display_env": {},
            },
            exe_path,
        )
    )
    out.append(
        (
            L,
            "build_desktop_launch_env",
            ["gnome-calculator"],
            {
                "parent_env": {
                    "GSETTINGS_SCHEMA_DIR": "/var/lib/snapd/schemas::/usr/share/schemas",
                    "LD_PRELOAD": "/usr/lib/libok.so",
                },
                "display_env": None,
            },
            exe_path,
        )
    )
    for args, desktop in (
        (["gnome-calculator", "--new-window"], None),
        (["/usr/bin/gnome-text-editor"], None),
        (["ls", "-la"], None),
        ([], None),
        (["{EXE_DIR}/soffice", "--writer"], True),
        (["{EXE_DIR}/soffice"], None),
        (["{EXE_DIR}/soffice"], False),
        (["bash", "-c", "echo hi"], True),
        (["python3", "s.py"], True),
        (["xdotool", "key", "a"], True),
        (["{EXE_DIR}/xdotool"], True),
        (["env:FOO=bar"], True),
        (["KEY=val"], True),
        (["/nonexistent/path/to/app-xyz"], True),
        (["definitely-not-a-real-binary-xyz"], True),
        (["soffice"], True),
        (["soffice"], None),
        ([123], True),
        ([""], True),
        (["   "], True),
        (["  mousepad  "], True),
    ):
        out.append((L, "is_desktop_gui_launch", [args], {"is_desktop_session": desktop}, exe_path))
    for parent in ({}, {"GTK_A11Y": "1"}, {"GTK_A11Y": ""}, {"GTK_A11Y": "  "}, {"GTK_A11Y": " custom "}):
        out.append((L, "gui_launch_overrides", ["soffice"], {"parent_env": parent}, None))
    for name in ("soffice", "nope-xyz", "{EXE_DIR}/mousepad", "/nonexistent/abs/app", "", 123):
        out.append((L, "resolve_executable", [name], {"parent_env": {"PATH": "{EXE_DIR}"}}, None))
    # Guidance compression.
    for arg in (
        "descriptor: UiNodeDescriptor | None = None",
        "filename: str = platynui-screenshot-{index}.png",
        "name",
        "rect: Rect | None = None",
        "text: str",
        "*args",
        "**kwargs",
        "count: int = 12345678901234",
        "count: int = 1234567890123",
    ):
        out.append((G, "_compress_arg", [arg], {}, None))
    out.append((G, "_compress_signature", ["Get Attribute", ["descriptor: UiNodeDescriptor", "name: str"]], {}, None))
    out.append(
        (
            G,
            "_compress_signature",
            [
                "Take Screenshot",
                [
                    "descriptor: UiNodeDescriptor | None = None",
                    "filename: str = platynui-screenshot-{index}.png",
                    "rect=None",
                ],
            ],
            {},
            None,
        )
    )
    out.append((G, "_compress_signature", ["Get Pointer Position", None], {}, None))
    return out


def record_calls(rec: Recorder) -> None:
    for index, (module, fn, args, kwargs, os_env) in enumerate(_calls()):
        func = getattr(RF_MODULES[module], fn)
        with os_environ(rec.ph.subst(os_env) if os_env is not None else None):
            result = func(*rec.ph.subst(args), **rec.ph.subst(kwargs))
        rec.add(
            "call",
            f"{RFH_MODULE[module]}.{RFH_NAME.get(fn, fn)}#{index}",
            {
                "rf": f"{module}.{fn}",
                "module": RFH_MODULE[module],
                "function": RFH_NAME.get(fn, fn),
                "args": args,
                "kwargs": kwargs,
                "os_environ": os_env,
            },
            result,
        )
    rec.cases.append(
        {
            "id": "locator_crib",
            "kind": "crib",
            "input": {"drop_mcp_tool_lines": ["get_locator_guidance"]},
            "expected": list(dg._LOCATOR_CRIB),
        }
    )


# --- G/H: Wayland warning, origin detection, X11 forcing ---------------------------


def record_wayland(rec: Recorder) -> None:
    for kw in KW_SAMPLE:
        for origin in (True, False):
            with patched(pp, "_WAYLAND_ORIGIN", origin):
                out = sig.wayland_input_warning(kw)
            rec.add("wayland", f"wayland:{kw or '<empty>'}:{origin}", {"keyword": kw, "was_wayland": origin}, out)

    origin_envs = [
        ("x11_plain", {"XDG_SESSION_TYPE": "x11", "DISPLAY": ":0"}),
        ("wayland_type", {"XDG_SESSION_TYPE": "wayland"}),
        ("wayland_type_upper", {"XDG_SESSION_TYPE": " Wayland "}),
        ("wayland_display_only", {"WAYLAND_DISPLAY": "wayland-0"}),
        ("scrubbed_with_socket", {"XDG_SESSION_TYPE": "x11", "XDG_RUNTIME_DIR": "{RT_SOCKET}"}),
        ("scrubbed_without_socket", {"XDG_SESSION_TYPE": "x11", "XDG_RUNTIME_DIR": "{RT_EMPTY}"}),
        ("empty", {}),
        ("tty", {"XDG_SESSION_TYPE": "tty"}),
    ]
    for case_id, env in origin_envs:
        with patched(pp, "_WAYLAND_ORIGIN", None):
            pp._record_session_origin(rec.ph.subst(env))
            out = pp.was_wayland_session()
        rec.add("origin", f"origin:{case_id}", {"env": env}, out)

    x11_cases = [
        (
            "windows_untouched",
            "win32",
            {"XDG_SESSION_TYPE": "wayland", "DISPLAY": ":0", "WAYLAND_DISPLAY": "wayland-0"},
        ),
        ("wayland_forced", "linux", {"XDG_SESSION_TYPE": "wayland", "DISPLAY": ":0", "WAYLAND_DISPLAY": "wayland-0"}),
        ("wayland_no_display", "linux", {"XDG_SESSION_TYPE": "wayland", "WAYLAND_DISPLAY": "wayland-0"}),
        (
            "wayland_keep_1",
            "linux",
            {"XDG_SESSION_TYPE": "wayland", "DISPLAY": ":0", "ROBOTMCP_PLATYNUI_KEEP_WAYLAND": "1"},
        ),
        (
            "wayland_keep_upper_not_honored",
            "linux",
            {"XDG_SESSION_TYPE": "wayland", "DISPLAY": ":0", "ROBOTMCP_PLATYNUI_KEEP_WAYLAND": "TRUE"},
        ),
        ("implicit_wayland", "linux", {"DISPLAY": ":0", "WAYLAND_DISPLAY": "wayland-0"}),
        (
            "x11_with_socket_pinned",
            "linux",
            {"XDG_SESSION_TYPE": "x11", "DISPLAY": ":100", "XDG_RUNTIME_DIR": "{RT_SOCKET}"},
        ),
        (
            "x11_without_socket",
            "linux",
            {"XDG_SESSION_TYPE": "x11", "DISPLAY": ":100", "XDG_RUNTIME_DIR": "{RT_EMPTY}"},
        ),
        (
            "x11_preset_gdk",
            "linux",
            {"XDG_SESSION_TYPE": "x11", "DISPLAY": ":100", "WAYLAND_DISPLAY": "wayland-0", "GDK_BACKEND": "wayland"},
        ),
        (
            "x11_preset_qt",
            "linux",
            {
                "XDG_SESSION_TYPE": "x11",
                "DISPLAY": ":100",
                "WAYLAND_DISPLAY": "wayland-0",
                "QT_QPA_PLATFORM": "wayland",
            },
        ),
        ("unset_type_socket", "linux", {"DISPLAY": ":100", "XDG_RUNTIME_DIR": "{RT_SOCKET}"}),
        ("unset_type_nothing", "linux", {"DISPLAY": ":100"}),
        (
            "tty_type_wayland_display",
            "linux",
            {"XDG_SESSION_TYPE": "tty", "DISPLAY": ":0", "WAYLAND_DISPLAY": "wayland-0"},
        ),
        ("no_display_no_wayland", "linux", {}),
    ]
    for case_id, platform, env in x11_cases:
        work = rec.ph.subst(dict(env))
        with patched(pp, "_WAYLAND_ORIGIN", None), patched(sys, "platform", platform):
            note = pp.ensure_x11_session_env(work)
            origin = pp.was_wayland_session()
        rec.add(
            "x11env",
            f"x11env:{case_id}",
            {"platform": platform, "env": env},
            {"note": note, "env": work, "was_wayland": origin},
        )


# --- I/J: lineage and the focus manager ----------------------------------------------

LINEAGE_CASES = [
    ("identical_pid", 100, 100, None, {}, {}),
    ("wrapper_child", 1002, 1000, 50, {1002: 1001, 1001: 1000, 1000: 500}, {1002: 50, 1000: 50}),
    ("daemonized_same_sid", 992769, 992737, 4242, {992769: 1}, {992769: 4242}),
    ("single_instance_handoff", 992769, 996321, 4242, {992769: 1}, {992769: 4242}),
    ("confirmed_foreign", 7777, 1000, 4242, {7777: 1}, {7777: 9000}),
    ("unreadable_indeterminate", 7777, 1000, 4242, {}, {}),
    ("no_recorded_sid", 7777, 1000, None, {7777: 1}, {7777: 9000}),
    ("hop_limit", 2019, 1999, 4242, {**{i: i - 1 for i in range(2000, 2020)}, 2000: 1}, {2019: 9000}),
    ("cycle_terminates", 10, 99, 4242, {10: 11, 11: 10}, {10: 4242}),
    ("parent_zero_stops", 50, 60, 1, {50: 0}, {50: 2}),
    ("target_sid_unreadable", 50, 60, 7, {50: 1}, {}),
]


def record_lineage(rec: Recorder) -> None:
    for case_id, target, aut, aut_sid, parents, sids in LINEAGE_CASES:
        out = pf.pid_in_aut_lineage(target, aut, aut_sid, _ppid=parents.get, _sid=sids.get)
        rec.add(
            "lineage",
            f"lineage:{case_id}",
            {
                "target": target,
                "aut": aut,
                "aut_sid": aut_sid,
                "ppid": {str(k): v for k, v in parents.items()},
                "sid": {str(k): v for k, v in sids.items()},
            },
            out,
        )


WS = "org.platynui.patterns.WindowSurface"
FOCUSABLE = "org.platynui.patterns.Focusable"
VISIBLE = {"IsVisible": True, "IsInView": True, "Bounds": [10, 10, 200, 100]}
GOOD_WIN = {"attrs": VISIBLE, "patterns": [WS], "surface": {"activate": "ok", "accepts_user_input": True}}
DESK = {"bounds": {"x": 0, "y": 0, "width": 1920, "height": 1080}}
EDIT = "/app:*[@Name='X']//control:Edit"
BUTTON = "/app:*[@Name='X']//control:Button[@Name='OK']"


def _step(keyword: str, args: list, before: str | None = None, **kwargs: Any) -> dict:
    out: dict[str, Any] = {"keyword": keyword, "args": args, "kwargs": kwargs}
    if before:
        out["before"] = before
    return out


def _focus(case_id: str, steps: list, windows: dict | None = None, runtime: dict | None = None, **extra: Any) -> dict:
    return {
        "id": case_id,
        "windows": windows if windows is not None else {"main": GOOD_WIN},
        "runtime": runtime if runtime is not None else {"bring_to_front": "ok", "desktop_info": DESK},
        "steps": steps,
        **extra,
    }


FOCUS_CASES = [
    _focus("non_interaction_keyword", [_step("Query", [BUTTON])]),
    _focus("bypass_focus_false", [_step("Pointer Click", [BUTTON], focus=False)]),
    _focus("bypass_env_no_focus", [_step("Pointer Click", [BUTTON])], env={"ROBOTMCP_PLATYNUI_NO_FOCUS": "1"}),
    _focus("type_at_focus_unverified", [_step("Keyboard Type", ["${None}", "hello"])]),
    _focus("type_at_focus_none_string", [_step("Keyboard Press", ["None", "<Ctrl>"])]),
    _focus("pointer_named_arg_no_descriptor", [_step("Pointer Click", ["button=left"])]),
    _focus(
        "descriptor_unresolved",
        [_step("Pointer Click", [BUTTON])],
        runtime={"bring_to_front": "ok", "evaluate": ["none"]},
    ),
    _focus(
        "descriptor_raises", [_step("Pointer Click", [BUTTON])], runtime={"bring_to_front": "ok", "evaluate": ["raise"]}
    ),
    _focus("bring_to_front_verified", [_step("Pointer Click", [BUTTON])]),
    _focus(
        "bring_to_front_no_wait_ms",
        [_step("Keyboard Type", [EDIT, "hi"])],
        runtime={"bring_to_front": "no_wait_ms", "desktop_info": DESK},
    ),
    _focus(
        "bring_to_front_fails_surface_activate",
        [_step("Pointer Click", [BUTTON])],
        runtime={"bring_to_front": "raise", "desktop_info": DESK},
    ),
    _focus(
        "surface_activate_only",
        [_step("Pointer Click", [BUTTON])],
        windows={"main": {"attrs": VISIBLE, "patterns": [WS], "surface": {"activate": "ok"}}},
        runtime={"desktop_info": DESK},
    ),
    _focus(
        "runtime_focus_tier",
        [_step("Pointer Click", [BUTTON])],
        windows={"main": {"attrs": VISIBLE, "patterns": [FOCUSABLE]}},
        runtime={"bring_to_front": "raise", "focus": "ok", "desktop_info": DESK},
    ),
    _focus(
        "x11_raise_fallback",
        [_step("Pointer Click", [BUTTON])],
        windows={"main": {"attrs": VISIBLE, "patterns": [WS], "surface": "raise"}},
        runtime={"bring_to_front": "raise", "focus": "raise", "desktop_info": DESK},
        x11_raise=True,
    ),
    _focus(
        "nothing_focuses",
        [_step("Pointer Click", [BUTTON])],
        windows={"main": {"attrs": VISIBLE, "patterns": [WS], "surface": None}},
        runtime={"desktop_info": DESK},
        x11_raise=False,
    ),
    _focus(
        "no_focus_patterns",
        [_step("Keyboard Type", [EDIT, "x"])],
        windows={
            "main": {
                "attrs": VISIBLE,
                "patterns": ["org.platynui.patterns.Text"],
                "surface": {"activate": "ok", "accepts_user_input": True},
            }
        },
    ),
    _focus(
        "short_pattern_names",
        [_step("Keyboard Type", [EDIT, "x"])],
        windows={
            "main": {
                "attrs": VISIBLE,
                "patterns": ["WindowSurface"],
                "surface": {"activate": "ok", "accepts_user_input": True},
            }
        },
    ),
    _focus(
        "no_pattern_introspection",
        [_step("Keyboard Type", [EDIT, "x"])],
        windows={"main": {"attrs": VISIBLE, "surface": {"activate": "ok"}}},
    ),
    _focus(
        "supported_patterns_raises",
        [_step("Keyboard Type", [EDIT, "x"])],
        windows={
            "main": {"attrs": VISIBLE, "patterns": "raise", "surface": {"activate": "ok", "accepts_user_input": True}}
        },
    ),
    _focus(
        "supported_patterns_none",
        [_step("Keyboard Type", [EDIT, "x"])],
        windows={
            "main": {"attrs": VISIBLE, "patterns": None, "surface": {"activate": "ok", "accepts_user_input": True}}
        },
    ),
    _focus(
        "accepts_input_false",
        [_step("Keyboard Type", [EDIT, "x"])],
        windows={
            "main": {"attrs": VISIBLE, "patterns": [WS], "surface": {"activate": "ok", "accepts_user_input": False}}
        },
    ),
    _focus(
        "accepts_input_raises",
        [_step("Keyboard Type", [EDIT, "x"])],
        windows={
            "main": {"attrs": VISIBLE, "patterns": [WS], "surface": {"activate": "ok", "accepts_user_input": "raise"}}
        },
    ),
    _focus(
        "already_active",
        [_step("Pointer Click", [BUTTON])],
        windows={"main": {"attrs": {**VISIBLE, "IsActive": True}, "patterns": [WS], "surface": {"activate": "ok"}}},
    ),
    _focus(
        "is_focused_string",
        [_step("Pointer Click", [BUTTON])],
        windows={"main": {"attrs": {**VISIBLE, "IsFocused": "true"}, "patterns": [WS]}},
    ),
    _focus(
        "is_active_false_string",
        [_step("Pointer Click", [BUTTON])],
        windows={
            "main": {
                "attrs": {**VISIBLE, "IsActive": "no"},
                "patterns": [WS],
                "surface": {"activate": "ok", "accepts_user_input": True},
            }
        },
    ),
    _focus(
        "hidden_warns",
        [_step("Pointer Click", [BUTTON])],
        windows={"main": {**GOOD_WIN, "attrs": {**VISIBLE, "IsVisible": False}}},
    ),
    _focus(
        "hidden_fail_fast",
        [_step("Pointer Click", [BUTTON], fail_on_hidden=True)],
        windows={"main": {**GOOD_WIN, "attrs": {**VISIBLE, "IsVisible": False}}},
    ),
    _focus(
        "not_in_view",
        [_step("Pointer Click", [BUTTON])],
        windows={"main": {**GOOD_WIN, "attrs": {**VISIBLE, "IsInView": "false"}}},
    ),
    _focus(
        "zero_size",
        [_step("Pointer Click", [BUTTON])],
        windows={"main": {**GOOD_WIN, "attrs": {"Bounds": [0, 0, 0, 50]}}},
    ),
    _focus(
        "off_screen",
        [_step("Pointer Click", [BUTTON])],
        windows={"main": {**GOOD_WIN, "attrs": {"Bounds": [5000, 5000, 100, 100]}}},
    ),
    _focus(
        "off_screen_no_desktop_info",
        [_step("Pointer Click", [BUTTON])],
        windows={"main": {**GOOD_WIN, "attrs": {"Bounds": [5000, 5000, 100, 100]}}},
        runtime={"bring_to_front": "ok", "desktop_info": None},
    ),
    _focus("no_visibility_attrs", [_step("Pointer Click", [BUTTON])], windows={"main": {**GOOD_WIN, "attrs": {}}}),
    _focus(
        "cross_window_warns",
        [_step("Pointer Click", [BUTTON])],
        windows={"main": GOOD_WIN, "other": {"attrs": {}}},
        runtime={"bring_to_front": "ok", "desktop_info": DESK, "evaluate": ["node:main", "node:other"]},
    ),
    _focus(
        "cross_window_strict_raises",
        [_step("Pointer Click", [BUTTON], strict_scope=True)],
        windows={"main": GOOD_WIN, "other": {"attrs": {}}},
        runtime={"bring_to_front": "ok", "desktop_info": DESK, "evaluate": ["node:main", "node:other"]},
    ),
    _focus("scope_check_off", [_step("Pointer Click", [BUTTON], check_scope=False)]),
    _focus(
        "lineage_foreign_warns",
        [_step("Pointer Click", [BUTTON], aut_pid=1000, aut_sid=4242)],
        windows={"main": {**GOOD_WIN, "attrs": {**VISIBLE, "ProcessId": 7777}}},
        lineage={"verdict": False, "target_sid": 9000},
    ),
    _focus(
        "lineage_related_silent",
        [_step("Pointer Click", [BUTTON], aut_pid=1000, aut_sid=4242)],
        windows={"main": {**GOOD_WIN, "attrs": {**VISIBLE, "ProcessId": 1002}}},
        lineage={"verdict": True, "target_sid": 4242},
    ),
    _focus(
        "lineage_indeterminate_silent",
        [_step("Pointer Click", [BUTTON], aut_pid=1000)],
        windows={"main": {**GOOD_WIN, "attrs": {**VISIBLE, "ProcessId": 7777}}},
        lineage={"verdict": None, "target_sid": None},
    ),
    _focus(
        "lineage_no_window_pid",
        [_step("Pointer Click", [BUTTON], aut_pid=1000, aut_sid=1)],
        lineage={"verdict": False, "target_sid": 9},
    ),
    _focus(
        "highlight_called",
        [_step("Pointer Click", [BUTTON], highlight=True)],
        runtime={"bring_to_front": "ok", "desktop_info": DESK, "highlight": "ok"},
    ),
    _focus(
        "highlight_env_kill_switch",
        [_step("Pointer Click", [BUTTON], highlight=True)],
        runtime={"bring_to_front": "ok", "desktop_info": DESK, "highlight": "ok"},
        env={"ROBOTMCP_PLATYNUI_HIGHLIGHT": "0"},
    ),
    _focus(
        "highlight_no_duration_fallback",
        [_step("Pointer Click", [BUTTON], highlight=True)],
        runtime={"bring_to_front": "ok", "desktop_info": DESK, "highlight": "no_duration"},
    ),
    _focus(
        "highlight_raises_soft",
        [_step("Pointer Click", [BUTTON], highlight=True)],
        runtime={"bring_to_front": "ok", "desktop_info": DESK, "highlight": "raise"},
    ),
    _focus("highlight_absent", [_step("Pointer Click", [BUTTON], highlight=True)]),
    _focus(
        "verified_then_type_at_focus", [_step("Pointer Click", [BUTTON]), _step("Keyboard Type", ["${None}", "hi"])]
    ),
    _focus(
        "x11_then_type_at_focus",
        [_step("Pointer Click", [BUTTON]), _step("Keyboard Type", ["${None}", "hi"])],
        windows={"main": {"attrs": VISIBLE, "patterns": [WS]}},
        runtime={"desktop_info": DESK},
        x11_raise=True,
    ),
    _focus("second_focus_cached", [_step("Pointer Click", [BUTTON]), _step("Pointer Click", [BUTTON])]),
    _focus(
        "invalidate_forces_reactivation",
        [_step("Pointer Click", [BUTTON]), _step("Pointer Click", [BUTTON], before="invalidate")],
    ),
    _focus(
        "reset_forces_reactivation",
        [_step("Pointer Click", [BUTTON]), _step("Pointer Click", [BUTTON], before="reset")],
    ),
    _focus(
        "clear_cache_absent",
        [_step("Pointer Click", [BUTTON])],
        runtime={"bring_to_front": "ok", "desktop_info": DESK, "clear_cache": False},
    ),
    _focus("no_runtime", [_step("Pointer Click", [BUTTON])], no_runtime=True),
]


def _run_focus(mgr: Any, case: dict, ph: fx.Placeholders, calls: list) -> list[dict]:
    results = []
    for step in case["steps"]:
        if step.get("before") == "invalidate":
            mgr.invalidate_focus_cache()
        elif step.get("before") == "reset":
            runtime = mgr._runtime
            mgr.reset()
            mgr._runtime = runtime
        try:
            outcome = mgr.ensure_focused(step["keyword"], list(step["args"]), **step["kwargs"])
            results.append({"outcome": outcome.to_dict(), "raises": None, "verified": mgr.has_verified_focus})
        except Exception as exc:  # FocusError
            results.append(
                {"outcome": None, "raises": f"{type(exc).__name__}: {exc}", "verified": mgr.has_verified_focus}
            )
    return results


def record_focus(rec: Recorder) -> None:
    stub = types.ModuleType("platynui_native")
    stub.WindowSurface = fx.WindowSurfaceType
    for case in FOCUS_CASES:
        runtime, calls = fx.build_focus_fakes(case)
        mgr = pf.PlatynUIFocusManager()
        if case.get("no_runtime"):
            mgr._get_runtime = lambda: None
        else:
            mgr._runtime = runtime
        x11 = bool(case.get("x11_raise", False))
        mgr._x11_raise = lambda _w, _x11=x11, _calls=calls: (_calls.append("x11_raise"), _x11)[1]
        lineage = case.get("lineage") or {}
        verdict, target_sid = lineage.get("verdict"), lineage.get("target_sid")
        with (
            mock.patch.dict(sys.modules, {"platynui_native": stub}),
            os_environ(case.get("env", {})),
            patched(pf, "pid_in_aut_lineage", constant(verdict)),
            patched(pf, "_read_pid_sid", constant(target_sid)),
        ):
            results = _run_focus(mgr, case, rec.ph, calls)
        inputs = {k: v for k, v in case.items() if k != "id"}
        rec.add("focus", f"focus:{case['id']}", inputs, {"steps": results, "calls": calls})


# --- main ------------------------------------------------------------------------------


def provenance() -> dict:
    def git(*args: str) -> str:
        return subprocess.run(["git", "-C", str(RFMCP_ROOT), *args], capture_output=True, text=True).stdout.strip()

    try:
        import tomllib

        version = tomllib.loads((RFMCP_ROOT / "pyproject.toml").read_text())["project"]["version"]
    except Exception:
        version = "unknown"
    same_as_main = (
        subprocess.run(["git", "-C", str(RFMCP_ROOT), "diff", "--quiet", "main", "--", *SOURCE_FILES]).returncode == 0
    )
    return {
        "rf_mcp_version": version,
        "rf_mcp_commit": git("rev-parse", "HEAD"),
        "rf_mcp_main_commit": git("rev-parse", "main"),
        "rf_mcp_sources_identical_to_main": same_as_main,
        "rf_mcp_source_sha256": {
            rel: hashlib.sha256((RFMCP_ROOT / rel).read_bytes()).hexdigest()[:16] for rel in SOURCE_FILES
        },
        "generated": datetime.date.today().isoformat(),
        "python": sys.version.split()[0],
        "generator": "tests/desktop/make_corpus.py",
        "text_renames": [list(p) for p in fx.TEXT_RENAMES],
    }


def main() -> int:
    ph = fx.Placeholders()
    try:
        rec = Recorder(ph)
        record_display(rec)
        record_steps(rec)
        record_calls(rec)
        record_wayland(rec)
        record_lineage(rec)
        record_focus(rec)
    finally:
        ph.close()
    corpus = {"provenance": provenance(), "cases": rec.cases}
    out = HERE / "corpus.json"
    out.write_text(json.dumps(corpus, indent=1, ensure_ascii=False, sort_keys=False) + "\n", encoding="utf-8")
    kinds: dict[str, int] = {}
    for case in rec.cases:
        kinds[case["kind"]] = kinds.get(case["kind"], 0) + 1
    print(f"wrote {out} with {len(rec.cases)} cases: {kinds}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
