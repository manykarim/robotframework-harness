"""Registry of every RFH_* environment variable: the single source for runtime defaults and the docs reference.

Each runtime module reads its settings through `get()` / `get_float()` / `get_bool()`, so a variable that is not
registered here raises at import time in tests, and `docs/reference/environment.md` is generated from `VARIABLES`.
"""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Var:
    name: str
    default: str
    doc: str
    category: str = "general"


VARIABLES: dict[str, Var] = {}


def register(name: str, default: str, doc: str, category: str = "general") -> Var:
    if not name.startswith("RFH_"):
        raise ValueError(f"harness variables start with RFH_: {name}")
    var = Var(name, default, doc, category)
    VARIABLES[name] = var
    return var


def get(name: str) -> str:
    var = VARIABLES.get(name)
    if var is None:
        raise KeyError(f"unregistered harness variable {name}; add it to rf_harness.config")
    return os.environ.get(name, var.default)


def get_float(name: str) -> float:
    try:
        return float(get(name))
    except ValueError:
        return float(VARIABLES[name].default)


def get_bool(name: str) -> bool:
    return get(name).strip().lower() not in ("0", "false", "no", "off", "")
