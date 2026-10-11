"""Window focus + visibility + scope guarantees for PlatynUI desktop steps.

Vendored from rf-mcp ``src/robotmcp/components/execution/platynui_focus.py``
(https://github.com/manykarim/rf-mcp, release 0.36.0, commit c1a18eb; Apache-2.0,
same author). Harness changes: ``ROBOTMCP_*`` -> ``RFH_*``; env readers accept
an ``environ`` mapping; the runtime comes from an injectable provider instead
of rf-mcp's plugin broker; the ``WindowSurface`` pattern type is injectable;
the focus-verifiability ladder is a pure function
(:func:`focus_unverifiable_reason`); the X11 window-list/pid probes used only
for rf-mcp's empty-display diagnostics are not vendored.

PlatynUI pointer/keyboard operations are delivered at *screen coordinates*
via the platform input backend. The accessibility tree can be fully
addressable even when the AUT window is not focused/topmost, and on
overlapping windows the same coordinate belongs to whichever window is
stacked on top. This module makes desktop execution target the
application-under-test (AUT) on purpose:

* resolve the AUT top-level window from any descriptor,
* ensure it is raised + focused before pointer/keyboard dispatch,
* verify a resolved target belongs to the AUT window subtree,
* report window visibility and enforce a precondition.

The focus mechanism is tiered: native WindowSurface activation where a WM is
present, a portable X11 raise fallback when WindowSurface is unavailable (the
WM-less case), and a no-op when the window is already active. All of it
degrades gracefully — the scope/visibility checks are the real guarantee when
focus cannot be asserted.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Callable, Mapping
from typing import Any

from . import _env

logger = logging.getLogger(__name__)

# Per-call argument + env escape hatch.
NO_FOCUS_ENV = _env.NO_FOCUS

# Upstream bring_to_front input-readiness wait budget (ms). Capped so the
# focus gate never stalls an interaction step noticeably.
BRING_TO_FRONT_WAIT_MS = 1500

# Target highlighting via upstream Runtime.highlight(): mark the element
# about to receive input on the (visible) display so a human can see
# exactly where commands go.
HIGHLIGHT_ENV = _env.HIGHLIGHT
HIGHLIGHT_DURATION_MS = 600


def highlight_disabled_by_env(environ: Mapping[str, str] | None = None) -> bool:
    return _env.env_get(HIGHLIGHT_ENV, environ).strip().lower() in {"0", "false", "no"}


# The AUT frame may expose no WindowSurface/Focusable pattern; focus then
# silently falls through and keystrokes vanish. This warning makes
# unverifiable focus explicit.
FOCUS_UNVERIFIABLE_PREFIX = "input focus could not be verified for this target — keystrokes may not land"

# Blind type-at-focus (no descriptor) into an empty display reports robot-level
# "success". When no AUT window focus was ever verified in this session, say so.
UNFOCUSED_TYPING_WARNING = (
    "type-at-focus with no previously verified AUT window focus — "
    "keystrokes may land nowhere; target a descriptor or focus/activate "
    "the AUT window first"
)

# PlatynUI keywords whose FIRST positional argument is a descriptor that an
# operation actuates (pointer + window ops). Keyboard keywords take an
# optional descriptor then text; handled separately.
_DESCRIPTOR_FIRST_KEYWORDS = frozenset(
    {
        "pointer click",
        "pointer multi click",
        "pointer press",
        "pointer release",
        "pointer move to",
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
    }
)
_KEYBOARD_KEYWORDS = frozenset(
    {
        "keyboard type",
        "keyboard press",
        "keyboard release",
    }
)

# Keywords that should trigger focus-before-act (and the active-desktop safety
# guard). Window-management keywords manipulate focus themselves, so they are
# NOT pre-focused.
_INTERACTION_KEYWORDS = frozenset(
    {
        "pointer click",
        "pointer multi click",
        "pointer press",
        "pointer release",
        "pointer move to",
        "keyboard type",
        "keyboard press",
        "keyboard release",
    }
)


def normalize_keyword(keyword: str) -> str:
    """Lowercase, strip library prefix, collapse separators."""
    kw = (keyword or "").strip().lower()
    if "." in kw:
        # Strip any library prefix (e.g. "platynui.baremetal."); RF keyword
        # names contain no dots, so the segment after the last dot is the kw.
        kw = kw.rsplit(".", 1)[-1]
    kw = kw.replace("_", " ").replace("-", " ")
    return " ".join(kw.split())


def focus_disabled_by_env(environ: Mapping[str, str] | None = None) -> bool:
    return _env.env_true(NO_FOCUS_ENV, environ)


def is_interaction_keyword(keyword: str) -> bool:
    return normalize_keyword(keyword) in _INTERACTION_KEYWORDS


def is_keyboard_keyword(keyword: str) -> bool:
    return normalize_keyword(keyword) in _KEYBOARD_KEYWORDS


def extract_descriptor(keyword: str, arguments: list) -> str | None:
    """Return the AUT descriptor a PlatynUI keyword acts on, if any.

    Pointer/window keywords: first positional arg. Keyboard keywords: first
    arg unless it is the None/${None} sentinel (type-at-focus), in which
    case there is no descriptor to resolve.
    """
    if not arguments:
        return None
    kw = normalize_keyword(keyword)
    first = arguments[0]
    if not isinstance(first, str):
        return None
    if kw in _KEYBOARD_KEYWORDS:
        sentinel = first.strip().lower()
        if sentinel in {"", "none", "${none}"}:
            return None
        return first
    if kw in _DESCRIPTOR_FIRST_KEYWORDS:
        if not first.strip():
            return None
        if _looks_like_named_arg(first):
            return None
        return first
    return None


def _looks_like_named_arg(value: str) -> bool:
    """True for ``name=value`` (RF named arg), not for descriptors that
    merely contain ``=`` inside a predicate like ``[@Name='7']``."""
    head = value.split("=", 1)[0]
    if "=" not in value or not head:
        return False
    # A descriptor head contains path/predicate characters; a named arg head
    # is a bare identifier.
    return all(c.isalnum() or c in "_-" for c in head)


def app_scope_of(descriptor: str) -> str | None:
    """Extract the ``/app:*[...]`` prefix of an app-scoped descriptor."""
    if not descriptor:
        return None
    text = descriptor.strip()
    if not text.startswith("/app:"):
        return None
    # /app:*[@Name='X']//control:... -> /app:*[@Name='X']
    marker = text.find("//", 1)
    return text[:marker] if marker > 0 else text


def is_unscoped(descriptor: str) -> bool:
    """True when a desktop descriptor is not rooted at an application."""
    text = (descriptor or "").strip()
    return text.startswith("//") or (not text.startswith("/app:") and "//" in text)


def focus_unverifiable_reason(
    patterns: list | None,
    strategy: str | None,
    input_ready: bool | None,
) -> str | None:
    """Why focus could not be verified for a target, or None when verified.

    Verified means the platform reports the window active, or upstream
    ``accepts_user_input()`` confirmed readiness; anything weaker gets an
    explicit warning so silent keystroke loss cannot recur.
    """
    suffixes = PlatynUIFocusManager._pattern_suffixes(patterns)
    if suffixes is not None and not ({"windowsurface", "focusable"} & suffixes):
        return "no WindowSurface/Focusable pattern"
    if strategy == "x11_raise":
        return "ctypes X11 raise fallback used"
    if strategy in ("already_active", "cached"):
        return None
    if input_ready is True:
        return None
    if suffixes is None:
        return "runtime does not expose pattern introspection"
    if input_ready is False:
        return "window is not accepting user input"
    if strategy is not None:
        return "input readiness could not be confirmed"
    return "no focus mechanism succeeded"


def drop_repeated_unfocused_typing(outcome: FocusOutcome, already_warned: set[str]) -> None:
    """Once-per-session de-dup of :data:`UNFOCUSED_TYPING_WARNING` (rf-mcp does
    this in its executor): the first occurrence is kept and recorded in
    ``already_warned``; later ones are removed from ``outcome.warnings``."""
    if UNFOCUSED_TYPING_WARNING not in outcome.warnings:
        return
    if UNFOCUSED_TYPING_WARNING in already_warned:
        outcome.warnings = [w for w in outcome.warnings if w != UNFOCUSED_TYPING_WARNING]
    else:
        already_warned.add(UNFOCUSED_TYPING_WARNING)


def focus_hints(outcome: FocusOutcome) -> list[dict[str, Any]]:
    """rf-mcp's step-result hints for focus warnings (``platynui_focus_warning``)."""
    return [{"type": "platynui_focus_warning", "message": w} for w in outcome.warnings]


class FocusOutcome:
    """Result of a focus-before-act attempt (carried into step hints)."""

    __test__ = False

    def __init__(self) -> None:
        self.attempted = False
        self.focused = False
        self.bypassed = False
        self.strategy: str | None = None
        self.visible: bool | None = None
        self.in_scope: bool | None = None
        self.warnings: list = []
        self.error: str | None = None
        # Upstream pattern introspection + verified activation.
        self.patterns: list | None = None
        self.input_ready: bool | None = None

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "attempted": self.attempted,
            "focused": self.focused,
        }
        if self.bypassed:
            out["bypassed"] = True
        if self.strategy:
            out["strategy"] = self.strategy
        if self.visible is not None:
            out["visible"] = self.visible
        if self.in_scope is not None:
            out["in_scope"] = self.in_scope
        if self.patterns is not None:
            out["patterns"] = self.patterns
        if self.input_ready is not None:
            out["input_ready"] = self.input_ready
        if self.warnings:
            out["warnings"] = self.warnings
        if self.error:
            out["error"] = self.error
        return out


_SHARED_RUNTIME: Any = None


def default_runtime() -> Any:
    """Process-shared ``platynui_native.Runtime`` (created once, never shut down).

    The PlatynUI platform module is process-global and not re-initializable
    after shutdown, so the harness keeps one runtime for the process. Forces
    the X11 backend first (rf-mcp's broker does the same). Returns None when
    PlatynUI is not installed or cannot bind to the display.
    """
    global _SHARED_RUNTIME
    if _SHARED_RUNTIME is not None:
        return _SHARED_RUNTIME
    try:
        from .launch_env import ensure_x11_session_env

        ensure_x11_session_env()
        import platynui_native as pn  # optional dependency

        _SHARED_RUNTIME = pn.Runtime()
    except Exception as exc:  # pragma: no cover - env dependent
        logger.debug("PlatynUI runtime unavailable: %s", exc)
        _SHARED_RUNTIME = None
    return _SHARED_RUNTIME


class PlatynUIFocusManager:
    """Resolves the AUT window and ensures it is focused/visible/in-scope.

    Talks to a process-shared ``platynui_native`` runtime (injectable via
    ``runtime_provider``; tests may also assign ``_runtime`` directly). One
    instance per live session; caches the last-focused window per app scope to
    avoid focus thrash.
    """

    def __init__(
        self,
        runtime_provider: Callable[[], Any] | None = None,
        window_surface_type: Any = None,
    ) -> None:
        self._runtime = None
        self._runtime_provider = runtime_provider
        self._window_surface_type = window_surface_type
        self._last_focused_scope: str | None = None
        # Verified-activation cache keyed by window runtime_id; invalidated by
        # the call site when the desktop tree is dirty.
        self._focused_window_ids: set = set()
        # Whether ANY AUT window focus has been verifiably established in this
        # manager's lifetime — gates the blind type-at-focus warning.
        self._verified_focus: bool = False

    # -- runtime ---------------------------------------------------------

    def _get_runtime(self) -> Any:
        if getattr(self, "_runtime", None) is not None:
            return self._runtime
        provider = getattr(self, "_runtime_provider", None) or default_runtime
        try:
            self._runtime = provider()
        except Exception as exc:  # pragma: no cover - env dependent
            logger.debug("PlatynUI focus runtime unavailable: %s", exc)
            self._runtime = None
        return self._runtime

    def reset(self) -> None:
        # The runtime is process-shared — drop our reference only; do NOT shut
        # it down (that would break other call sites).
        self._runtime = None
        self._last_focused_scope = None
        self.invalidate_focus_cache()

    def invalidate_focus_cache(self) -> None:
        """Drop the verified-activation cache (e.g. after a desktop launch —
        window identities may have changed)."""
        try:
            self._focused_window_ids.clear()
        except AttributeError:
            self._focused_window_ids = set()

    # -- window resolution ----------------------------------------------

    def resolve_window(self, descriptor: str) -> Any | None:
        """Resolve the AUT top-level window node for a descriptor."""
        runtime = self._get_runtime()
        if runtime is None or not descriptor:
            return None
        # A long-lived Runtime caches the desktop tree; apps launched after it
        # was created are invisible until the cache is cleared.
        clear = getattr(runtime, "clear_cache", None)
        if callable(clear):
            try:
                clear()
            except Exception:
                pass
        try:
            node = runtime.evaluate_single(descriptor)
        except Exception as exc:
            logger.debug("focus: descriptor did not resolve (%s): %s", descriptor, exc)
            return None
        if node is None:
            return None
        return self._top_level(node)

    @staticmethod
    def _top_level(node: Any) -> Any | None:
        for attr in ("top_level_or_self", "top_level_pattern"):
            fn = getattr(node, attr, None)
            if callable(fn):
                try:
                    top = fn()
                    if top is not None:
                        return top
                except Exception:
                    continue
        return node

    # -- visibility ------------------------------------------------------

    def window_visibility(self, window: Any) -> tuple[bool | None, list]:
        """Return (is_visible, warnings) for a resolved window node."""
        warnings: list = []
        if window is None:
            return None, warnings
        is_visible = _attr_bool(window, "IsVisible")
        in_view = _attr_bool(window, "IsInView")
        bounds = _attr_rect(window, "Bounds")
        visible = True
        if is_visible is False:
            visible = False
            warnings.append("window IsVisible=false")
        if in_view is False:
            visible = False
            warnings.append("window IsInView=false")
        if bounds is not None:
            w, h = bounds[2], bounds[3]
            if w <= 0 or h <= 0:
                visible = False
                warnings.append("window has zero size")
            else:
                desktop = self._desktop_bounds()
                if desktop is not None and not _intersects(bounds, desktop):
                    visible = False
                    warnings.append("window is off-screen")
        if is_visible is None and in_view is None and bounds is None:
            return None, warnings
        return visible, warnings

    def _desktop_bounds(self) -> tuple[float, float, float, float] | None:
        runtime = self._get_runtime()
        if runtime is None:
            return None
        try:
            info = runtime.desktop_info()
        except Exception:
            return None
        b = info.get("bounds") if isinstance(info, dict) else None
        if b is None:
            return None
        try:
            if isinstance(b, dict):
                return (
                    float(b.get("x", 0)),
                    float(b.get("y", 0)),
                    float(b.get("width", 0)),
                    float(b.get("height", 0)),
                )
            # Rect-like
            return (float(b.x()), float(b.y()), float(b.width()), float(b.height()))
        except Exception:
            return None

    # -- scope check -----------------------------------------------------

    def target_in_window(self, descriptor: str, window: Any) -> bool | None:
        """True when the resolved target's top-level is the AUT window."""
        runtime = self._get_runtime()
        if runtime is None or window is None or not descriptor:
            return None
        try:
            target = runtime.evaluate_single(descriptor)
        except Exception:
            return None
        if target is None:
            return None
        target_top = self._top_level(target)
        return _same_node(target_top, window)

    # -- focus -----------------------------------------------------------

    def focus_window(self, window: Any, scope: str | None) -> tuple[bool, str | None, bool | None]:
        """Raise + focus the window via upstream-first tiers.

        Returns ``(focused, strategy, input_ready)`` where ``input_ready`` is
        the upstream ``WindowSurface.accepts_user_input()`` verdict (None when
        unavailable).
        """
        if window is None:
            return False, None, None
        # Skip redundant raises when already the active window (thrash).
        if self._is_active(window) is True:
            self._last_focused_scope = scope
            self._verified_focus = True
            return True, "already_active", None
        rid = str(getattr(window, "runtime_id", "") or "")
        cache = getattr(self, "_focused_window_ids", None)
        if rid and cache and rid in cache:
            return True, "cached", None
        runtime = self._get_runtime()
        # Tier 1: upstream bring_to_front — restore + activate + (on new-core
        # runtimes) poll accepts_user_input until ready. wait_ms is dropped for
        # older runtimes.
        if runtime is not None:
            fn = getattr(runtime, "bring_to_front", None)
            if callable(fn):
                try:
                    try:
                        fn(window, wait_ms=BRING_TO_FRONT_WAIT_MS)
                    except TypeError:
                        fn(window)
                    self._last_focused_scope = scope
                    self._remember_focused(rid)
                    return True, "bring_to_front", self._accepts_user_input(window)
                except Exception as exc:
                    logger.debug("focus: runtime.bring_to_front failed: %s", exc)
        # Tier 1b: direct WindowSurface.activate() (no readiness polling).
        ws = self._window_surface(window)
        if ws is not None:
            fn = getattr(ws, "activate", None)
            if callable(fn):
                try:
                    fn()
                    self._last_focused_scope = scope
                    self._remember_focused(rid)
                    return True, "window_surface:activate", self._accepts_user_input(window)
                except Exception as exc:
                    logger.debug("focus: WindowSurface.activate failed: %s", exc)
        # Tier 2: upstream Runtime.focus() (Focusable pattern / grab_focus).
        if runtime is not None:
            ffn = getattr(runtime, "focus", None)
            if callable(ffn):
                try:
                    ffn(window)
                    self._last_focused_scope = scope
                    self._remember_focused(rid)
                    return True, "focus", None
                except Exception as exc:
                    logger.debug("focus: runtime.focus failed: %s", exc)
        # Tier 3: LAST RESORT — portable ctypes X11 raise (WM-less Xvfb). Never
        # silent: ensure_focused pairs this strategy with the
        # focus-unverifiable warning.
        if self._x11_raise(window):
            self._last_focused_scope = scope
            return True, "x11_raise", None
        return False, None, None

    def _remember_focused(self, rid: str) -> None:
        # Every upstream-mechanism success (bring_to_front / WindowSurface /
        # Runtime.focus) counts as verified focus for the blind type-at-focus
        # gate; the ctypes x11_raise fallback does NOT reach here.
        self._verified_focus = True
        if not rid:
            return
        cache = getattr(self, "_focused_window_ids", None)
        if cache is None:
            cache = self._focused_window_ids = set()
        cache.add(rid)

    @property
    def has_verified_focus(self) -> bool:
        return bool(getattr(self, "_verified_focus", False))

    @staticmethod
    def _supported_patterns(window: Any) -> list | None:
        """Upstream pattern introspection: list of advertised pattern names,
        or None when the runtime predates ``supported_patterns()``."""
        fn = getattr(window, "supported_patterns", None)
        if not callable(fn):
            return None
        try:
            patterns = fn()
        except Exception:
            return None
        if patterns is None:
            return None
        try:
            return [str(p) for p in patterns]
        except Exception:
            return None

    @staticmethod
    def _pattern_suffixes(patterns: list | None) -> set | None:
        """Normalize pattern names (short or reverse-DNS) to lowercase
        suffixes, e.g. 'org.platynui.patterns.Focusable' -> 'focusable'."""
        if patterns is None:
            return None
        return {str(p).rsplit(".", 1)[-1].strip().lower() for p in patterns if p}

    def highlight_target(self, descriptor: str, window: Any) -> None:
        """Mark the interaction target on screen via upstream
        ``Runtime.highlight()``. Strictly soft-fail: never raises, never
        blocks the step."""
        runtime = self._get_runtime()
        if runtime is None:
            return
        hl = getattr(runtime, "highlight", None)
        if not callable(hl):
            return
        try:
            node = None
            if descriptor:
                try:
                    node = runtime.evaluate_single(descriptor)
                except Exception:
                    node = None
            if node is None:
                node = window
            rect = _attr(node, "Bounds")
            if rect is None:
                return
            try:
                hl(rect, duration_ms=HIGHLIGHT_DURATION_MS)
            except TypeError:
                hl(rect)
        except Exception as exc:  # pragma: no cover - defensive
            logger.debug("highlight skipped: %s", exc)

    def clear_highlight(self) -> None:
        """Remove any active highlight overlay (call before screenshots so
        evidence images show the app, not the marker)."""
        runtime = self._get_runtime()
        fn = getattr(runtime, "clear_highlight", None) if runtime else None
        if not callable(fn):
            return
        try:
            fn()
        except Exception as exc:  # pragma: no cover - defensive
            logger.debug("clear_highlight skipped: %s", exc)

    def _accepts_user_input(self, window: Any) -> bool | None:
        """Upstream WindowSurface.accepts_user_input() verdict, or None."""
        ws = self._window_surface(window)
        if ws is None:
            return None
        fn = getattr(ws, "accepts_user_input", None)
        if not callable(fn):
            return None
        try:
            val = fn()
        except Exception:
            return None
        if val is None:
            return None
        return bool(val)

    def _resolve_window_surface_type(self) -> Any:
        ws_type = getattr(self, "_window_surface_type", None)
        if ws_type is not None:
            return ws_type
        try:
            import platynui_native as pn  # optional dependency

            return getattr(pn, "WindowSurface", None)
        except Exception:
            return None

    def _window_surface(self, window: Any) -> Any | None:
        """Return the WindowSurface pattern of a window node, or None."""
        getter = getattr(window, "get_pattern", None)
        if not callable(getter):
            return None
        try:
            ws_type = self._resolve_window_surface_type()
            if ws_type is None:
                return None
            return getter(ws_type)
        except Exception:
            return None

    @staticmethod
    def _window_pid(window: Any) -> int | None:
        """ProcessId lives on the app ancestor, not the window node itself."""
        pid = _attr_int(window, "ProcessId")
        if pid is not None:
            return pid
        # Walk ancestors (app:Application carries ProcessId).
        for getter in ("ancestors_including_self", "ancestors"):
            fn = getattr(window, getter, None)
            if callable(fn):
                try:
                    for anc in fn():
                        pid = _attr_int(anc, "ProcessId")
                        if pid is not None:
                            return pid
                except Exception:
                    continue
        # Fallback: walk parent() chain.
        node = window
        for _ in range(8):
            parent_fn = getattr(node, "parent", None)
            if not callable(parent_fn):
                break
            try:
                node = parent_fn()
            except Exception:
                break
            if node is None:
                break
            pid = _attr_int(node, "ProcessId")
            if pid is not None:
                return pid
        return None

    def _is_active(self, window: Any) -> bool | None:
        for attr in ("IsActive", "IsFocused"):
            val = _attr_bool(window, attr)
            if val is not None:
                return val
        return None

    def _x11_raise(self, window: Any) -> bool:
        """Raise + focus the window's X11 toplevel, matched by _NET_WM_PID.

        The portable fallback for WM-less / EWMH-less X servers where the
        PlatynUI WindowSurface activation is unavailable.
        """
        if os.environ.get("DISPLAY") is None:
            return False
        pid = self._window_pid(window)
        if pid is None:
            return False
        return _x11_raise_by_pid(pid)

    # -- orchestration ---------------------------------------------------

    def ensure_focused(
        self,
        keyword: str,
        arguments: list,
        *,
        focus: bool = True,
        check_scope: bool = True,
        strict_scope: bool = False,
        fail_on_hidden: bool = False,
        aut_pid: int | None = None,
        aut_sid: int | None = None,
        highlight: bool = False,
        environ: Mapping[str, str] | None = None,
    ) -> FocusOutcome:
        """Focus-before-act + visibility + scope for one interaction step.

        Returns a FocusOutcome; raises FocusError when a precondition is
        violated under a strict/fail-fast policy. Callers de-dup the
        type-at-focus warning per session with
        :func:`drop_repeated_unfocused_typing`.
        """
        outcome = FocusOutcome()
        if not is_interaction_keyword(keyword):
            return outcome
        if not focus or focus_disabled_by_env(environ):
            outcome.bypassed = True
            return outcome
        descriptor = extract_descriptor(keyword, arguments)
        if descriptor is None:
            # type-at-focus / no positional target — nothing to resolve. Blind
            # typing with NO verified AUT focus this session is the
            # silent-keystroke-loss shape — warn.
            if normalize_keyword(keyword) in _KEYBOARD_KEYWORDS and not self.has_verified_focus:
                outcome.warnings.append(UNFOCUSED_TYPING_WARNING)
            return outcome
        scope = app_scope_of(descriptor) or descriptor
        window = self.resolve_window(descriptor)
        if window is None:
            # Descriptor unresolved here; the real keyword will surface the
            # element-not-found error. Do not block.
            return outcome
        outcome.attempted = True

        # Upstream pattern introspection: what focus mechanisms does the
        # resolved window actually advertise?
        outcome.patterns = self._supported_patterns(window)

        # AUT process-identity scope check by LINEAGE, not bare pid equality.
        # Warn ONLY on a CONFIRMED foreign process.
        if aut_pid is not None:
            target_pid = self._window_pid(window)
            if target_pid is not None:
                related = pid_in_aut_lineage(int(target_pid), int(aut_pid), aut_sid)
                if related is False:
                    target_sid = _read_pid_sid(int(target_pid))
                    outcome.warnings.append(
                        f"resolved target (PID {target_pid}, session "
                        f"{target_sid}) has no lineage relation to the "
                        f"launched AUT (PID {aut_pid}, session {aut_sid}) — "
                        f"commands may be going to a different application"
                    )

        # Visibility precondition.
        visible, vis_warnings = self.window_visibility(window)
        outcome.visible = visible
        outcome.warnings.extend(vis_warnings)
        if visible is False:
            msg = "AUT window is not visible/on-screen: " + ", ".join(vis_warnings)
            if fail_on_hidden:
                outcome.error = msg
                raise FocusError(msg)

        # Scope check.
        if check_scope:
            in_scope = self.target_in_window(descriptor, window)
            outcome.in_scope = in_scope
            if in_scope is False:
                msg = "resolved target is outside the AUT window (cross-window collision): " + descriptor
                outcome.warnings.append(msg)
                if strict_scope:
                    outcome.error = msg
                    raise FocusError(msg)

        # Visible-targeting: mark the element about to receive input before
        # dispatch. Soft-fail.
        if highlight and not highlight_disabled_by_env(environ):
            self.highlight_target(descriptor, window)

        # Focus — upstream-first tiers.
        focused, strategy, input_ready = self.focus_window(window, scope)
        outcome.focused = focused
        outcome.strategy = strategy
        outcome.input_ready = input_ready
        if not focused:
            outcome.warnings.append("could not raise/focus the AUT window")

        reason = focus_unverifiable_reason(outcome.patterns, strategy, input_ready)
        if reason is not None:
            outcome.warnings.append(f"{FOCUS_UNVERIFIABLE_PREFIX} ({reason})")
        return outcome


class FocusError(Exception):
    """Raised when a focus/visibility/scope precondition fails fast."""


# --- attribute helpers ------------------------------------------------------


def _attr(node: Any, name: str) -> Any:
    try:
        return node.attribute(name)
    except Exception:
        return None


def _attr_bool(node: Any, name: str) -> bool | None:
    val = _attr(node, name)
    if isinstance(val, bool):
        return val
    if isinstance(val, str):
        low = val.strip().lower()
        if low in {"true", "1", "yes"}:
            return True
        if low in {"false", "0", "no"}:
            return False
    return None


def _attr_int(node: Any, name: str) -> int | None:
    val = _attr(node, name)
    try:
        return int(val)
    except (TypeError, ValueError):
        return None


def _attr_rect(node: Any, name: str) -> tuple[float, float, float, float] | None:
    val = _attr(node, name)
    if val is None:
        return None
    try:
        return (float(val.x()), float(val.y()), float(val.width()), float(val.height()))
    except Exception:
        pass
    if isinstance(val, dict):
        try:
            return (
                float(val.get("x", 0)),
                float(val.get("y", 0)),
                float(val.get("width", 0)),
                float(val.get("height", 0)),
            )
        except Exception:
            return None
    return None


def _intersects(a: tuple[float, float, float, float], b: tuple[float, float, float, float]) -> bool:
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    return not (ax + aw <= bx or bx + bw <= ax or ay + ah <= by or by + bh <= ay)


def _x11_raise_by_pid(pid: int) -> bool:  # pragma: no cover - needs a live X display
    """Raise + focus the top-level X11 window whose _NET_WM_PID == pid.

    Pure ctypes (no python-xlib / xdotool dependency). Best-effort: returns
    True only when a matching toplevel was found and raised.
    """
    import ctypes
    import ctypes.util

    libname = ctypes.util.find_library("X11")
    if not libname:
        return False
    try:
        x11 = ctypes.CDLL(libname)
    except OSError:
        return False

    # Minimal Xlib signatures.
    x11.XOpenDisplay.restype = ctypes.c_void_p
    x11.XOpenDisplay.argtypes = [ctypes.c_char_p]
    x11.XDefaultRootWindow.restype = ctypes.c_ulong
    x11.XDefaultRootWindow.argtypes = [ctypes.c_void_p]
    x11.XInternAtom.restype = ctypes.c_ulong
    x11.XInternAtom.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_int]
    x11.XQueryTree.restype = ctypes.c_int
    x11.XQueryTree.argtypes = [
        ctypes.c_void_p,
        ctypes.c_ulong,
        ctypes.POINTER(ctypes.c_ulong),
        ctypes.POINTER(ctypes.c_ulong),
        ctypes.POINTER(ctypes.POINTER(ctypes.c_ulong)),
        ctypes.POINTER(ctypes.c_uint),
    ]
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
    x11.XRaiseWindow.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
    x11.XFlush.argtypes = [ctypes.c_void_p]

    display = x11.XOpenDisplay(os.environ["DISPLAY"].encode())
    if not display:
        return False
    try:
        net_wm_pid = x11.XInternAtom(display, b"_NET_WM_PID", False)
        root = x11.XDefaultRootWindow(display)

        def _window_pid(win: int) -> int | None:
            actual_type = ctypes.c_ulong()
            actual_format = ctypes.c_int()
            nitems = ctypes.c_ulong()
            bytes_after = ctypes.c_ulong()
            prop = ctypes.POINTER(ctypes.c_ubyte)()
            status = x11.XGetWindowProperty(
                display,
                win,
                net_wm_pid,
                0,
                1,
                False,
                0,  # AnyPropertyType
                ctypes.byref(actual_type),
                ctypes.byref(actual_format),
                ctypes.byref(nitems),
                ctypes.byref(bytes_after),
                ctypes.byref(prop),
            )
            if status != 0 or not prop or nitems.value == 0:
                if prop:
                    x11.XFree(prop)
                return None
            value = ctypes.cast(prop, ctypes.POINTER(ctypes.c_ulong))[0]
            x11.XFree(prop)
            return int(value)

        def _enumerate(parent: int, depth: int = 0):
            if depth > 3:
                return
            root_r = ctypes.c_ulong()
            parent_r = ctypes.c_ulong()
            children = ctypes.POINTER(ctypes.c_ulong)()
            n = ctypes.c_uint()
            if not x11.XQueryTree(
                display,
                parent,
                ctypes.byref(root_r),
                ctypes.byref(parent_r),
                ctypes.byref(children),
                ctypes.byref(n),
            ):
                return
            try:
                for i in range(n.value):
                    win = children[i]
                    if _window_pid(win) == pid:
                        yield win
                    else:
                        yield from _enumerate(win, depth + 1)
            finally:
                if children:
                    x11.XFree(children)

        match = next(_enumerate(root), None)
        if match is None:
            return False
        x11.XRaiseWindow(display, match)
        x11.XFlush(display)
        return True
    except Exception as exc:
        logger.debug("focus: x11 raise-by-pid failed: %s", exc)
        return False
    finally:
        x11.XCloseDisplay(display)


# --- AUT process lineage -----------------------------------------------------


def _read_pid_ppid(pid: int) -> int | None:
    """Parent pid via /proc/<pid>/status PPid, or None when unreadable."""
    try:
        with open(f"/proc/{pid}/status") as f:
            for line in f:
                if line.startswith("PPid:"):
                    return int(line.split()[1])
    except Exception:
        return None
    return None


def _read_pid_sid(pid: int) -> int | None:
    """Session id of a pid, or None when unreadable/exited."""
    try:
        return os.getsid(pid)
    except Exception:
        return None


def pid_in_aut_lineage(
    target_pid: int,
    aut_pid: int,
    aut_sid: int | None,
    *,
    _ppid: Callable[[int], int | None] | None = None,
    _sid: Callable[[int], int | None] | None = None,
) -> bool | None:
    """Is ``target_pid`` part of the launched AUT's process lineage?

    Three tiers:
    1. pid identity;
    2. the target's parent chain reaches ``aut_pid`` (live wrapper parents);
    3. the target's session id matches ``aut_sid`` — the signal that survives
       daemonization and single-instance handoff.

    Returns True (related), False (CONFIRMED foreign: both signals resolved and
    negative), or None (indeterminate — callers must not warn).
    """
    ppid_of = _ppid if _ppid is not None else _read_pid_ppid
    sid_of = _sid if _sid is not None else _read_pid_sid

    if target_pid == aut_pid:
        return True

    # Tier 2: ancestor walk, bounded; stop at init/kernel.
    node = target_pid
    for _ in range(15):
        parent = ppid_of(node)
        if parent is None:
            break
        if parent == aut_pid:
            return True
        if parent <= 1:
            break
        node = parent

    # Tier 3: session-id match.
    target_sid = sid_of(target_pid)
    if aut_sid is not None and target_sid is not None:
        if target_sid == aut_sid:
            return True
        # Both signals resolved, no relation on any tier -> confirmed foreign.
        return False
    # SID comparison unavailable: indeterminate, never a confirmed-foreign
    # verdict (tier 2 alone can never confirm foreignness).
    return None


def _same_node(a: Any, b: Any) -> bool | None:
    if a is None or b is None:
        return None
    ra, rb = getattr(a, "runtime_id", None), getattr(b, "runtime_id", None)
    if ra is not None and rb is not None:
        return str(ra) == str(rb)
    try:
        return bool(a == b)
    except Exception:
        return None
