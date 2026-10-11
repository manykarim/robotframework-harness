"""Desktop launch-environment hardening: snap sanitization, GUI-launch
accessibility/backend overlay, X11 backend forcing and Wayland-origin detection.

Vendored from rf-mcp (https://github.com/manykarim/rf-mcp, release 0.36.0,
commit c1a18eb; Apache-2.0, same author):

* ``src/robotmcp/components/execution/desktop_launch_env.py`` (verbatim logic);
* ``KeywordExecutor._maybe_resolve_desktop_executable`` and
  ``KeywordExecutor._maybe_sanitize_desktop_launch`` from
  ``keyword_executor.py``, as pure functions taking an ``environ`` mapping
  (:func:`resolve_launch_executable`, :func:`sanitize_launch_arguments`);
* ``ensure_x11_session_env`` / ``_pin_gtk_x11_backend`` /
  ``_record_session_origin`` from ``plugins/builtin/platynui_plugin.py``.

Harness changes: ``ROBOTMCP_PLATYNUI_KEEP_WAYLAND`` -> ``RFH_PLATYNUI_KEEP_WAYLAND``;
platform and filesystem probes are injectable for replay tests.

Why: when the server is launched from a snap-confined shell (e.g. a VS Code
snap), the parent environment carries snap-rooted loader/module/data
variables. A GNOME app launched via ``Process.Start Process`` inheriting those
loads the snap-bundled libpthread and dies with ``symbol lookup error ...
undefined symbol __libc_pthread_init``. A sanitized CHILD environment filters
``/snap/``-rooted PATH SEGMENTS (not whole variables) and overlays the display
variables; a snap-confined AUT keeps its own roots.
"""

from __future__ import annotations

import logging
import os
import shutil
import sys
import threading
from collections.abc import Callable, Mapping, MutableMapping
from typing import Any

from . import _env

logger = logging.getLogger(__name__)

# Variables whose value is a list of path SEGMENTS we filter by package root.
_PATH_LIST_VARS = (
    "LD_LIBRARY_PATH",
    "GTK_PATH",
    "GIO_MODULE_DIR",
    "GIO_EXTRA_MODULES",
    "GSETTINGS_SCHEMA_DIR",
    "QT_PLUGIN_PATH",
    "XDG_DATA_DIRS",
    "FONTCONFIG_PATH",
    "LOCPATH",
)
# Single-path variables: dropped entirely when they point under a package root.
_SINGLE_PATH_VARS = (
    "LD_PRELOAD",
    "GTK_EXE_PREFIX",
    "FONTCONFIG_FILE",
)

# Package-root prefixes considered "contaminating" for a non-snap AUT.
# /var/lib/snapd/ holds snap-exported .desktop launchers/icons that, if left in
# XDG_DATA_DIRS, can re-introduce snap Exec= handlers.
_CONTAMINATING_ROOTS = ("/snap/", "/var/lib/snapd/")


def get_effective_path(parent_env: Mapping[str, str] | None = None) -> str:
    """Return the PATH the server process resolves executables against."""
    env = parent_env if parent_env is not None else os.environ
    return env.get("PATH", "") or ""


def resolve_executable(name: str, *, parent_env: Mapping[str, str] | None = None) -> str | None:
    """Resolve an executable name to an absolute path via ``shutil.which``
    against the SERVER-process PATH (never an interactive shell's startup
    environment). Returns ``None`` when unresolvable. An already-absolute
    existing path is returned unchanged.
    """
    if not name or not isinstance(name, str):
        return None
    if os.path.isabs(name):
        return name if os.path.exists(name) else None
    env = parent_env if parent_env is not None else os.environ
    return shutil.which(name, path=env.get("PATH"))


def _segment_under_roots(segment: str, roots: tuple) -> bool:
    seg = segment.strip()
    return bool(seg) and any(seg.startswith(r) for r in roots)


def _filter_path_list(value: str, roots: tuple) -> str:
    parts = value.split(os.pathsep)
    kept = [p for p in parts if not _segment_under_roots(p, roots)]
    return os.pathsep.join(kept)


def _aut_snap_root(executable: str, path: str | None = None) -> str | None:
    """Return the /snap/<name>/ root when the AUT is itself a snap binary.

    Resolves the binary (PATH + symlinks); a snap app's binary resolves under
    ``/snap/<name>/...``. We then preserve that snap's roots from stripping.
    """
    if not executable:
        return None
    resolved = shutil.which(executable, path=path) or executable
    try:
        real = os.path.realpath(resolved)
    except OSError:
        real = resolved
    for candidate in (resolved, real):
        if candidate and candidate.startswith("/snap/"):
            # /snap/<name>/<rev>/... -> keep "/snap/<name>/"
            parts = candidate.split("/")
            if len(parts) >= 3:
                return "/snap/" + parts[2] + "/"
    return None


def build_desktop_launch_env(
    executable: str,
    *,
    parent_env: Mapping[str, str] | None = None,
    display_env: Mapping[str, str] | None = None,
    sanitize: bool = True,
    path: str | None = None,
) -> dict[str, str]:
    """Build a sanitized child environment for a desktop GUI launch.

    Args:
        executable: the GUI binary being launched (for snap-AUT detection).
        parent_env: base environment (defaults to ``os.environ``).
        display_env: display variables to overlay (DISPLAY, XDG_SESSION_TYPE,
            GDK_BACKEND, ...). A value of "" removes the variable.
        sanitize: when False, skip filtering (the no-sanitize hatch); the
            display overlay is still applied.
        path: PATH used to resolve ``executable`` for snap-AUT detection
            (default: the server process PATH, as in rf-mcp).

    Returns:
        A new env dict (the parent is not mutated).
    """
    base = dict(parent_env if parent_env is not None else os.environ)

    # When the AUT is itself a snap binary it needs its snap roots — do not
    # sanitize at all in that case (stripping would break it).
    if sanitize and _aut_snap_root(executable, path) is None:
        roots = _CONTAMINATING_ROOTS
        for var in _PATH_LIST_VARS:
            if var in base and base[var]:
                base[var] = _filter_path_list(base[var], roots)
        for var in _SINGLE_PATH_VARS:
            val = base.get(var, "")
            if val and _segment_under_roots(val, roots):
                base.pop(var, None)

    # Overlay display variables; an empty value means "unset".
    for key, value in (display_env or {}).items():
        if value == "":
            base.pop(key, None)
        else:
            base[key] = value

    return base


# Fast-path allow-set: binaries always treated as GUI launches (no session
# context needed).
_KNOWN_GUI_BINARIES = frozenset(
    {
        "gnome-calculator",
        "gnome-text-editor",
        "gedit",
        "nautilus",
        "gnome-control-center",
        "gnome-terminal",
        "eog",
        "evince",
    }
)

# Deny-set: obvious non-GUI shell/utility binaries that a desktop session may
# legitimately ``Start Process`` without any GUI launch hardening.
_NON_GUI_BINARIES = frozenset(
    {
        "bash",
        "sh",
        "dash",
        "zsh",
        "fish",
        "csh",
        "tcsh",
        "ksh",
        "python",
        "python3",
        "python2",
        "uv",
        "uvx",
        "pipx",
        "node",
        "deno",
        "cat",
        "echo",
        "sleep",
        "env",
        "true",
        "false",
        "ls",
        "test",
        "printf",
        "grep",
        "sed",
        "awk",
        "cut",
        "head",
        "tail",
        "sort",
        "uniq",
        "wc",
        "cp",
        "mv",
        "rm",
        "mkdir",
        "touch",
        "chmod",
        "chown",
        "which",
        "id",
        "kill",
        "pkill",
        "pgrep",
        "ps",
        "uname",
        "date",
        "sync",
        "dbus-send",
        "xdotool",
        "xrandr",
        "xset",
        "import",
        "convert",
    }
)


def is_desktop_gui_launch(
    arguments: list,
    *,
    is_desktop_session: bool | None = None,
    environ: Mapping[str, str] | None = None,
) -> str | None:
    """Return the GUI binary name when arguments look like a desktop GUI launch
    (``Start Process <gui-binary> ...``), else None.

    - A binary in the known-gnome allow-set is always recognized (fast path,
      no session context needed).
    - When ``is_desktop_session`` is True, ANY resolvable binary that is not on
      the non-GUI deny-set is recognized as a GUI launch, so non-gnome AUTs
      (LibreOffice, Firefox, Qt apps, mousepad) get the same launch hardening.
    """
    if not arguments:
        return None
    first = arguments[0]
    if not isinstance(first, str):
        return None
    raw = first.strip()
    if not raw or raw.startswith("env:") or "=" in raw:
        return None
    binary = os.path.basename(raw)
    if binary in _KNOWN_GUI_BINARIES:
        return binary
    if is_desktop_session is not True:
        return None
    if binary in _NON_GUI_BINARIES:
        return None
    # Evidence-based: a desktop session launching a resolvable, non-utility
    # binary is treated as a GUI AUT.
    if os.path.isabs(raw):
        return binary if os.path.exists(raw) else None
    path = None if environ is None else environ.get("PATH")
    if shutil.which(raw, path=path) is not None:
        return binary
    return None


def gui_launch_overrides(binary: str, *, parent_env: Mapping[str, str] | None = None) -> dict[str, str]:
    """Return the accessibility/backend override keys applied to a recognized
    GUI launch.

    ``GTK_A11Y`` defaults to ``atspi`` unless the parent env already sets it to
    a non-empty value (an explicit operator choice is never overwritten). The
    X11 backend pins are always applied so a GTK or Qt AUT comes up on X11 with
    a populated AT-SPI tree regardless of the server process environment.
    """
    env = parent_env if parent_env is not None else os.environ
    overrides: dict[str, str] = {
        "GTK_A11Y": (env.get("GTK_A11Y") or "").strip() or "atspi",
        "GDK_BACKEND": "x11",
        "QT_QPA_PLATFORM": "xcb",
        "XDG_SESSION_TYPE": "x11",
        "NO_AT_BRIDGE": "0",
    }
    return overrides


# --- Executor launch rewriting (rf-mcp KeywordExecutor, as pure functions) ---

_PROCESS_LAUNCH_KEYWORDS = ("start process", "run process")

# Vars injected as RF ``env:`` overrides (per-var; the rest is inherited).
_INJECT_VARS = (
    "LD_LIBRARY_PATH",
    "GTK_PATH",
    "GIO_MODULE_DIR",
    "GIO_EXTRA_MODULES",
    "GSETTINGS_SCHEMA_DIR",
    "QT_PLUGIN_PATH",
    "XDG_DATA_DIRS",
    "DISPLAY",
    "XDG_SESSION_TYPE",
    "GDK_BACKEND",
    "GTK_A11Y",
    "QT_QPA_PLATFORM",
    "NO_AT_BRIDGE",
)
_A11Y_BACKEND_KEYS = ("GTK_A11Y", "GDK_BACKEND", "QT_QPA_PLATFORM", "XDG_SESSION_TYPE", "NO_AT_BRIDGE")


def _process_launch(keyword: str) -> bool:
    return keyword.strip().lower().rsplit(".", 1)[-1] in _PROCESS_LAUNCH_KEYWORDS


def resolve_launch_executable(
    keyword: str,
    arguments: list,
    *,
    desktop_session: bool,
    environ: Mapping[str, str] | None = None,
) -> list:
    """For a desktop-session Process launch, resolve ``arguments[0]`` to an
    absolute path against the server PATH so a tool present for the server is
    found from step execution. Returns possibly-rewritten arguments."""
    try:
        if not _process_launch(keyword) or desktop_session is not True or not arguments:
            return arguments
        exe = arguments[0]
        # Skip RF config tokens (env:..., key=value options).
        if not isinstance(exe, str) or not exe or exe.startswith("env:") or "=" in exe:
            return arguments
        env = os.environ if environ is None else environ
        resolved = resolve_executable(exe, parent_env=env)
        if resolved and resolved != exe:
            logger.info("PlatynUI desktop launch: resolved executable %r -> %r", exe, resolved)
            return [resolved] + list(arguments[1:])
        if resolved is None and not os.path.isabs(exe):
            logger.warning(
                "PlatynUI desktop launch: executable %r is not resolvable on the server PATH=%s",
                exe,
                get_effective_path(env),
            )
        return arguments
    except Exception as exc:  # pragma: no cover - defensive
        logger.debug("desktop executable resolution skipped: %s", exc)
        return arguments


def sanitize_launch_arguments(
    keyword: str,
    arguments: list,
    *,
    desktop_session: bool,
    environ: Mapping[str, str] | None = None,
    no_sanitize: bool = False,
) -> tuple[list, dict[str, Any] | None]:
    """For a desktop-session ``Start/Run Process`` of a GUI binary, append RF
    ``env:`` overrides that strip snap-contaminated loader vars and pin the
    bound display / accessibility backend.

    Returns ``(arguments, info)`` where ``info`` is ``None`` when the launch was
    not recognized as a GUI launch, else ``{"binary", "applied", "a11y_backend"}``
    (the applied override keys, for diagnosing an empty accessibility tree).
    """
    try:
        if not _process_launch(keyword) or desktop_session is not True:
            return arguments, None
        env = os.environ if environ is None else environ
        # Evidence-based detection: any GUI AUT in a desktop session.
        binary = is_desktop_gui_launch(list(arguments or []), is_desktop_session=True, environ=env)
        if binary is None:
            return arguments, None
        # Already carries explicit env: overrides? leave it to the author.
        if any(isinstance(a, str) and a.startswith("env:") for a in (arguments or [])):
            return arguments, {"binary": binary, "applied": [], "a11y_backend": [], "author_env": True}
        display_env = {
            "DISPLAY": env.get("DISPLAY", ""),
            "WAYLAND_DISPLAY": "",
        }
        display_env.update(gui_launch_overrides(binary, parent_env=env))
        clean = build_desktop_launch_env(
            arguments[0], parent_env=env, display_env=display_env, sanitize=not no_sanitize, path=env.get("PATH")
        )
        extra = []
        for var in _INJECT_VARS:
            if var in clean and clean[var]:
                extra.append(f"env:{var}={clean[var]}")
        # Neutralize snap single-path vars that were dropped.
        for var in ("LD_PRELOAD", "GTK_EXE_PREFIX"):
            if var in env and var not in clean:
                extra.append(f"env:{var}=")
        applied = [e.split("=", 1)[0].split(":", 1)[1] for e in extra if e.startswith("env:") and "=" in e]
        info = {
            "binary": binary,
            "applied": applied,
            "a11y_backend": [k for k in applied if k in _A11Y_BACKEND_KEYS],
        }
        if extra:
            logger.info(
                "PlatynUI desktop launch: %s recognized as GUI AUT; applied %d env overrides (a11y/backend: %s)",
                binary,
                len(extra),
                ",".join(info["a11y_backend"]) or "none",
            )
            return list(arguments) + extra, info
        return arguments, info
    except Exception as exc:  # pragma: no cover - defensive
        logger.debug("desktop launch sanitize skipped: %s", exc)
        return arguments, None


# --- X11 backend forcing + Wayland origin (rf-mcp platynui_plugin) -----------

KEEP_WAYLAND_ENV = _env.KEEP_WAYLAND

_ENV_SHIM_LOCK = threading.Lock()

# Whether this process's desktop session originated as Wayland (set once,
# before X11 is forced, by ensure_x11_session_env).
_WAYLAND_ORIGIN: bool | None = None


def wayland_origin(
    environ: Mapping[str, str] | None = None,
    *,
    path_exists: Callable[[str], bool] = os.path.exists,
) -> bool:
    """True when the environment looks like a Wayland session: env signals or a
    live ``$XDG_RUNTIME_DIR/wayland-0`` socket (the env may be scrubbed on a
    real Wayland host while the socket still exists). Pure; never raises."""
    env = os.environ if environ is None else environ
    try:
        session_type = env.get("XDG_SESSION_TYPE", "").strip().lower()
        if session_type == "wayland" or env.get("WAYLAND_DISPLAY"):
            return True
        runtime_dir = env.get("XDG_RUNTIME_DIR", "")
        return bool(runtime_dir and path_exists(os.path.join(runtime_dir, "wayland-0")))
    except Exception:  # pragma: no cover - defensive
        return False


def _record_session_origin(env: Mapping[str, str]) -> None:
    """Record (once, sticky True) whether the session originated as Wayland."""
    global _WAYLAND_ORIGIN
    if _WAYLAND_ORIGIN:
        return  # already known to be Wayland; do not downgrade
    if wayland_origin(env):
        _WAYLAND_ORIGIN = True
    elif _WAYLAND_ORIGIN is None:
        _WAYLAND_ORIGIN = False


def was_wayland_session() -> bool:
    """True when this process recorded a Wayland-origin desktop session."""
    return _WAYLAND_ORIGIN is True


def ensure_x11_session_env(
    environ: MutableMapping[str, str] | None = None,
    *,
    platform: str | None = None,
) -> str | None:
    """Force the X11 backend for PlatynUI on Linux Wayland sessions.

    The PlatynUI Wayland input backend performs an xdg-desktop-portal
    RemoteDesktop handshake with no timeout (and an interactive consent dialog)
    — fatal for a headless session. Must run BEFORE the first
    ``platynui_native.Runtime`` is created in the process (the session type is
    cached process-wide). MUTATES ``environ`` (default ``os.environ``).

    Returns a human-readable note when the environment was changed, else None.
    """
    env = environ if environ is not None else os.environ
    if (platform or sys.platform) != "linux":
        return None

    with _ENV_SHIM_LOCK:
        # Record whether this session ORIGINATED as Wayland, BEFORE forcing X11.
        _record_session_origin(env)

        if env.get(KEEP_WAYLAND_ENV, "").strip() in {"1", "true", "yes"}:
            return None

        session_type = env.get("XDG_SESSION_TYPE", "").strip().lower()
        wayland = bool(env.get("WAYLAND_DISPLAY"))
        display = bool(env.get("DISPLAY"))

        if session_type == "x11":
            _pin_gtk_x11_backend(env)
            return None
        if not display:
            # No X server available — forcing X11 would break init outright.
            if session_type == "wayland" or wayland:
                logger.warning(
                    "PlatynUI: Wayland session without DISPLAY — runtime init may "
                    "block on an xdg-desktop-portal consent dialog. Approve the "
                    "dialog once (a restore token is persisted) or provide an "
                    "X11/XWayland DISPLAY."
                )
            return None
        if session_type == "wayland" or (not session_type and wayland):
            env["XDG_SESSION_TYPE"] = "x11"
            _pin_gtk_x11_backend(env)
            note = (
                "PlatynUI: forced XDG_SESSION_TYPE=x11 (XWayland) to avoid the "
                "Wayland xdg-desktop-portal consent handshake which blocks "
                f"indefinitely in headless contexts. Set {KEEP_WAYLAND_ENV}=1 to "
                "keep the native Wayland backend."
            )
            logger.warning(note)
            return note
        _pin_gtk_x11_backend(env)
        return None


def _pin_gtk_x11_backend(env: MutableMapping[str, str]) -> None:
    """Pin GUI-toolkit backends to X11 when a Wayland compositor socket is
    reachable.

    Unsetting ``WAYLAND_DISPLAY`` is NOT sufficient: libwayland's
    ``wl_display_connect(NULL)`` falls back to the literal socket ``wayland-0``
    in ``$XDG_RUNTIME_DIR``, so an AUT launched with ``DISPLAY=:100`` can
    silently render on the user's ACTIVE host desktop while synthetic XTest
    input goes to the isolated display. Children inherit this process env via
    Start Process, so pinning here confines GTK/Qt AUTs to the bound X display.
    Respects pre-set values.
    """
    try:
        if env.get("GDK_BACKEND") or env.get("QT_QPA_PLATFORM"):
            return
        runtime_dir = env.get("XDG_RUNTIME_DIR", "")
        wayland_reachable = bool(env.get("WAYLAND_DISPLAY")) or (
            runtime_dir and os.path.exists(os.path.join(runtime_dir, "wayland-0"))
        )
        if not wayland_reachable or not env.get("DISPLAY"):
            return
        env["GDK_BACKEND"] = "x11"
        env["QT_QPA_PLATFORM"] = "xcb"
        logger.info(
            "PlatynUI: pinned GDK_BACKEND=x11 / QT_QPA_PLATFORM=xcb — a "
            "Wayland compositor socket is reachable and GTK's wayland-0 "
            "fallback would otherwise let AUTs escape to the active desktop."
        )
    except Exception:  # pragma: no cover - defensive
        pass
