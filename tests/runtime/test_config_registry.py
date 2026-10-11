"""The RFH_* registry (rf_harness.config) covers every variable the runtime reads, with the prototype defaults, and
applies `.rf/harness.json` env defaults below the process environment."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from rf_harness import config

RUNTIME = Path(config.__file__).parent / "runtime"
DYNAMIC_PREFIXES = ("RFH_MAX_CTX_", "RFH_MAX_CTX_RICH_")       # per agent: <prefix><AGENT>


def _runtime_names() -> set:
    names = set()
    for f in RUNTIME.rglob("*.py"):
        names |= set(re.findall(r"\bRFH_[A-Z0-9_]*[A-Z0-9]\b", f.read_text(encoding="utf-8")))
    return names


def test_every_variable_the_runtime_mentions_is_registered():
    missing = sorted(n for n in _runtime_names() if not config.is_registered(n) and n not in DYNAMIC_PREFIXES
                     and not n.endswith("_"))
    assert not missing, f"register these in rf_harness.config: {missing}"


def test_desktop_variables_match_the_desktop_package():
    from rf_harness.runtime.desktop import _env

    assert _env.ENV_VARIABLES, "desktop package lists no variables"
    for name, (default, doc) in _env.ENV_VARIABLES.items():
        var = config.VARIABLES.get(name)
        assert var is not None, f"{name} is not registered"
        assert (var.default, var.doc, var.category) == (default, doc, "desktop"), name


def test_per_agent_budget_variables_exist_for_every_agent():
    for agent in config.AGENTS:
        assert config.is_registered(f"RFH_MAX_CTX_{agent.upper()}")
        assert config.is_registered(f"RFH_MAX_CTX_RICH_{agent.upper()}")


def test_categories_and_docs():
    for var in config.VARIABLES.values():
        assert var.category in config.CATEGORIES, var
        assert var.doc.strip(), var


@pytest.mark.parametrize(("name", "default"), [
    ("RFH_BUDGET", "90"), ("RFH_GATE_TIMEOUT", "2.5"), ("RFH_IDLE_EXIT", "1200"), ("RFH_MAX_CONTEXT", "2048"),
    ("RFH_MAX_CONTEXT_OPENCODE", "1200"), ("RFH_SHORT_TIMEOUT", "2.5"), ("RFH_STABLE_S", "2"),
    ("RFH_ADAPT_FACTOR", "1.5"), ("RFH_FRESH_DOC_S", "6"), ("RFH_MAX_CAPTURES", "2"), ("RFH_STATE_HISTORY", "15"),
    ("RFH_CAPTURE", "end"), ("RFH_CAPTURE_SETTLE", "1.5"), ("RFH_GUARD_SETTLE", "5.0"), ("RFH_PAGE_TEXT", "4000"),
    ("RFH_MAX_DENIALS", "3"), ("RFH_MAX_DENIALS_OPENCODE", "2"), ("RFH_MAX_STOP_BLOCKS", "2"), ("RFH_LOOP_AT", "3"),
    ("RFH_READ_STREAK_AT", "8"), ("RFH_DOC_WAIT", "1.2"), ("RFH_KWDOC_FILES", "0"), ("RFH_STATIC", "on"),
    ("RFH_DENY_CODES", "TokenError,ParsingError,InvalidHeader,ModelError"),
    ("RFH_REWRITE_AGENTS", "claude,opencode,codex,copilot"), ("RFH_COMPACT_AGENTS", "opencode"),
    ("RFH_RFMCP_HINTS", "0"), ("RFH_DESKTOP", "0"),
])
def test_prototype_defaults(name, default):
    assert config.VARIABLES[name].default == default


def test_typed_getters(monkeypatch):
    monkeypatch.setenv("RFH_BUDGET", "nonsense")
    assert config.get_float("RFH_BUDGET") == 90.0
    monkeypatch.setenv("RFH_MAX_DENIALS", "5")
    assert config.get_int("RFH_MAX_DENIALS") == 5
    monkeypatch.setenv("RFH_COMPACT_AGENTS", "")
    assert config.get_list("RFH_COMPACT_AGENTS") == ["opencode"]
    with pytest.raises(KeyError):
        config.get("RFH_NOT_A_THING")


def test_harness_json_env_defaults(tmp_path, monkeypatch):
    (tmp_path / ".rf").mkdir()
    (tmp_path / ".rf" / "harness.json").write_text(json.dumps({
        "python": "/x/bin/python", "version": "0.9.0",
        "env": {"RFH_STATIC": "runtime-only", "RFH_BUDGET": 30, "OTHER": "ignored", "RFH_X": ["bad"]}}))
    sub = tmp_path / "tests"
    sub.mkdir()
    monkeypatch.delenv("RFH_ROOT", raising=False)
    monkeypatch.delenv("CLAUDE_PROJECT_DIR", raising=False)
    monkeypatch.delenv("RFH_STATIC", raising=False)
    monkeypatch.delenv("RFH_BUDGET", raising=False)
    assert config.find_harness_json(sub) == tmp_path / ".rf" / "harness.json"
    try:
        config.set_project_root(tmp_path)
        assert config.project_env() == {"RFH_STATIC": "runtime-only", "RFH_BUDGET": "30"}
        assert config.get("RFH_STATIC") == "runtime-only"
        assert config.get_float("RFH_BUDGET") == 30.0
        monkeypatch.setenv("RFH_STATIC", "on")                   # the process environment wins
        assert config.get("RFH_STATIC") == "on"
    finally:
        config.set_project_root(None)


def test_malformed_harness_json_is_ignored(tmp_path):
    (tmp_path / ".rf").mkdir()
    (tmp_path / ".rf" / "harness.json").write_text("{not json")
    assert config.load_project_env(tmp_path / ".rf" / "harness.json") == {}
    (tmp_path / ".rf" / "harness.json").write_text(json.dumps({"env": ["RFH_STATIC"]}))
    assert config.load_project_env(tmp_path / ".rf" / "harness.json") == {}
    assert config.load_project_env(None) == {}
