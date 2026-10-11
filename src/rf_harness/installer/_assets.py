"""Locate the plugin tree (skill, hooks, launcher, variants) that the installer copies.

Search order:
1. ``RF_HARNESS_ASSETS_DIR`` (tests, local experiments);
2. a source checkout: ``<repo>/plugins/rf-harness`` next to ``src/rf_harness`` (the single source of truth);
3. the wheel: ``rf_harness/_assets`` (built from ``plugins/rf-harness`` by hatch_build.py).

Adapted from robotframework-agentskills' ``installer/src/rf_agentskills/_assets.py`` (same author, Apache-2.0).
"""

from __future__ import annotations

import atexit
import json
import os
from collections.abc import Iterator
from contextlib import ExitStack
from importlib.resources import as_file, files
from pathlib import Path

ASSETS_ENV = "RF_HARNESS_ASSETS_DIR"
_IGNORED = {"__pycache__", ".DS_Store"}
_stack = ExitStack()
atexit.register(_stack.close)


class AssetsMissing(RuntimeError):
    """The plugin tree could not be found."""


def _valid(root: Path) -> bool:
    return (root / ".claude-plugin" / "plugin.json").is_file()


def source_checkout_root() -> Path | None:
    """``plugins/rf-harness`` of the repository this package was imported from, if any."""
    candidate = Path(__file__).resolve().parents[3] / "plugins" / "rf-harness"
    return candidate if _valid(candidate) else None


def plugin_root() -> Path:
    env = os.environ.get(ASSETS_ENV)
    if env:
        root = Path(env).expanduser().resolve()
        if not _valid(root):
            raise AssetsMissing(f"{ASSETS_ENV}={env} has no .claude-plugin/plugin.json")
        return root
    checkout = source_checkout_root()
    if checkout is not None:
        return checkout
    traversable = files("rf_harness").joinpath("_assets")
    root = Path(_stack.enter_context(as_file(traversable)))  # type: ignore[arg-type]
    if not _valid(root):
        raise AssetsMissing("the bundled plugin assets (rf_harness/_assets) are missing; reinstall robotframework-harness")
    return root


def bundle_version(root: Path | None = None) -> str:
    root = root or plugin_root()
    data = json.loads((root / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
    return str(data.get("version", "unknown"))


def iter_files(base: Path) -> Iterator[Path]:
    """Every shipped file under ``base`` (sorted, caches skipped)."""
    if base.is_file():
        yield base
        return
    if not base.is_dir():
        return
    for path in sorted(base.rglob("*")):
        if path.is_file() and not (_IGNORED & set(path.parts)) and path.suffix != ".pyc":
            yield path
