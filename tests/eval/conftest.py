"""Offline tests of the evaluation harness: put eval/ (the stdlib scripts) and this directory (eval_helpers) on sys.path."""

from __future__ import annotations

import sys
from pathlib import Path

# The evaluation harness is Linux-only (it reaps processes via /proc, drives agent CLIs, and cell paths contain ':'),
# so its tests run only on Linux.
if sys.platform != "linux":
    collect_ignore_glob = ["test_*.py"]

_HERE = Path(__file__).resolve().parent
for _p in (_HERE.parents[1] / "eval", _HERE):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))
