"""Desktop execution signals: pre-dispatch locator/screenshot guards and the
input-landing (steering-confidence) verdict.

Vendored from rf-mcp ``src/robotmcp/components/execution/desktop_execution_signals.py``
(https://github.com/manykarim/rf-mcp, release 0.36.0, commit c1a18eb; Apache-2.0,
same author). Harness changes: ``ROBOTMCP_*`` -> ``RFH_*``, "rf-mcp" ->
"rf-harness" in user-facing text, and :func:`wayland_input_warning` takes the
Wayland-origin fact as an argument instead of reading rf-mcp's plugin state.
Only the guard-relevant functions are vendored (launch/close liveness,
evidence and visual hints are not; see ``tests/desktop`` for parity).

All functions are PURE decision functions (no I/O), so the wiring stays
best-effort and the contract is unit-testable without a live desktop.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from . import _env

# Keyword (basename, lowercased) sets the signals apply to.
_LAUNCH_KEYWORDS = frozenset({"start process", "run process"})
_INTERACTION_KEYWORDS = frozenset(
    {
        "pointer click",
        "pointer multi click",
        "keyboard type",
        "keyboard press",
        "keyboard release",
        "click",
        "type text",
    }
)

# Desktop keywords that RESOLVE a descriptor against the accessibility tree —
# discovery/assertion reads and the interaction keywords (which resolve a
# locator before acting).
_TREE_RESOLVING_KEYWORDS = frozenset({"query", "get attribute", "set root"} | set(_INTERACTION_KEYWORDS))


def _basename(keyword: str) -> str:
    return (keyword or "").strip().lower().rsplit(".", 1)[-1]


def is_launch_keyword(keyword: str) -> bool:
    return _basename(keyword) in _LAUNCH_KEYWORDS


def is_interaction_keyword(keyword: str) -> bool:
    return _basename(keyword) in _INTERACTION_KEYWORDS


def is_tree_resolving_keyword(keyword: str) -> bool:
    """True for a desktop keyword that resolves a descriptor against the
    accessibility tree (so it must see a fresh tree after a launch)."""
    return _basename(keyword) in _TREE_RESOLVING_KEYWORDS


# --- Unscoped-locator guardrail. A leading // is ABSOLUTE XPath: it ignores
# Set Root/context and re-walks the whole session AT-SPI tree (every desktop
# app), which on a busy desktop takes tens of seconds.

# Keywords whose first string argument is an XPath the guardrail inspects.
_XPATH_KEYWORDS = frozenset({"query", "evaluate"})

# Outer scalar-aggregate wrappers: these return ONE value, not a node set, so
# the count(//...) discovery step the locator guidance recommends stays allowed.
_SCALAR_AGGREGATE_PREFIXES = ("count(", "string(", "number(", "boolean(")


def is_query_keyword(keyword: str) -> bool:
    """True for desktop keywords whose first argument is an XPath the
    unscoped-locator guardrail should inspect (Query / Evaluate)."""
    return _basename(keyword) in _XPATH_KEYWORDS


def is_unscoped_locator(xpath: Any) -> bool:
    """True when an XPath would walk the whole session tree.

    Unscoped: starts with ``//`` or ``descendant-or-self::``, or is a bare
    wildcard walk (``*`` / ``//*``). NOT unscoped (allowed): ``/app:``-anchored
    or any other explicit absolute path, relative locators (``control:``,
    ``item:``, ``.``, an axis like ``child::``), and pure scalar-aggregate
    expressions (``count(...)`` etc.). Conservative — anything ambiguous is
    treated as allowed (fail-open toward running).
    """
    if not isinstance(xpath, str):
        return False
    expr = xpath.strip()
    if not expr:
        return False
    low = expr.lower()
    # Pure scalar-aggregate wrapper -> returns a number/string, not nodes.
    if low.startswith(_SCALAR_AGGREGATE_PREFIXES):
        return False
    if expr.startswith("//"):
        return True
    if low.startswith("descendant-or-self::") or low.startswith("descendant::"):
        return True
    if expr in ("*", "//*"):
        return True
    return False


def wayland_input_warning(keyword: str, *, was_wayland: bool) -> dict[str, Any] | None:
    """Return a warning when a desktop INTERACTION keyword runs on a session
    that originated as Wayland (and was forced to X11): synthetic X11 (XTest)
    input is likely blocked by the Wayland compositor, so a keyword "success"
    may not have reached the application.

    Returns None for non-interaction keywords or non-Wayland sessions.
    """
    if not is_interaction_keyword(keyword):
        return None
    if not was_wayland:
        return None
    return {
        "type": "wayland_x11_input_blocked_risk",
        "message": (
            "This desktop session originated as Wayland; rf-harness injects input "
            "via X11 (XTest), which a Wayland compositor (e.g. mutter) typically "
            "BLOCKS for security. A pointer/keyboard keyword may report success "
            "without the input reaching the application. Read/query operations "
            "(AT-SPI over D-Bus) are unaffected."
        ),
        "remediation": [
            "Run the automation on a real X11 login session (not Wayland), or",
            "use PlatynUI's Wayland input backend (libei/eis) when available.",
        ],
    }


def input_effect_hint(
    *,
    keyword: str,
    success: bool,
    state_before: Any,
    state_after: Any,
) -> dict[str, Any] | None:
    """Return a warning hint when a successful desktop interaction left the
    target's accessible display state unchanged.

    ``state_before``/``state_after`` are opaque comparable snapshots (e.g. a
    ``native:Text.CharacterCount`` value). Returns ``None`` when the keyword is
    not an interaction, the step did not succeed, a snapshot is missing, or the
    state changed.
    """
    if not success or not is_interaction_keyword(keyword):
        return None
    if state_before is None or state_after is None:
        return None
    if state_before != state_after:
        return None
    return {
        "type": "desktop_input_no_effect",
        "message": (
            f"'{keyword}' returned success but the target's accessible display "
            "state did not change. Success is not evidence the application "
            "reacted — check window focus, duplicate application roots, or "
            "whether the click targeted the interactable node."
        ),
    }


# --- Steering-confidence verdict. Composes the landing signals (verified
# focus, input effect, Wayland-drop risk) into ONE machine-parseable verdict,
# so a "success" that never reached the application is caught instead of
# trusted. A `contradicted` verdict fails the step unless the mode is "warn".

_STEERING_CONFIDENCE_ENV = _env.STEERING_CONFIDENCE

SC_CONFIRMED = "confirmed"
SC_UNCONFIRMED = "unconfirmed"
SC_CONTRADICTED = "contradicted"


def steering_confidence_mode(environ: Mapping[str, str] | None = None) -> str:
    """Return "warn" when enforcement is opted down, else "enforce" (default)."""
    return "warn" if _env.env_get(_STEERING_CONFIDENCE_ENV, environ).strip().lower() == "warn" else "enforce"


def steering_confidence(
    *,
    keyword: str,
    success: bool,
    verified_focus: bool | None,
    state_before: Any,
    state_after: Any,
    wayland_risk: bool = False,
) -> dict[str, Any] | None:
    """Compose a steering-confidence verdict for a desktop interaction step.

    Returns ``None`` for non-interaction keywords or a non-success step.
    Otherwise ``{"verdict", "type", "message", "signals"}`` where ``verdict`` is:

    - ``confirmed``    — focus was verified OR the target's accessible state
      changed (positive evidence the input landed).
    - ``contradicted`` — success reported but focus was NOT verified AND the
      state did not change, or a Wayland input-drop risk applies to an
      unverified target.
    - ``unconfirmed``  — no positive or negative evidence.
    """
    if not success or not is_interaction_keyword(keyword):
        return None

    vf = verified_focus is True
    effect_known = state_before is not None and state_after is not None
    effect_observed = effect_known and state_before != state_after
    effect_absent = effect_known and state_before == state_after

    if vf or effect_observed:
        verdict = SC_CONFIRMED
        msg = "Input landing is confirmed " + ("(window focus verified)" if vf else "(target state changed)") + "."
    elif effect_absent or wayland_risk:
        verdict = SC_CONTRADICTED
        why = (
            "the target's accessible state did not change"
            if effect_absent
            else "synthetic X11 input is likely dropped by the Wayland compositor"
        )
        msg = (
            f"'{keyword}' returned success but the input did not demonstrably "
            f"reach the application ({why}, and window focus was not verified). "
            "Re-verify focus (Activate Window on the app-scoped Frame) and retry."
        )
    else:
        verdict = SC_UNCONFIRMED
        msg = (
            f"'{keyword}' succeeded but the effect could not be confirmed "
            "(no readable target state and focus not positively verified)."
        )

    return {
        "type": "desktop_steering_confidence",
        "verdict": verdict,
        "message": msg,
        "signals": {
            "verified_focus": vf,
            "effect_observed": effect_observed,
            "effect_absent": effect_absent,
            "wayland_risk": bool(wayland_risk),
        },
    }


# --- Screenshot signature / Linux control:Window fail-fast guards.

_SCREENSHOT_KEYWORDS = frozenset({"take screenshot"})
_SCREENSHOT_EXTENSIONS = (".png", ".jpg", ".jpeg")


def is_screenshot_keyword(keyword: str) -> bool:
    return _basename(keyword) in _SCREENSHOT_KEYWORDS


def screenshot_request_path(keyword: str, arguments: Any) -> str | None:
    """Extract the requested screenshot file path from the arguments, or None.

    Recognizes ``filename=<path>`` named form and bare path-looking
    positionals (image extension). ``EMBED`` and templated ``{index}``
    filenames yield None (not verifiable without the output dir).
    """
    if not is_screenshot_keyword(keyword):
        return None
    for arg in arguments or []:
        if not isinstance(arg, str):
            continue
        candidate = arg
        if arg.startswith("filename="):
            candidate = arg.split("=", 1)[1]
        if candidate == "EMBED" or "{index}" in candidate:
            return None
        if candidate.lower().endswith(_SCREENSHOT_EXTENSIONS):
            return candidate
    return None


def screenshot_path_in_descriptor_slot(keyword: str, arguments: Any) -> str | None:
    """Return the offending path when a ``Take Screenshot`` DESCRIPTOR slot holds
    a bare image path (the filename-as-descriptor trap), else None.

    PlatynUI ``Take Screenshot(descriptor, filename, rect)`` — a filename-only
    first positional binds to ``descriptor`` and triggers a 30s descriptor
    resolution before ElementNotFound. ``filename=``/``rect=`` named args and a
    correct ``(descriptor, path)`` two-positional call are NOT misuse.
    """
    if not is_screenshot_keyword(keyword):
        return None
    descriptor_val: Any = None
    for arg in arguments or []:
        if isinstance(arg, str) and "=" in arg and not arg.startswith("descriptor="):
            continue  # a named arg (filename=, rect=) — not the descriptor slot
        if isinstance(arg, str) and arg.startswith("descriptor="):
            descriptor_val = arg.split("=", 1)[1]
        else:
            descriptor_val = arg  # first positional -> descriptor slot
        break
    if not isinstance(descriptor_val, str):
        return None  # a real descriptor object (or none) — fine
    if descriptor_val == "EMBED" or "{index}" in descriptor_val:
        return None
    if descriptor_val.lower().endswith(_SCREENSHOT_EXTENSIONS):
        return descriptor_val
    return None


def control_window_locator(keyword: str, arguments: Any) -> str | None:
    """Return the offending locator when a desktop tree-resolving keyword's
    argument uses the ``control:Window`` role, else None.

    On AT-SPI (Linux) windows are ``control:Frame``; ``control:Window`` matches
    nothing and hangs 30s. Platform gating is the caller's job.
    """
    if not (is_tree_resolving_keyword(keyword) or is_query_keyword(keyword)):
        return None
    for arg in arguments or []:
        if isinstance(arg, str) and "control:window" in arg.lower():
            return arg
    return None
