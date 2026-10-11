"""RFH_* environment access for the desktop guards (temporary local helper).

Every desktop setting is read through :func:`env_get`, so moving the registry
into ``rf_harness.config`` later only changes this module. The truthiness
rules are deliberately NOT ``rf_harness.config.get_bool``: each guard keeps the
exact parsing rf-mcp uses (``{"1", "true", "yes"}`` for opt-ins, ``== "warn"``
for warn modes, ``{"0", "false", "no"}`` for the highlight kill switch), so the
parity tests stay meaningful.

rf-mcp reads ``ROBOTMCP_*`` variables; the harness reads the same settings
under the ``RFH_`` prefix (see :data:`RFMCP_ENV_MAP`). The old names are not
read: an rf-mcp opt-in must never silently relax a harness guard.
"""

from __future__ import annotations

import os
from collections.abc import Mapping

DESKTOP = "RFH_DESKTOP"
ISOLATED_DISPLAY = "RFH_PLATYNUI_ISOLATED_DISPLAY"
ISOLATED_XPID = "RFH_PLATYNUI_ISOLATED_XPID"
ALLOW_ACTIVE_DESKTOP = "RFH_PLATYNUI_ALLOW_ACTIVE_DESKTOP"
SAFETY_GUARD = "RFH_PLATYNUI_SAFETY_GUARD"
REQUIRE_ISOLATED = "RFH_PLATYNUI_REQUIRE_ISOLATED"
ALLOW_UNSCOPED = "RFH_PLATYNUI_ALLOW_UNSCOPED"
ALLOW_PATH_DESCRIPTOR = "RFH_PLATYNUI_ALLOW_PATH_DESCRIPTOR"
ALLOW_CONTROL_WINDOW = "RFH_PLATYNUI_ALLOW_CONTROL_WINDOW"
NO_FOCUS = "RFH_PLATYNUI_NO_FOCUS"
HIGHLIGHT = "RFH_PLATYNUI_HIGHLIGHT"
KEEP_WAYLAND = "RFH_PLATYNUI_KEEP_WAYLAND"
STEERING_CONFIDENCE = "RFH_PLATYNUI_STEERING_CONFIDENCE"
SCREENSHOT_DIR = "RFH_SCREENSHOT_DIR"

# name -> (default, doc). Defaults have the same meaning as "unset" in rf-mcp.
ENV_VARIABLES: dict[str, tuple[str, str]] = {
    DESKTOP: (
        "0",
        "Set to 1 to allow live desktop (PlatynUI) steps. Off by default until the vendored rf-mcp desktop "
        "guards pass their parity tests; even when on, every safety, isolation and focus guard still applies.",
    ),
    ISOLATED_DISPLAY: (
        "",
        "Isolation marker: the X DISPLAY(s) (comma/space separated) the harness may drive, for example ':99'. "
        "Only counts when RFH_PLATYNUI_ISOLATED_XPID names the live X server for that display.",
    ),
    ISOLATED_XPID: (
        "",
        "PID of the Xvfb/Xephyr/Xorg server that owns the isolated display. Corroborates the isolation marker; "
        "without it the display is classified 'unknown' and desktop input is refused.",
    ),
    ALLOW_ACTIVE_DESKTOP: (
        "0",
        "Escape hatch: 1 allows desktop input on an 'active' or 'unknown' display (audited). Input may still "
        "target the wrong window on a shared desktop; prefer an isolated display.",
    ),
    SAFETY_GUARD: (
        "enforce",
        "'warn' logs instead of refusing desktop input on a non-isolated display (transition mode).",
    ),
    REQUIRE_ISOLATED: (
        "0",
        "Windows only: 1 refuses desktop input on the active Windows desktop (there is no nested-display model).",
    ),
    ALLOW_UNSCOPED: (
        "0",
        "1 allows //-rooted desktop Query/Evaluate locators (whole-desktop walks) with a one-time warning.",
    ),
    ALLOW_PATH_DESCRIPTOR: (
        "0",
        "1 allows an image path in the Take Screenshot descriptor slot with a one-time warning.",
    ),
    ALLOW_CONTROL_WINDOW: (
        "0",
        "1 allows control:Window locators on Linux (AT-SPI windows are control:Frame) with a one-time warning.",
    ),
    NO_FOCUS: (
        "0",
        "1 disables focus-before-act for desktop pointer/keyboard steps (the step is marked focus-bypassed).",
    ),
    HIGHLIGHT: (
        "1",
        "0 disables highlighting the target element before desktop input.",
    ),
    KEEP_WAYLAND: (
        "0",
        "1 keeps the native Wayland backend instead of forcing XDG_SESSION_TYPE=x11 before PlatynUI starts.",
    ),
    STEERING_CONFIDENCE: (
        "enforce",
        "'warn' downgrades a 'contradicted' steering-confidence verdict from a step failure to a warning.",
    ),
    SCREENSHOT_DIR: (
        "",
        "Extra directory desktop screenshots may be written to (the system temp dir is always allowed).",
    ),
}

# rf-mcp name -> harness name (documentation and parity-test input mapping).
RFMCP_ENV_MAP: dict[str, str] = {
    "ROBOTMCP_PLATYNUI_ISOLATED_DISPLAY": ISOLATED_DISPLAY,
    "ROBOTMCP_PLATYNUI_ISOLATED_XPID": ISOLATED_XPID,
    "ROBOTMCP_PLATYNUI_ALLOW_ACTIVE_DESKTOP": ALLOW_ACTIVE_DESKTOP,
    "ROBOTMCP_PLATYNUI_SAFETY_GUARD": SAFETY_GUARD,
    "ROBOTMCP_PLATYNUI_REQUIRE_ISOLATED": REQUIRE_ISOLATED,
    "ROBOTMCP_PLATYNUI_ALLOW_UNSCOPED": ALLOW_UNSCOPED,
    "ROBOTMCP_PLATYNUI_ALLOW_PATH_DESCRIPTOR": ALLOW_PATH_DESCRIPTOR,
    "ROBOTMCP_PLATYNUI_ALLOW_CONTROL_WINDOW": ALLOW_CONTROL_WINDOW,
    "ROBOTMCP_PLATYNUI_NO_FOCUS": NO_FOCUS,
    "ROBOTMCP_PLATYNUI_HIGHLIGHT": HIGHLIGHT,
    "ROBOTMCP_PLATYNUI_KEEP_WAYLAND": KEEP_WAYLAND,
    "ROBOTMCP_PLATYNUI_STEERING_CONFIDENCE": STEERING_CONFIDENCE,
    "ROBOTMCP_SCREENSHOT_DIR": SCREENSHOT_DIR,
}

_TRUE_VALUES = frozenset({"1", "true", "yes"})


def env_get(name: str, environ: Mapping[str, str] | None = None) -> str:
    """Raw value of a registered RFH_* variable (its default when unset)."""
    if name not in ENV_VARIABLES:
        raise KeyError(f"unregistered desktop variable {name}; add it to rf_harness.runtime.desktop._env")
    env = os.environ if environ is None else environ
    return env.get(name, ENV_VARIABLES[name][0])


def env_true(name: str, environ: Mapping[str, str] | None = None) -> bool:
    """rf-mcp opt-in truthiness: ``value.strip().lower() in {"1", "true", "yes"}``."""
    return env_get(name, environ).strip().lower() in _TRUE_VALUES


def desktop_enabled(environ: Mapping[str, str] | None = None) -> bool:
    """Feature gate for live desktop steps: ``RFH_DESKTOP == "1"``."""
    return env_get(DESKTOP, environ).strip() == "1"
