"""Parity: replay rf-mcp's recorded desktop guard decisions against the vendored API.

``corpus.json`` was recorded by ``make_corpus.py`` from rf-mcp itself; this file
never imports rf-mcp. Every case must produce the same allow/refuse decision,
the same guard rule and the same guidance (after the documented renames
``ROBOTMCP_`` -> ``RFH_`` and "rf-mcp" -> "rf-harness").

Linux only: the corpus exercises /proc ownership probes, POSIX path lists and a
fake ``Xvfb`` process.
"""

from __future__ import annotations

import importlib
import os
import sys
import types
from contextlib import contextmanager, nullcontext
from typing import Any
from unittest import mock

import desktop_fakes as fx
import pytest

from rf_harness.runtime.desktop import SessionFacts, evaluate_step, guidance, launch_env, probe_context, safety, signals
from rf_harness.runtime.desktop import focus as focus_mod

pytestmark = pytest.mark.skipif(not sys.platform.startswith("linux"), reason="parity corpus is Linux-specific")

CORPUS = fx.load_corpus()
RECIPE = "<isolation_recipe>"
MY_RECIPE = safety.build_isolation_recipe()


def cases_of(kind: str) -> list:
    return [pytest.param(c, id=c["id"]) for c in CORPUS["cases"] if c["kind"] == kind]


def jsonable(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {str(k): jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [jsonable(v) for v in obj]
    if isinstance(obj, (set, frozenset)):
        return sorted(jsonable(v) for v in obj)
    return obj


def strip_recipe(obj: Any) -> Any:
    if isinstance(obj, dict):
        if obj == MY_RECIPE:
            return RECIPE
        return {k: strip_recipe(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [strip_recipe(v) for v in obj]
    return obj


def actual(obj: Any, ph: fx.Placeholders) -> Any:
    return strip_recipe(ph.unsubst(jsonable(obj)))


def expected(case: dict) -> Any:
    return fx.normalize_text(case["expected"])


def harness_input(obj: Any, ph: fx.Placeholders) -> Any:
    return ph.subst(fx.map_env_keys(obj))


@contextmanager
def os_environ(env: dict[str, str]):
    with mock.patch.dict(os.environ, env, clear=True):
        yield


def ownership_probe(value: str | None):
    return (lambda _env, _display: value) if value is not None else None


# --- display classification and the safety decision ---------------------------------


@pytest.mark.parametrize("case", cases_of("classify"))
def test_classify(case, placeholders):
    inp = case["input"]
    env = harness_input(inp["env"], placeholders)
    kwargs = {
        "wm_probe": lambda _d: inp["wm"],
        "ownership_probe": ownership_probe(inp["ownership"]),
        "is_windows": inp["is_windows"],
    }
    out = safety.classify_bound_display_detailed(env, **kwargs)
    assert actual(out, placeholders) == expected(case)
    ctx = probe_context(env, **kwargs)
    assert (ctx.isolation, ctx.isolation_source) == (out["isolation"], out["isolation_source"])


@pytest.mark.parametrize("case", cases_of("ownership"))
def test_marker_ownership(case, placeholders):
    inp = case["input"]
    out = safety.marker_ownership_status(harness_input(inp["env"], placeholders), inp["display"])
    assert out == expected(case)


@pytest.mark.parametrize("case", cases_of("safety"))
def test_evaluate_safety(case, placeholders):
    inp = case["input"]
    session = types.SimpleNamespace(platynui_allow_active_desktop=inp["session_opt_in"])
    out = safety.evaluate_safety(
        session,
        harness_input(inp["env"], placeholders),
        wm_probe=lambda _d: inp["wm"],
        ownership_probe=ownership_probe(inp["ownership"]),
        is_windows=inp["is_windows"],
    )
    assert actual(out, placeholders) == expected(case)


@pytest.mark.parametrize("case", cases_of("recipe"))
def test_isolation_recipe_is_rf_mcp_guidance(case):
    assert MY_RECIPE == expected(case)


# --- the pre-dispatch guard chain ------------------------------------------------------


def _session(facts: dict) -> SessionFacts:
    return SessionFacts(
        desktop_session=facts.get("desktop_session", True),
        allow_active_desktop=facts.get("allow_active_desktop", False),
        allow_unscoped=facts.get("allow_unscoped", False),
        allow_path_descriptor=facts.get("allow_path_descriptor", False),
        allow_control_window=facts.get("allow_control_window", False),
        no_sanitize=facts.get("no_sanitize", False),
        aut_app_name=facts.get("aut_app_name"),
        warned=frozenset(facts.get("warned", [])),
    )


@pytest.mark.parametrize("case", cases_of("step"))
def test_step_decision(case, placeholders):
    inp = case["input"]
    env = harness_input(inp.get("env", {}), placeholders)
    env["RFH_DESKTOP"] = "1"  # parity runs with the harness gate open
    ctx = probe_context(
        env,
        session=_session(inp.get("session", {})),
        platform=inp.get("platform", "linux"),
        is_windows=inp.get("is_windows", False),
        was_wayland=bool(inp.get("was_wayland", False)),
        wm_probe=lambda _d: inp.get("wm"),
        ownership_probe=ownership_probe(inp.get("ownership")),
    )
    decision = evaluate_step(inp["keyword"], placeholders.subst(inp.get("args", [])), ctx)
    exp = expected(case)

    assert decision.applies == exp["applies"]
    assert decision.allowed == exp["allowed"]
    refusal = exp["refusal"]
    if refusal is None:
        assert decision.refusals == ()
        assert decision.reason == ""
    else:
        assert actual(decision.reason, placeholders) == refusal["error"]
        assert actual(list(decision.hints), placeholders) == refusal["hints"]
        assert decision.rule == refusal["hints"][0]["type"]
        assert decision.refusals == (decision.rule,)
        assert decision.guidance.startswith(placeholders.subst(refusal["hints"][0]["message"]))
        if "platynui_safety" in refusal:
            assert decision.safety is not None
            got = {k: decision.safety[k] for k in ("classification", "enforcing")}
            assert got == refusal["platynui_safety"]
    assert actual(decision.safety, placeholders) == exp["safety"]
    assert actual(list(decision.warnings), placeholders) == exp["warnings"]
    assert actual(list(decision.arguments), placeholders) == exp["arguments"]


# --- pure functions ----------------------------------------------------------------------


@pytest.mark.parametrize("case", cases_of("call"))
def test_function_call(case, placeholders):
    inp = case["input"]
    module = importlib.import_module(f"rf_harness.runtime.desktop.{inp['module']}")
    func = getattr(module, inp["function"])
    args = harness_input(inp["args"], placeholders)
    kwargs = harness_input(inp["kwargs"], placeholders)
    env = inp["os_environ"]
    with os_environ(placeholders.subst(env)) if env is not None else nullcontext():
        out = func(*args, **kwargs)
    assert actual(out, placeholders) == expected(case)


@pytest.mark.parametrize("case", cases_of("crib"))
def test_locator_crib(case):
    drop = case["input"]["drop_mcp_tool_lines"]
    rf_crib = [line for line in expected(case) if not any(tok in line for tok in drop)]
    assert list(guidance.LOCATOR_CRIB) == rf_crib


@pytest.mark.parametrize("case", cases_of("wayland"))
def test_wayland_warning(case, placeholders):
    inp = case["input"]
    out = signals.wayland_input_warning(inp["keyword"], was_wayland=inp["was_wayland"])
    assert actual(out, placeholders) == expected(case)


@pytest.mark.parametrize("case", cases_of("origin"))
def test_wayland_origin(case, placeholders, monkeypatch):
    env = harness_input(case["input"]["env"], placeholders)
    assert launch_env.wayland_origin(env) is expected(case)
    monkeypatch.setattr(launch_env, "_WAYLAND_ORIGIN", None)
    launch_env._record_session_origin(env)
    assert launch_env.was_wayland_session() is expected(case)


@pytest.mark.parametrize("case", cases_of("x11env"))
def test_x11_session_env(case, placeholders, monkeypatch):
    inp = case["input"]
    monkeypatch.setattr(launch_env, "_WAYLAND_ORIGIN", None)
    work = harness_input(dict(inp["env"]), placeholders)
    note = launch_env.ensure_x11_session_env(work, platform=inp["platform"])
    out = {"note": note, "env": work, "was_wayland": launch_env.was_wayland_session()}
    assert actual(out, placeholders) == expected(case)


@pytest.mark.parametrize("case", cases_of("lineage"))
def test_aut_lineage(case):
    inp = case["input"]
    ppid = {int(k): v for k, v in inp["ppid"].items()}
    sid = {int(k): v for k, v in inp["sid"].items()}
    out = focus_mod.pid_in_aut_lineage(inp["target"], inp["aut"], inp["aut_sid"], _ppid=ppid.get, _sid=sid.get)
    assert out is expected(case)


# --- focus-before-act ----------------------------------------------------------------------


@pytest.mark.parametrize("case", cases_of("focus"))
def test_focus_manager(case, placeholders, monkeypatch):
    inp = case["input"]
    runtime, calls = fx.build_focus_fakes(inp)
    mgr = focus_mod.PlatynUIFocusManager(window_surface_type=fx.WindowSurfaceType)
    if inp.get("no_runtime"):
        mgr._get_runtime = lambda: None
    else:
        mgr._runtime = runtime
    x11 = bool(inp.get("x11_raise", False))
    mgr._x11_raise = lambda _w: (calls.append("x11_raise"), x11)[1]
    lineage = inp.get("lineage") or {}
    monkeypatch.setattr(focus_mod, "pid_in_aut_lineage", lambda *_a, **_k: lineage.get("verdict"))
    monkeypatch.setattr(focus_mod, "_read_pid_sid", lambda _pid: lineage.get("target_sid"))
    env = fx.map_env_keys(inp.get("env", {}))

    results = []
    for step in inp["steps"]:
        if step.get("before") == "invalidate":
            mgr.invalidate_focus_cache()
        elif step.get("before") == "reset":
            kept = mgr._runtime
            mgr.reset()
            mgr._runtime = kept
        try:
            outcome = mgr.ensure_focused(step["keyword"], list(step["args"]), environ=env, **step["kwargs"])
            results.append({"outcome": outcome.to_dict(), "raises": None, "verified": mgr.has_verified_focus})
        except Exception as exc:
            results.append(
                {"outcome": None, "raises": f"{type(exc).__name__}: {exc}", "verified": mgr.has_verified_focus}
            )
    assert actual({"steps": results, "calls": calls}, placeholders) == expected(case)


# --- corpus integrity ---------------------------------------------------------------------


def test_corpus_covers_every_guard_family():
    kinds: dict[str, int] = {}
    for case in CORPUS["cases"]:
        kinds[case["kind"]] = kinds.get(case["kind"], 0) + 1
    minimum = {
        "classify": 30,
        "ownership": 10,
        "safety": 20,
        "recipe": 1,
        "step": 80,
        "call": 500,
        "crib": 1,
        "wayland": 20,
        "origin": 5,
        "x11env": 10,
        "lineage": 9,
        "focus": 40,
    }
    for kind, count in minimum.items():
        assert kinds.get(kind, 0) >= count, (kind, kinds.get(kind, 0))
    rules = {
        h["type"]
        for c in CORPUS["cases"]
        if c["kind"] == "step" and c["expected"]["refusal"]
        for h in c["expected"]["refusal"]["hints"]
    }
    assert rules == {
        "platynui_active_desktop_guard",
        "screenshot_path_refused",
        "unscoped_desktop_locator",
        "screenshot_signature",
        "control_window_on_linux",
    }
    prov = CORPUS["provenance"]
    assert prov["rf_mcp_version"] and prov["rf_mcp_commit"]


def test_rf_mcp_is_not_imported():
    assert not any(name == "robotmcp" or name.startswith("robotmcp.") for name in sys.modules)
