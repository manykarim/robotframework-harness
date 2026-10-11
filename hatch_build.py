"""Hatch build hook: mirror plugins/rf-harness/ into src/rf_harness/_assets/.

The plugin tree is the single source of truth: the plugin marketplace serves it directly, and the installer ships the
same files inside the wheel (files mode, OpenCode) so both install exactly the same content.

- sdist / editable / wheel-from-repo: the plugin tree exists next to pyproject.toml -> copy it.
- wheel built from an extracted sdist: there is no plugins/ directory, but _assets/ came with the sdist -> keep it.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from hatchling.builders.hooks.plugin.interface import BuildHookInterface

PLUGIN_REL = Path("plugins") / "rf-harness"
ASSETS_REL = Path("src") / "rf_harness" / "_assets"
IGNORE = shutil.ignore_patterns("__pycache__", "*.pyc", ".DS_Store")


class CustomBuildHook(BuildHookInterface):  # type: ignore[misc]
    PLUGIN_NAME = "custom"

    def initialize(self, version: str, build_data: dict[str, Any]) -> None:
        src = (Path(self.root) / PLUGIN_REL).resolve()
        dst = (Path(self.root) / ASSETS_REL).resolve()
        if not src.is_dir():
            if dst.is_dir() and any(dst.rglob("SKILL.md")):
                return
            raise RuntimeError(f"rf-harness: plugin source {src} is missing and {dst} is empty")
        if dst.exists():
            shutil.rmtree(dst)
        shutil.copytree(src, dst, ignore=IGNORE)
