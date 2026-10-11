"""Fixtures for the desktop guard tests (``rf_harness.runtime.desktop``)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import desktop_fakes as fx  # noqa: E402


@pytest.fixture(scope="session")
def placeholders():
    ph = fx.Placeholders()
    try:
        yield ph
    finally:
        ph.close()
