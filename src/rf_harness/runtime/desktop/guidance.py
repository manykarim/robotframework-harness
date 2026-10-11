"""Desktop guidance bundle: the PlatynUI keyword cheat-sheet and locator crib.

Vendored from rf-mcp ``src/robotmcp/components/execution/desktop_guidance.py``
(https://github.com/manykarim/rf-mcp, release 0.36.0, commit c1a18eb; Apache-2.0,
same author). Harness changes: the crib drops rf-mcp's MCP-tool line
("call get_locator_guidance") and the bundle drops the MCP ``execute_batch``
advice, since the harness has neither tool. The remaining rules are verbatim.

The cheat-sheet is derived once from ``LibraryDocumentation("PlatynUI.BareMetal")``
and cached process-wide; it soft-fails to None when Robot Framework or PlatynUI
is not installed.
"""

from __future__ import annotations

import logging
import threading
from typing import Any

logger = logging.getLogger(__name__)

DESKTOP_LIBRARY = "PlatynUI.BareMetal"

# Authoritative locator rules (rf-mcp's crib, minus its MCP-tool pointer).
LOCATOR_CRIB: tuple[str, ...] = (
    "Scope EVERY locator to the app: /app:*[@Name='<app>']//control:... — NEVER start a locator with // (it walks the whole desktop and the guard refuses it).",
    "Set Root to the app once, then use relative control:/item: locators.",
    "On Linux, windows are control:Frame, NOT control:Window (control:Window matches nothing and hangs 30s).",
    "Launch the app first (Process.Start Process), then Query for its control:Frame before acting.",
    "Read a value back with Get Attribute on the scoped node; GTK text views expose native:Text.CharacterCount (not live text content).",
    "Take Screenshot signature is (descriptor, filename, rect) — the FIRST positional is a node descriptor, not a filename; pass filename= for a path.",
    "Prefer the atomic 'Keyboard Type' (self-contained press+release) for shortcuts, e.g. Keyboard Type  <descriptor>  <Ctrl+A>. A bare 'Keyboard Press' sends key-DOWN ONLY and MUST be paired with 'Keyboard Release' — an unpaired Press (esp. a non-modifier like a letter/F-key/Escape) leaves a key physically held on the OS.",
)

_cache_lock = threading.Lock()
_cached_bundle: dict[str, Any] | None = None


def compress_arg(arg: Any) -> str:
    """Reduce a libdoc arg spec to ``name`` or ``name=<short default>``.

    ``descriptor: UiNodeDescriptor | None = None`` -> ``descriptor=None``;
    ``filename: ... = platynui-screenshot-{index}.png`` -> ``filename=…``.
    Type annotations are dropped; argument order and defaults are preserved.
    """
    text = str(arg)
    name = text.split(":", 1)[0].split("=", 1)[0].strip()
    if "=" in text:
        default = text.split("=", 1)[1].strip()
        if len(default) > 14:
            default = "…"
        return f"{name}={default}"
    return name


def compress_signature(name: str, args: Any) -> str:
    """One-line signature preserving argument order, e.g. ``Get Attribute(descriptor, name)``."""
    parts = [compress_arg(a) for a in (args or [])]
    return f"{name}({', '.join(parts)})"


def build_cheat_sheet(library: str = DESKTOP_LIBRARY) -> list[str]:
    """Derive the PlatynUI keyword cheat-sheet from libdoc as compact one-line
    signatures (each begins with the keyword name), preserving argument order."""
    from robot.libdocpkg import LibraryDocumentation  # local import: libdoc is heavy

    lib = LibraryDocumentation(library)
    return [compress_signature(kw.name, getattr(kw, "args", None)) for kw in lib.keywords]


def get_desktop_guidance() -> dict[str, Any] | None:
    """Return the cached desktop guidance bundle, or None if libdoc is unavailable."""
    global _cached_bundle
    if _cached_bundle is not None:
        return _cached_bundle
    with _cache_lock:
        if _cached_bundle is not None:
            return _cached_bundle
        try:
            cheat_sheet = build_cheat_sheet()
        except Exception as e:  # soft-fail: never break session start
            logger.debug("Desktop guidance unavailable (libdoc): %s", e)
            return None
        _cached_bundle = {
            "library": DESKTOP_LIBRARY,
            "keyword_count": len(cheat_sheet),
            "keywords": cheat_sheet,
            "locator_crib": list(LOCATOR_CRIB),
            "note": "Desktop keyword surface + locator rules.",
        }
        return _cached_bundle
