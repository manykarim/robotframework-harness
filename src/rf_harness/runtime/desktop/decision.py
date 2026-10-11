"""Pure decision API for live desktop (PlatynUI) steps.

``evaluate_step(keyword, args, context)`` reproduces the pre-dispatch guard
chain of rf-mcp's ``KeywordExecutor`` (``keyword_executor.py`` in release
0.36.0, commit c1a18eb) without running anything:

1. harness feature gate (``RFH_DESKTOP``) — refuses every PlatynUI keyword and
   desktop GUI launch unless ``RFH_DESKTOP=1``;
2. active-desktop safety guard for pointer/keyboard input
   (``_platynui_safety_guard`` + the inline refusal payload);
3. screenshot path guard (``_screenshot_path_guard``);
4. unscoped-locator guard (``_unscoped_locator_guard``);
5. screenshot descriptor-slot guard (``_screenshot_signature_guard``);
6. Linux ``control:Window`` guard (``_control_window_guard``);
7. focus-before-act plan (executed later by
   :class:`~rf_harness.runtime.desktop.focus.PlatynUIFocusManager`);
8. one-time Wayland input warning;
9. desktop launch hardening (``_maybe_resolve_desktop_executable`` +
   ``_maybe_sanitize_desktop_launch``).

``probe_context()`` gathers the display/session facts once (environment
variables plus one read-only EWMH root-property probe of the bound X display);
``evaluate_step`` itself does no I/O apart from path resolution for screenshot
and launch arguments. A refused step must not be dispatched: no input is sent.
"""

from __future__ import annotations

import logging
import os
import sys
import tempfile
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, field, fields
from types import MappingProxyType
from typing import Any

from . import _env, focus, launch_env, safety, signals

logger = logging.getLogger(__name__)

# The 24 PlatynUI.BareMetal keywords of the new core (lowercase RF names).
PLATYNUI_KEYWORDS = frozenset(
    {
        "set root",
        "query",
        "get attribute",
        "pointer click",
        "pointer multi click",
        "pointer press",
        "pointer release",
        "pointer move to",
        "get pointer position",
        "keyboard type",
        "keyboard press",
        "keyboard release",
        "focus",
        "activate window",
        "maximize window",
        "minimize window",
        "restore window",
        "close window",
        "move window",
        "resize window",
        "move and resize window",
        "bring to front",
        "take screenshot",
        "highlight",
    }
)
# Names PlatynUI shares with other common libraries (Browser: Focus, Get
# Attribute, Take Screenshot; DatabaseLibrary: Query). Without knowing the
# session uses PlatynUI, these are not treated as desktop steps.
AMBIGUOUS_KEYWORDS = frozenset({"focus", "get attribute", "take screenshot", "query"})

DESKTOP_DISABLED = "desktop_disabled"
DESKTOP_DISABLED_MESSAGE = (
    "Desktop (PlatynUI) live steps are disabled in this release until the vendored rf-mcp desktop "
    f"guards pass their parity tests; set {_env.DESKTOP}=1 to opt in. The step was not run and no input was sent."
)

WARNING_TYPES = (
    "unscoped_desktop_locator_allowed",
    "screenshot_path_descriptor_allowed",
    "control_window_allowed",
    "wayland_x11_input_blocked_risk",
)


@dataclass(frozen=True)
class SessionFacts:
    """Per-session facts and opt-ins (rf-mcp's ``platynui_*`` session attributes).

    ``desktop_session``: True when the suite/session uses PlatynUI, False when
    it does not, None when unknown (then only unambiguous PlatynUI keyword
    names count as desktop steps). ``warned`` holds warning types already
    surfaced in this session (one-time warnings are not repeated).
    """

    desktop_session: bool | None = None
    allow_active_desktop: bool = False
    allow_unscoped: bool = False
    allow_path_descriptor: bool = False
    allow_control_window: bool = False
    no_focus: bool = False
    fail_on_hidden: bool = False
    strict_scope: bool = False
    highlight: bool = True
    no_sanitize: bool = False
    aut_pid: int | None = None
    aut_sid: int | None = None
    aut_app_name: str | None = None
    warned: frozenset[str] = frozenset()


@dataclass(frozen=True)
class DesktopContext:
    """Display, platform and opt-in facts a desktop decision depends on."""

    platform: str
    is_windows: bool
    display: str | None
    wayland_display: str | None
    xdg_session_type: str | None
    was_wayland: bool
    isolation: str
    isolation_source: str
    x_server: str | None
    in_container: bool
    desktop_enabled: bool
    allow_active_desktop: bool
    safety_guard_warn: bool
    require_isolated: bool
    allow_unscoped: bool
    allow_path_descriptor: bool
    allow_control_window: bool
    no_focus: bool
    highlight_disabled: bool
    keep_wayland: bool
    screenshot_dir: str
    steering_confidence_mode: str
    session: SessionFacts = field(default_factory=SessionFacts)
    environ: Mapping[str, str] = field(default_factory=lambda: MappingProxyType({}), repr=False, compare=False)

    def to_dict(self) -> dict[str, Any]:
        out = {f.name: getattr(self, f.name) for f in fields(self) if f.name not in ("environ", "session")}
        out["session"] = asdict(self.session)
        out["session"]["warned"] = sorted(self.session.warned)
        return out


@dataclass(frozen=True)
class FocusPlan:
    """What focus-before-act must do before an interaction keyword is sent."""

    required: bool
    bypassed: bool
    descriptor: str | None
    scope: str | None


@dataclass(frozen=True)
class Decision:
    """Outcome of :func:`evaluate_step`.

    ``allowed`` False means the step must not run (no input is sent);
    ``reason`` is the refusal error, ``guidance`` the agent-facing text, and
    ``hints`` the rf-mcp-shaped hint payload (including the isolation recipe).
    ``refusals`` lists every rule that refused (the gate plus the guard that
    would refuse with the gate open). ``warnings`` are one-time warnings to
    surface (record their ``type`` in :attr:`SessionFacts.warned`).
    ``arguments`` are the arguments to dispatch (desktop launches gain ``env:``
    overrides). ``safety`` is the active-desktop guard outcome for
    pointer/keyboard keywords, including the audit flag ``bypassed``.
    """

    allowed: bool
    reason: str = ""
    guidance: str = ""
    rule: str = ""
    applies: bool = True
    refusals: tuple[str, ...] = ()
    hints: tuple[dict[str, Any], ...] = ()
    warnings: tuple[dict[str, Any], ...] = ()
    safety: dict[str, Any] | None = None
    focus: FocusPlan | None = None
    arguments: tuple[Any, ...] = ()
    launch: dict[str, Any] | None = None

    @property
    def warning_types(self) -> tuple[str, ...]:
        return tuple(str(w.get("type")) for w in self.warnings)

    def to_dict(self) -> dict[str, Any]:
        out = asdict(self)
        out["hints"] = list(self.hints)
        out["warnings"] = list(self.warnings)
        out["arguments"] = list(self.arguments)
        out["refusals"] = list(self.refusals)
        return out


def desktop_enabled(environ: Mapping[str, str] | None = None) -> bool:
    """``RFH_DESKTOP == "1"``: live desktop steps are allowed to run (guards still apply)."""
    return _env.desktop_enabled(environ)


def _has_platynui_prefix(keyword: str) -> bool:
    text = (keyword or "").strip().lower()
    return "." in text and "platynui" in text.rsplit(".", 1)[0]


def is_platynui_keyword(keyword: str) -> bool:
    """True for a PlatynUI.BareMetal keyword name (with or without library prefix)."""
    return _has_platynui_prefix(keyword) or focus.normalize_keyword(keyword) in PLATYNUI_KEYWORDS


def is_desktop_step(keyword: str, desktop_session: bool | None) -> bool:
    """Whether the desktop guard chain applies to a step.

    True in a PlatynUI session; outside one, only explicitly prefixed PlatynUI
    keywords; when unknown, also unambiguous PlatynUI keyword names.
    """
    if desktop_session is True:
        return True
    if _has_platynui_prefix(keyword):
        return True
    if desktop_session is False:
        return False
    name = focus.normalize_keyword(keyword)
    return name in PLATYNUI_KEYWORDS and name not in AMBIGUOUS_KEYWORDS


def _x_server_name(xpid: str | None) -> str | None:
    """Informational: basename of the recorded X server's argv[0]."""
    raw = (xpid or "").strip()
    if not raw.isdigit():
        return None
    try:
        with open(f"/proc/{int(raw)}/cmdline", "rb") as fh:
            argv0 = fh.read().split(b"\x00", 1)[0].decode("utf-8", "replace")
    except OSError:
        return None
    return os.path.basename(argv0) or None


def _in_container() -> bool:
    """Informational only: Docker/Podman marker files. Never relaxes a guard."""
    return os.path.exists("/.dockerenv") or os.path.exists("/run/.containerenv")


def probe_context(
    environ: Mapping[str, str] | None = None,
    *,
    session: SessionFacts | None = None,
    platform: str | None = None,
    is_windows: bool | None = None,
    was_wayland: bool | None = None,
    probe_display: bool = True,
    wm_probe: safety.WmProbe | None = None,
    ownership_probe: safety.OwnershipProbe | None = None,
) -> DesktopContext:
    """Gather display/session facts for desktop decisions.

    Side-effect-free: reads environment variables, ``/proc/<xpid>/cmdline`` and
    (when ``probe_display``) one root-window property of the bound X display.
    ``probe_display=False`` skips the X probe; an unproven display then
    classifies as ``unknown`` (fail closed). The keyword-only probes exist for
    replay tests.
    """
    env = dict(os.environ if environ is None else environ)
    windows = (os.name == "nt") if is_windows is None else is_windows
    wm = wm_probe if wm_probe is not None else (safety.ewmh_wm_present if probe_display else (lambda _d: None))
    detail = safety.classify_bound_display_detailed(
        env, wm_probe=wm, ownership_probe=ownership_probe, is_windows=windows
    )
    if was_wayland is None:
        was_wayland = launch_env.wayland_origin(env) or launch_env.was_wayland_session()
    return DesktopContext(
        platform=platform or sys.platform,
        is_windows=windows,
        display=(env.get("DISPLAY") or "").strip() or None,
        wayland_display=env.get("WAYLAND_DISPLAY") or None,
        xdg_session_type=env.get("XDG_SESSION_TYPE") or None,
        was_wayland=bool(was_wayland),
        isolation=str(detail["isolation"]),
        isolation_source=str(detail["isolation_source"]),
        x_server=_x_server_name(env.get(safety.ISOLATION_XPID_ENV)),
        in_container=_in_container(),
        desktop_enabled=_env.desktop_enabled(env),
        allow_active_desktop=safety.allow_opt_in(env),
        safety_guard_warn=safety.warn_mode(env),
        require_isolated=safety.require_isolated(env),
        allow_unscoped=_env.env_true(_env.ALLOW_UNSCOPED, env),
        allow_path_descriptor=_env.env_true(_env.ALLOW_PATH_DESCRIPTOR, env),
        allow_control_window=_env.env_true(_env.ALLOW_CONTROL_WINDOW, env),
        no_focus=focus.focus_disabled_by_env(env),
        highlight_disabled=focus.highlight_disabled_by_env(env),
        keep_wayland=env.get(_env.KEEP_WAYLAND, "").strip() in {"1", "true", "yes"},
        screenshot_dir=_env.env_get(_env.SCREENSHOT_DIR, env).strip(),
        steering_confidence_mode=signals.steering_confidence_mode(env),
        session=session or SessionFacts(),
        environ=MappingProxyType(env),
    )


# --- guard chain (rf-mcp KeywordExecutor pre-dispatch block) -----------------


def _refusal(keyword: str, error: str, hint: dict[str, Any], **extra: Any) -> dict[str, Any]:
    out: dict[str, Any] = {"success": False, "error": error, "keyword": keyword}
    out.update(extra)
    out["hints"] = [hint]
    return out


def _safety_guard(keyword: str, ctx: DesktopContext) -> dict[str, Any] | None:
    """Active-desktop safety outcome for pointer/keyboard keywords, else None."""
    if not focus.is_interaction_keyword(keyword):
        return None
    outcome = safety.decide_safety(
        ctx.isolation,
        opted_in=ctx.session.allow_active_desktop or ctx.allow_active_desktop,
        warn=ctx.safety_guard_warn,
        require_isolated_on_windows=ctx.require_isolated,
    )
    if outcome["bypassed"] or (not outcome["enforcing"]):
        logger.warning(
            "PlatynUI safety guard: %s desktop (%s) — %s",
            "bypassed on" if outcome["bypassed"] else "warn-only on",
            outcome["classification"],
            outcome["reason"],
        )
    elif not outcome["allowed"]:
        logger.warning("PlatynUI safety guard: refused on %s desktop", outcome["classification"])
    elif outcome["classification"] == safety.WINDOWS:
        logger.warning("PlatynUI: driving the ACTIVE Windows desktop — %s", outcome.get("reason") or "")
    return outcome


def _safety_refusal(keyword: str, outcome: Mapping[str, Any]) -> dict[str, Any]:
    hint: dict[str, Any] = {"type": "platynui_active_desktop_guard", "message": outcome["reason"]}
    recipe = outcome.get("isolation_recipe")
    if recipe:
        hint["isolation_recipe"] = recipe
    return _refusal(
        keyword,
        outcome["reason"],
        hint,
        platynui_safety={"classification": outcome["classification"], "enforcing": outcome["enforcing"]},
    )


def _screenshot_allowed_roots(ctx: DesktopContext) -> list[str]:
    roots = [tempfile.gettempdir()]
    if ctx.screenshot_dir:
        roots.append(ctx.screenshot_dir)
    return roots


def _screenshot_path_guard(keyword: str, arguments: Sequence[Any], ctx: DesktopContext) -> dict[str, Any] | None:
    requested = signals.screenshot_request_path(keyword, arguments)
    if not requested or not os.path.isabs(requested):
        return None
    real = os.path.realpath(requested)
    allowed = _screenshot_allowed_roots(ctx)
    for root in allowed:
        root_real = os.path.realpath(root)
        if real == root_real or real.startswith(root_real + os.sep):
            return None
    roots = ", ".join(allowed)
    return _refusal(
        keyword,
        f"screenshot path '{requested}' is outside the allowed roots ({roots})",
        {
            "type": "screenshot_path_refused",
            "message": (
                f"Desktop screenshots may only be written under: {roots}. "
                f"Set {_env.SCREENSHOT_DIR} to allow an additional root."
            ),
        },
    )


def _unscoped_locator_guard(
    keyword: str, arguments: Sequence[Any], ctx: DesktopContext, warnings: list[dict[str, Any]]
) -> dict[str, Any] | None:
    if not signals.is_query_keyword(keyword):
        return None
    args = list(arguments or [])
    if not args or not signals.is_unscoped_locator(args[0]):
        return None
    locator = str(args[0]).strip()
    app = ctx.session.aut_app_name
    rewrite = f"/app:*[@Name='{app}']{locator}" if app else f"/app:*[@Name='<app>']{locator}"
    if ctx.allow_unscoped or ctx.session.allow_unscoped:
        if "unscoped_desktop_locator_allowed" not in ctx.session.warned:
            warnings.append(
                {
                    "type": "unscoped_desktop_locator_allowed",
                    "message": (
                        f"unscoped locator '{locator}' is walking the whole "
                        f"session UI tree ({_env.ALLOW_UNSCOPED} "
                        "opt-in) — this can take tens of seconds on a busy "
                        "desktop. Scope to /app:*[@Name='X']//… when possible."
                    ),
                }
            )
        return None
    return _refusal(
        keyword,
        (
            f"unscoped desktop locator '{locator}' would walk the whole "
            "session UI tree (every desktop application) and can take tens "
            "of seconds — refused before dispatch"
        ),
        {
            "type": "unscoped_desktop_locator",
            "message": (
                "NEVER start a desktop locator with // — it is absolute "
                "XPath and ignores Set Root, re-walking every application "
                "on the session AT-SPI bus. Scope to the application "
                f"instead, e.g. '{rewrite}'. To size a subtree first, "
                "count() is allowed (e.g. count(//control:Button)). "
                f"Set {_env.ALLOW_UNSCOPED}=1 only for a "
                "deliberate desktop-wide search."
            ),
        },
    )


def _screenshot_signature_guard(
    keyword: str, arguments: Sequence[Any], ctx: DesktopContext, warnings: list[dict[str, Any]]
) -> dict[str, Any] | None:
    path = signals.screenshot_path_in_descriptor_slot(keyword, arguments)
    if path is None:
        return None
    if ctx.allow_path_descriptor or ctx.session.allow_path_descriptor:
        if "screenshot_path_descriptor_allowed" not in ctx.session.warned:
            warnings.append(
                {
                    "type": "screenshot_path_descriptor_allowed",
                    "message": (
                        f"'{path}' sits in the Take Screenshot DESCRIPTOR slot "
                        "(ALLOW_PATH_DESCRIPTOR opt-in); if it is a filename, "
                        "pass filename= instead."
                    ),
                }
            )
        return None
    return _refusal(
        keyword,
        (
            f"Take Screenshot received the path '{path}' in its DESCRIPTOR slot "
            "(first positional) — it resolves as a UI node and hangs ~30s "
            "before failing. Refused before dispatch."
        ),
        {
            "type": "screenshot_signature",
            "message": (
                "Take Screenshot signature is (descriptor, filename, rect). "
                f"For the whole desktop:  Take Screenshot  filename={path} . "
                f"For one element:  Take Screenshot  <descriptor>  {path} . "
                f"Set {_env.ALLOW_PATH_DESCRIPTOR}=1 to bypass."
            ),
        },
    )


def _control_window_guard(
    keyword: str, arguments: Sequence[Any], ctx: DesktopContext, warnings: list[dict[str, Any]]
) -> dict[str, Any] | None:
    if ctx.platform != "linux":
        return None
    locator = signals.control_window_locator(keyword, arguments)
    if locator is None:
        return None
    if ctx.allow_control_window or ctx.session.allow_control_window:
        if "control_window_allowed" not in ctx.session.warned:
            warnings.append(
                {
                    "type": "control_window_allowed",
                    "message": (
                        f"'{locator}' uses control:Window on Linux "
                        "(ALLOW_CONTROL_WINDOW opt-in); AT-SPI windows are "
                        "control:Frame."
                    ),
                }
            )
        return None
    rewrite = locator.replace("control:Window", "control:Frame").replace("control:window", "control:Frame")
    return _refusal(
        keyword,
        (
            f"desktop locator '{locator}' uses control:Window, which matches "
            "nothing on Linux AT-SPI (windows are control:Frame) and hangs "
            "~30s — refused before dispatch."
        ),
        {
            "type": "control_window_on_linux",
            "message": (
                "On Linux AT-SPI, application windows are control:Frame, not "
                f"control:Window. Use '{rewrite}'. Set "
                f"{_env.ALLOW_CONTROL_WINDOW}=1 to bypass."
            ),
        },
    )


def _focus_plan(keyword: str, arguments: Sequence[Any], ctx: DesktopContext) -> FocusPlan | None:
    if not focus.is_interaction_keyword(keyword):
        return None
    bypassed = ctx.no_focus or ctx.session.no_focus
    descriptor = focus.extract_descriptor(keyword, list(arguments))
    scope = (focus.app_scope_of(descriptor) or descriptor) if descriptor else None
    return FocusPlan(required=not bypassed, bypassed=bypassed, descriptor=descriptor, scope=scope)


def _guidance(hints: Sequence[Mapping[str, Any]]) -> str:
    parts = []
    for hint in hints:
        parts.append(str(hint.get("message", "")))
        recipe = hint.get("isolation_recipe")
        if recipe:
            parts.append(safety.render_isolation_recipe(recipe))
    return "\n\n".join(p for p in parts if p)


def _gated(keyword: str, arguments: Sequence[Any], ctx: DesktopContext) -> bool:
    """Steps the RFH_DESKTOP gate refuses: PlatynUI keywords and desktop GUI launches."""
    if is_platynui_keyword(keyword):
        return True
    if signals.is_launch_keyword(keyword):
        binary = launch_env.is_desktop_gui_launch(list(arguments), is_desktop_session=True, environ=ctx.environ)
        return binary is not None
    return False


def evaluate_step(
    keyword: str,
    args: Sequence[Any] = (),
    context: DesktopContext | None = None,
    *,
    environ: Mapping[str, str] | None = None,
    session: SessionFacts | None = None,
) -> Decision:
    """Decide whether a live step may run, with rf-mcp's desktop guidance.

    Non-desktop steps return ``Decision(allowed=True, applies=False)`` without
    probing anything. Without a ``context`` one is probed lazily (only for
    desktop steps) from ``environ``/``session``.
    """
    arguments = list(args or [])
    facts = context.session if context is not None else (session or SessionFacts())
    if not is_desktop_step(keyword, facts.desktop_session):
        return Decision(allowed=True, applies=False, arguments=tuple(arguments))
    ctx = context if context is not None else probe_context(environ, session=facts)

    warnings: list[dict[str, Any]] = []
    refusal: dict[str, Any] | None = None
    outcome = _safety_guard(keyword, ctx)
    if outcome is not None and not outcome["allowed"]:
        refusal = _safety_refusal(keyword, outcome)
    if refusal is None:
        for guard in (
            lambda: _screenshot_path_guard(keyword, arguments, ctx),
            lambda: _unscoped_locator_guard(keyword, arguments, ctx, warnings),
            lambda: _screenshot_signature_guard(keyword, arguments, ctx, warnings),
            lambda: _control_window_guard(keyword, arguments, ctx, warnings),
        ):
            refusal = guard()
            if refusal is not None:
                break

    safety_info = None
    if outcome is not None:
        safety_info = {k: outcome.get(k) for k in ("classification", "enforcing", "allowed", "bypassed", "reason")}

    gated = not ctx.desktop_enabled and _gated(keyword, arguments, ctx)
    if gated or refusal is not None:
        hints: list[dict[str, Any]] = []
        refusals: list[str] = []
        if gated:
            hints.append({"type": DESKTOP_DISABLED, "message": DESKTOP_DISABLED_MESSAGE})
            refusals.append(DESKTOP_DISABLED)
        if refusal is not None:
            hints.extend(refusal["hints"])
            refusals.append(str(refusal["hints"][0]["type"]))
        return Decision(
            allowed=False,
            reason=DESKTOP_DISABLED_MESSAGE if gated else str(refusal["error"]),  # type: ignore[index]
            guidance=_guidance(hints),
            rule=refusals[0],
            refusals=tuple(refusals),
            hints=tuple(hints),
            safety=safety_info,
            arguments=tuple(arguments),
        )

    if signals.is_interaction_keyword(keyword) and "wayland_x11_input_blocked_risk" not in ctx.session.warned:
        wayland = signals.wayland_input_warning(keyword, was_wayland=ctx.was_wayland)
        if wayland:
            warnings.append(wayland)

    dispatched = launch_env.resolve_launch_executable(keyword, arguments, desktop_session=True, environ=ctx.environ)
    dispatched, launch = launch_env.sanitize_launch_arguments(
        keyword, dispatched, desktop_session=True, environ=ctx.environ, no_sanitize=ctx.session.no_sanitize
    )
    return Decision(
        allowed=True,
        warnings=tuple(warnings),
        safety=safety_info,
        focus=_focus_plan(keyword, arguments, ctx),
        arguments=tuple(dispatched),
        launch=launch,
    )
