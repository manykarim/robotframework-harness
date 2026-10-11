"""Output-profile selection (rf_harness.runtime.profiles): model id -> lean|rich and the detection order."""

from __future__ import annotations

import json

import pytest

from rf_harness.runtime import profiles

NOMODEL = {"ANTHROPIC_MODEL": "", "RFH_MODEL": "", "RFH_PROFILE": "", "OPENCODE_MODEL": "", "CODEX_MODEL": ""}

TABLE = {
    "claude-haiku-5-5": "lean", "anthropic/claude-haiku-5.5": "lean", "claude-sonnet-5": "lean",
    "gpt-5.6-luna": "lean", "openai/gpt-5.2-codex": "lean", "o3": "lean",
    "minimax-coding-plan/MiniMax-M2.5": "rich", "deepseek/deepseek-v4.1-flash": "rich", "qwen/qwen3.8-flash": "rich",
    "z-ai/glm-5.3-flash": "rich", "google/gemini-3.8-flash": "rich", "openrouter/google/gemini-3.8-flash": "rich",
    "moonshotai/kimi-k2.6": "rich", "mistralai/devstral-2": "rich",
}


@pytest.mark.parametrize(("model", "profile"), sorted(TABLE.items()))
def test_classify_model_ids(model, profile):
    assert profiles.classify(model)[0] == profile


def test_no_model_has_no_profile():
    assert profiles.classify("") == (None, "")
    assert profiles.classify(None) == (None, "")


def test_explicit_profile_wins_over_the_model():
    d = profiles.detect("claude", {}, {}, {**NOMODEL, "RFH_PROFILE": "rich", "ANTHROPIC_MODEL": "claude-haiku-5-5"})
    assert (d["profile"], d["src"]) == ("rich", "env")


def test_agent_defaults_without_any_model(tmp_path, monkeypatch):
    monkeypatch.setenv("CODEX_HOME", str(tmp_path))          # no codex config.toml with a model
    got = {a: profiles.detect(a, {}, {}, dict(NOMODEL))["profile"]
           for a in ("claude", "codex", "opencode", "copilot", "vscode")}
    assert got == {"claude": "lean", "codex": "lean", "opencode": "rich", "copilot": "lean", "vscode": "lean"}


def test_opencode_payload_model_object():
    d = profiles.detect("opencode", {"model": {"providerID": "minimax-coding-plan", "modelID": "MiniMax-M2.5"}}, {},
                        dict(NOMODEL))
    assert (d["profile"], d["model"], d["src"]) == ("rich", "minimax-coding-plan/MiniMax-M2.5", "model:payload")


def test_anthropic_model_env_only_for_claude():
    env = {**NOMODEL, "ANTHROPIC_MODEL": "z-ai/glm-5.3-flash"}
    assert profiles.detect("claude", {}, {}, env)["src"] == "model:ANTHROPIC_MODEL"
    assert profiles.detect("copilot", {}, {}, env)["src"] == "default"


def test_transcript_model(tmp_path):
    tr = tmp_path / "t.jsonl"
    tr.write_text(json.dumps({"type": "assistant", "message": {"model": "claude-haiku-5-5", "content": []}}) + "\n")
    d = profiles.detect("claude", {"transcript_path": str(tr)}, {}, dict(NOMODEL))
    assert (d["profile"], d["src"]) == ("lean", "model:transcript")


def test_stored_model_decision_is_reused():
    stored = {"profile": "rich", "src": "model:payload", "model": "deepseek/deepseek-v4.1-flash"}
    d = profiles.detect("opencode", {}, stored, dict(NOMODEL))
    assert (d["profile"], d["src"]) == ("rich", "model:payload")


def test_process_environment_goes_through_the_registry(monkeypatch):
    monkeypatch.setenv("RFH_PROFILE", "lean")
    monkeypatch.setenv("RFH_MODEL", "qwen/qwen3.8-flash")
    d = profiles.detect("opencode", {}, {})
    assert (d["profile"], d["src"], d["model"]) == ("lean", "env", "qwen/qwen3.8-flash")
    monkeypatch.setenv("RFH_PROFILE", "")
    d = profiles.detect("claude", {}, {})
    assert (d["profile"], d["src"]) == ("rich", "model:RFH_MODEL")
