"""Offline tests of the evaluation harness: put eval/ (the stdlib scripts) and this directory (eval_helpers) on sys.path."""

from __future__ import annotations

import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
for _p in (_HERE.parents[1] / "eval", _HERE):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))
