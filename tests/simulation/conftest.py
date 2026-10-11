"""Shared readiness check for the browser-based simulation tests (Browser + RequestsLibrary + chromium on Linux)."""

from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

import pytest


def browser_skip_reason() -> str | None:
    if not sys.platform.startswith("linux"):
        return "simulation suite runs on Linux (POSIX daemons, /proc process checks)"
    for mod in ("Browser", "RequestsLibrary"):
        if importlib.util.find_spec(mod) is None:
            return f"{mod} not installed (uv sync --group dev --group browser)"
    from rf_harness.runtime import hookcore

    wrapper = Path(importlib.util.find_spec("Browser").origin).parent / "wrapper" / "node_modules"
    if not wrapper.is_dir():
        return "Browser wrapper not initialized (uv run rfbrowser init --skip-browsers)"
    bundled = any((wrapper / "playwright-core" / ".local-browsers").glob("chromium_headless_shell-*"))
    if not (bundled or os.environ.get("PLAYWRIGHT_BROWSERS_PATH") or hookcore.playwright_env(sys.executable)):
        return "no chromium-headless-shell for Browser's playwright-core (bundled or in ~/.cache/ms-playwright)"
    return None


@pytest.fixture(scope="session")
def browser_ready() -> None:
    reason = browser_skip_reason()
    if reason:
        pytest.skip(reason)
