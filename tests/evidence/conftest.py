"""Shared helpers for the evidence-archive tests: load the stdlib scripts under evidence/ as modules."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest

REPO = Path(__file__).resolve().parents[2]
EVIDENCE = REPO / "evidence"


def load_script(name: str) -> ModuleType:
    """Import evidence/<name>.py (the scripts are not a package)."""
    path = EVIDENCE / f"{name}.py"
    spec = importlib.util.spec_from_file_location(f"evidence_{name}", path)
    assert spec and spec.loader, path
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="session")
def scrub() -> ModuleType:
    return load_script("scrub")


@pytest.fixture(scope="session")
def check_claims() -> ModuleType:
    return load_script("check_claims")


@pytest.fixture(scope="session")
def checksums() -> ModuleType:
    return load_script("checksums")


@pytest.fixture(scope="session")
def pack_transcripts() -> ModuleType:
    return load_script("pack_transcripts")


@pytest.fixture(scope="session")
def verify_assets() -> ModuleType:
    return load_script("verify_assets")


@pytest.fixture
def no_env_secrets(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> dict[str, str]:
    """An environment without real secret values, so tests never depend on (or touch) the developer's keys."""
    env = {"RFH_SCRUB_ENV": "RFH_TEST_FAKE_SECRET", "RFH_SCRUB_DOTENV": str(tmp_path / "absent.env")}
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    monkeypatch.delenv("RFH_TEST_FAKE_SECRET", raising=False)
    return env
