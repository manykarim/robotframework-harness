"""Bound-display safety classification for desktop (PlatynUI) sessions.

Vendored from rf-mcp ``src/robotmcp/components/execution/desktop_display_safety.py``
(https://github.com/manykarim/rf-mcp, release 0.36.0, commit c1a18eb; Apache-2.0,
same author). Harness changes: ``ROBOTMCP_*`` -> ``RFH_*`` variable names,
"rf-mcp" -> "rf-harness" in user-facing text, injectable probes
(``wm_probe``, ``ownership_probe``, ``is_windows``) for replay tests, and a pure
:func:`decide_safety` split out of :func:`evaluate_safety`. The decisions are
unchanged; ``tests/desktop`` replays rf-mcp's recorded decisions against them.

A desktop session must never silently drive the user's active desktop. We
classify the bound display as one of:

* ``isolated`` — POSITIVE proof of ownership (an isolation marker recorded by the
  bootstrap names this DISPLAY, corroborated by the PID of its X server). Only
  here is automation allowed without an override.
* ``active``   — an EWMH window manager is present on the bound DISPLAY
  (``_NET_SUPPORTING_WM_CHECK`` resolves to a live window) → the user's live
  session.
* ``unknown``  — everything else, including a bare X server with no marker and
  a probe that could not be completed. Fail closed (refuse).

"No EWMH WM" must NOT be treated as isolated (a non-EWMH real desktop would
false-allow), and the marker takes precedence over the EWMH probe (a nested
display running its own WM is still isolated when the harness owns it).
"""

from __future__ import annotations

import logging
import os
import re
from collections.abc import Callable, Mapping
from typing import Any

from . import _env

logger = logging.getLogger(__name__)

# Env names. The bootstrap records the isolated DISPLAY it provisioned; the
# operator may opt in to running on active/unknown displays; a transition mode
# warns instead of refusing.
ISOLATION_MARKER_ENV = _env.ISOLATED_DISPLAY
# Ownership corroboration: the bootstrap/entrypoint that mints the marker also
# records the PID of the X server (Xvfb/Xephyr/Xorg) it launched for the
# isolated display. The guard verifies that PID is a live X server for the
# claimed display, so a stale or hand-misconfigured marker (e.g. an inherited
# ``:0``) cannot false-allow input.
ISOLATION_XPID_ENV = _env.ISOLATED_XPID
ALLOW_ACTIVE_ENV = _env.ALLOW_ACTIVE_DESKTOP
SAFETY_GUARD_ENV = _env.SAFETY_GUARD  # "warn" => log, don't block
# Strict opt-IN to enforce isolation on Windows. Windows has no
# headless-isolation model (no Xvfb/Xephyr equivalent), so the guard is
# permissive by default there; operators who insist on isolation set this.
REQUIRE_ISOLATED_ENV = _env.REQUIRE_ISOLATED

ISOLATED = "isolated"
ACTIVE = "active"
UNKNOWN = "unknown"
# Windows has exactly one interactive desktop and no X11 isolated-display
# model; the X11/EWMH/marker probes never apply.
WINDOWS = "windows"

# Windows-accurate isolation note — NEVER the Linux nested-X-server recipe.
_WINDOWS_ISOLATION_NOTE = (
    "On Windows there is no headless nested-display isolation model. Desktop "
    "automation drives the active session's desktop. To isolate it, run rf-harness "
    "in a dedicated Windows user session or over RDP to a separate session."
)

WmProbe = Callable[[str], "bool | None"]
OwnershipProbe = Callable[[Mapping[str, str], "str | None"], str]


def _is_windows() -> bool:
    """True on Windows (patchable via ``os.name`` in tests)."""
    return os.name == "nt"


def require_isolated(environ: Mapping[str, str] | None = None) -> bool:
    """Strict opt-in to enforce isolation on Windows."""
    return _env.env_true(REQUIRE_ISOLATED_ENV, environ)


def _bound_display(environ: Mapping[str, str]) -> str | None:
    disp = environ.get("DISPLAY")
    return disp.strip() if disp else None


def _has_isolation_marker(environ: Mapping[str, str], display: str | None) -> bool:
    marker = environ.get(ISOLATION_MARKER_ENV)
    if not marker or not display:
        return False
    # Marker may list one or more displays, comma/space separated. Do NOT use
    # os.pathsep (":") — DISPLAY values themselves contain ":".
    claimed = {d.strip() for d in re.split(r"[,\s]+", marker) if d.strip()}
    return display in claimed


def marker_ownership_status(environ: Mapping[str, str], display: str | None) -> str:
    """Corroborate the isolation marker against a recorded X-server PID.

    Returns one of:
    - ``"verified"`` — ``RFH_PLATYNUI_ISOLATED_XPID`` names a live process
      whose cmdline is an X server bound to the claimed ``display``.
    - ``"invalid"``  — an XPID was provided but does not resolve to such a
      process (stale/misconfigured marker).
    - ``"absent"``   — no XPID provided (legacy marker-only setup) OR ownership
      cannot be determined (no /proc); the caller fails closed.

    Best-effort and never raises.
    """
    if not display:
        return "absent"
    raw = (environ.get(ISOLATION_XPID_ENV) or "").strip()
    if not raw:
        return "absent"
    try:
        pid = int(raw)
        if pid <= 0:
            return "invalid"
    except ValueError:
        return "invalid"
    try:
        with open(f"/proc/{pid}/cmdline", "rb") as fh:
            cmdline = fh.read().decode("utf-8", "replace").lower()
    except FileNotFoundError:
        return "invalid"  # PID recorded by the bootstrap is gone -> not owned
    except OSError:
        return "absent"  # cannot read /proc (permissions / non-Linux) -> unknown
    if not cmdline:
        return "invalid"
    # The display token (e.g. ":99") must appear on the X server's command line,
    # and the binary must look like an X server.
    disp_token = display.strip()
    args = [a for a in cmdline.split("\x00") if a]
    looks_x = any(b in (args[0] if args else cmdline) for b in ("xvfb", "xephyr", "xorg")) or (
        args and args[0].rstrip("0123456789").endswith("/x")
    )
    if looks_x and disp_token in args:
        return "verified"
    return "invalid"


# rf-mcp spelling, kept for traceability.
_marker_ownership_status = marker_ownership_status


def ewmh_wm_present(display: str) -> bool | None:
    """True when an EWMH WM owns the display (_NET_SUPPORTING_WM_CHECK), False
    when provably absent, None when the probe could not be completed.

    PlatynUI's native API exposes no live-WM-on-display signal, so this
    read-only ctypes probe of one root-window property supplies the
    security-relevant active-vs-isolated signal (no tree recursion)."""
    try:
        import ctypes
        import ctypes.util

        libname = ctypes.util.find_library("X11")
        if not libname:
            return None
        x11 = ctypes.CDLL(libname)
        x11.XOpenDisplay.restype = ctypes.c_void_p
        x11.XOpenDisplay.argtypes = [ctypes.c_char_p]
        x11.XDefaultRootWindow.restype = ctypes.c_ulong
        x11.XDefaultRootWindow.argtypes = [ctypes.c_void_p]
        x11.XInternAtom.restype = ctypes.c_ulong
        x11.XInternAtom.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_int]
        x11.XGetWindowProperty.restype = ctypes.c_int
        x11.XGetWindowProperty.argtypes = [
            ctypes.c_void_p,
            ctypes.c_ulong,
            ctypes.c_ulong,
            ctypes.c_long,
            ctypes.c_long,
            ctypes.c_int,
            ctypes.c_ulong,
            ctypes.POINTER(ctypes.c_ulong),
            ctypes.POINTER(ctypes.c_int),
            ctypes.POINTER(ctypes.c_ulong),
            ctypes.POINTER(ctypes.c_ulong),
            ctypes.POINTER(ctypes.POINTER(ctypes.c_ubyte)),
        ]
        x11.XFree.argtypes = [ctypes.c_void_p]
        x11.XCloseDisplay.argtypes = [ctypes.c_void_p]

        dpy = x11.XOpenDisplay(display.encode())
        if not dpy:
            return None
        try:
            atom = x11.XInternAtom(dpy, b"_NET_SUPPORTING_WM_CHECK", True)
            if atom == 0:
                return False  # atom never interned -> no EWMH WM has run
            root = x11.XDefaultRootWindow(dpy)
            actual_type = ctypes.c_ulong()
            actual_format = ctypes.c_int()
            nitems = ctypes.c_ulong()
            bytes_after = ctypes.c_ulong()
            prop = ctypes.POINTER(ctypes.c_ubyte)()
            status = x11.XGetWindowProperty(
                dpy,
                root,
                atom,
                0,
                1,
                False,
                33,  # XA_WINDOW = 33
                ctypes.byref(actual_type),
                ctypes.byref(actual_format),
                ctypes.byref(nitems),
                ctypes.byref(bytes_after),
                ctypes.byref(prop),
            )
            present = status == 0 and bool(prop) and nitems.value >= 1
            if prop:
                x11.XFree(prop)
            return present
        finally:
            x11.XCloseDisplay(dpy)
    except Exception as exc:  # pragma: no cover - env dependent
        logger.debug("EWMH probe failed: %s", exc)
        return None


_ewmh_wm_present = ewmh_wm_present


def classify_bound_display(
    environ: Mapping[str, str] | None = None,
    *,
    wm_probe: WmProbe | None = None,
    ownership_probe: OwnershipProbe | None = None,
    is_windows: bool | None = None,
) -> str:
    """Classify the bound display as isolated / active / unknown (/ windows).

    Positive isolation proof (the corroborated marker) takes precedence over
    the EWMH probe; absence of an EWMH WM is NOT isolation.
    """
    return str(
        classify_bound_display_detailed(
            environ, wm_probe=wm_probe, ownership_probe=ownership_probe, is_windows=is_windows
        )["isolation"]
    )


def classify_bound_display_detailed(
    environ: Mapping[str, str] | None = None,
    *,
    wm_probe: WmProbe | None = None,
    ownership_probe: OwnershipProbe | None = None,
    is_windows: bool | None = None,
) -> dict[str, Any]:
    """Classification plus provenance: ``{display, isolation, isolation_source}``.

    ``isolation_source`` is ``marker`` (corroborated marker), ``ewmh`` (live-WM
    probe), ``none`` (no display / probe inconclusive), ``marker_invalid``,
    ``marker_unverified``, ``marker_over_active_wm`` (marker contradicted by a
    live WM) or ``windows_console``.
    """
    env = os.environ if environ is None else environ
    wm_present = wm_probe if wm_probe is not None else _ewmh_wm_present
    ownership = ownership_probe if ownership_probe is not None else _marker_ownership_status
    windows = _is_windows() if is_windows is None else is_windows
    # Windows: no X11/EWMH/marker model applies — classify before any probe.
    if windows:
        return {"display": None, "isolation": WINDOWS, "isolation_source": "windows_console"}
    display = _bound_display(env)
    if _has_isolation_marker(env, display):
        status = ownership(env, display)
        if status == "verified":
            return {"display": display, "isolation": ISOLATED, "isolation_source": "marker"}
        if status == "invalid":
            # A companion XPID was provided but does not resolve to a live X
            # server for this display -> the marker is stale/misconfigured.
            # Fail closed; name the conflict when a live WM contradicts it.
            wm = wm_present(display)  # type: ignore[arg-type]
            return {
                "display": display,
                "isolation": UNKNOWN,
                "isolation_source": ("marker_over_active_wm" if wm is True else "marker_invalid"),
            }
        # status == "absent": no ownership proof. STRICT fail-closed: a marker
        # alone is not proof of ownership.
        wm = wm_present(display)  # type: ignore[arg-type]
        return {
            "display": display,
            "isolation": UNKNOWN,
            "isolation_source": ("marker_over_active_wm" if wm is True else "marker_unverified"),
        }
    if not display:
        return {"display": None, "isolation": UNKNOWN, "isolation_source": "none"}
    wm = wm_present(display)
    if wm is True:
        return {"display": display, "isolation": ACTIVE, "isolation_source": "ewmh"}
    # wm is False (no WM) or None (probe failed) -> unknown, NOT isolated.
    return {
        "display": display,
        "isolation": UNKNOWN,
        "isolation_source": "ewmh" if wm is False else "none",
    }


def allow_opt_in(environ: Mapping[str, str] | None = None) -> bool:
    return _env.env_true(ALLOW_ACTIVE_ENV, environ)


def warn_mode(environ: Mapping[str, str] | None = None) -> bool:
    return _env.env_get(SAFETY_GUARD_ENV, environ).strip().lower() == "warn"


class DesktopSafetyError(Exception):
    """Raised when the safety guard refuses to drive a non-isolated display."""


def _session_flag(session: Any, name: str) -> bool:
    """Per-session opt-in: rf-mcp's ``platynui_<name>`` attribute or ``<name>``."""
    if session is None:
        return False
    return bool(getattr(session, f"platynui_{name}", False) or getattr(session, name, False))


def decide_safety(
    classification: str,
    *,
    opted_in: bool,
    warn: bool,
    require_isolated_on_windows: bool,
) -> dict[str, Any]:
    """Pure guard decision for a classified display.

    Returns ``{classification, enforcing, allowed, bypassed, reason}`` plus
    ``isolation_recipe`` (non-isolated X11) or ``windows_note`` (Windows).
    """
    if classification == ISOLATED:
        return {
            "classification": classification,
            "enforcing": True,
            "allowed": True,
            "bypassed": False,
            "reason": None,
        }
    if classification == WINDOWS:
        # Windows has no isolated-display model — refusing every keyword (with
        # an impossible Xephyr recipe) would block all Windows automation.
        # Allow by default with an active-desktop warning; a strict opt-in
        # enforces isolation for operators who want it. No Xephyr recipe.
        if require_isolated_on_windows:
            return {
                "classification": classification,
                "enforcing": True,
                "allowed": False,
                "bypassed": False,
                "reason": (
                    f"{REQUIRE_ISOLATED_ENV} is set and this is a Windows active desktop. " + _WINDOWS_ISOLATION_NOTE
                ),
                "windows_note": _WINDOWS_ISOLATION_NOTE,
            }
        return {
            "classification": classification,
            "enforcing": True,
            "allowed": True,
            "bypassed": False,
            "reason": ("PlatynUI will drive the ACTIVE Windows desktop. " + _WINDOWS_ISOLATION_NOTE),
            "windows_note": _WINDOWS_ISOLATION_NOTE,
        }
    reason = (
        f"bound display classified '{classification}': refusing desktop input "
        "to avoid leaking onto the user's active session. Run on an isolated "
        "display (recipe below) — the bypass below is an escape hatch that does "
        "NOT guarantee correct input on a shared active desktop."
    )
    recipe = build_isolation_recipe()
    if opted_in:
        return {
            "classification": classification,
            "enforcing": True,
            "allowed": True,
            "bypassed": True,
            "reason": reason,
            "isolation_recipe": recipe,
        }
    if warn:
        return {
            "classification": classification,
            "enforcing": False,
            "allowed": True,
            "bypassed": False,
            "reason": reason,
            "isolation_recipe": recipe,
        }
    return {
        "classification": classification,
        "enforcing": True,
        "allowed": False,
        "bypassed": False,
        "reason": reason,
        "isolation_recipe": recipe,
    }


def evaluate_safety(
    session: Any = None,
    environ: Mapping[str, str] | None = None,
    *,
    wm_probe: WmProbe | None = None,
    ownership_probe: OwnershipProbe | None = None,
    is_windows: bool | None = None,
) -> dict[str, Any]:
    """Decide whether a desktop operation may proceed on the bound display.

    Same contract as rf-mcp: returns ``{classification, enforcing, allowed,
    bypassed, reason}``. Honors a per-session opt-in attribute
    (``platynui_allow_active_desktop`` / ``allow_active_desktop``) in addition
    to the env opt-in.
    """
    env = os.environ if environ is None else environ
    classification = classify_bound_display(
        env, wm_probe=wm_probe, ownership_probe=ownership_probe, is_windows=is_windows
    )
    return decide_safety(
        classification,
        opted_in=_session_flag(session, "allow_active_desktop") or allow_opt_in(env),
        warn=warn_mode(env),
        require_isolated_on_windows=require_isolated(env),
    )


def build_isolation_recipe() -> dict[str, Any]:
    """An actionable recipe for running desktop automation on an isolated
    display, returned on the active-desktop refuse path.

    The VISIBLE mode (Xephyr nested X server) leads as the recommended
    interactive path: the application renders in a window on the tester's
    screen — every interaction is watchable — while synthetic XTest input
    stays confined to the nested display and cannot leak onto the active
    desktop. Headless Xvfb is the CI alternative.
    """
    return {
        "summary": (
            "Run the desktop automation on an rf-harness-owned nested display: "
            "VISIBLE (Xephyr — recommended for interactive testing; the app "
            "is visible on your screen while input is confined to the nested "
            "display) or headless (Xvfb — CI)."
        ),
        "recommended_mode": "visible",
        "modes": [
            {
                "mode": "visible",
                "recommended": True,
                "description": (
                    "Xephyr nested X server — the app renders as a window on "
                    "your desktop so you can WATCH every interaction; "
                    "keyboard/pointer input stays confined to the nested "
                    "display."
                ),
            },
            {
                "mode": "headless",
                "description": "Xvfb virtual display — nothing rendered (CI default).",
            },
        ],
        "steps": [
            "RECOMMENDED (visible): `scripts/platynui_desktop_bootstrap.sh "
            "--mode visible` — or manually: `Xephyr :100 -screen 1280x1024 &`",
            "Start a minimal EWMH window manager inside the nested display "
            "(e.g. `DISPLAY=:100 openbox &`) — PlatynUI's window activation "
            "(WindowSurface/bring_to_front) needs EWMH; without a WM, focus "
            "verification degrades to a warning.",
            "GTK/Qt backends are pinned to X11 automatically (GDK_BACKEND=x11, "
            "QT_QPA_PLATFORM=xcb) when a host Wayland socket is reachable — "
            "without the pin, apps silently render on the host desktop via "
            "the 'wayland-0' fallback even with WAYLAND_DISPLAY unset.",
            "Export the display for the server process: `export DISPLAY=:100` and unset `WAYLAND_DISPLAY`.",
            "Launch the app under that display (e.g. via `systemd-run --user --setenv=DISPLAY=:100 <app>`).",
            f"Mark the display isolated so the guard allows input: set `{ISOLATION_MARKER_ENV}=:100`.",
            "Headless alternative (CI): `Xvfb :99 -screen 0 1280x1024x24 &` "
            f"then `export DISPLAY=:99` and `{ISOLATION_MARKER_ENV}=:99`.",
        ],
        "verification_commands": [
            "platynui-cli-rs info",
            "platynui-cli-rs window --list",
            "platynui-cli-rs highlight '<xpath>'",
            "platynui-cli-rs snapshot '<xpath>'",
        ],
        "bootstrap_script": "scripts/platynui_desktop_bootstrap.sh --mode visible",
        "marker_env": ISOLATION_MARKER_ENV,
        "bypass_env": ALLOW_ACTIVE_ENV,
        "bypass_note": (
            f"{ALLOW_ACTIVE_ENV}=1 is an ESCAPE HATCH only — input may still "
            "target the wrong window on a shared active desktop, so prefer an "
            "isolated display."
        ),
    }


def render_isolation_recipe(recipe: Mapping[str, Any]) -> str:
    """Plain-text rendering of :func:`build_isolation_recipe` for hook output."""
    lines = [str(recipe.get("summary", ""))]
    for index, step in enumerate(recipe.get("steps", []), start=1):
        lines.append(f"{index}. {step}")
    commands = recipe.get("verification_commands") or []
    if commands:
        lines.append("Verify: " + "; ".join(f"`{c}`" for c in commands))
    note = recipe.get("bypass_note")
    if note:
        lines.append(str(note))
    return "\n".join(line for line in lines if line)
