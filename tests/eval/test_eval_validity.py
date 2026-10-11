"""Round-7 fix (c): sessions that did no real work are detected from the transcript and marked invalid."""

from __future__ import annotations

import json

import pytest
import validity as V
from eval_helpers import (
    archived,
    claude_402_events,
    codex_outage_events,
    needs,
    result_row,
    write_gz_transcript,
    write_jsonl,
)


def test_402_transcript_fixture_is_invalid(tmp_path):
    """The recorded incident: Claude Code exits with result:success but its only answer is an HTTP 402."""
    tx = write_gz_transcript(tmp_path / "transcripts" / "cc-or:qwen" / "cell.jsonl.gz", claude_402_events())
    row = result_row("cc-or:qwen3.8-flash|hookpkg32|demoshop_order|1", transcript=str(tx.relative_to(tmp_path)),
                     agent_info={"errors": ["result:success"]})
    inv = V.classify_row(row, tmp_path)
    assert inv is not None
    assert inv["kind"] == "credits"
    assert "402" in inv["reason"]


def test_402_text_without_status_field_is_invalid(tmp_path):
    events = [{"type": "assistant", "message": {"model": "<synthetic>", "content": [
        {"type": "text", "text": "API Error: 402 This request requires more credits, or fewer max_tokens."}]}}]
    inv = V.classify("cc-or:glm", [json.dumps(e) for e in events])
    assert inv and inv["kind"] == "credits"


@pytest.mark.parametrize("text,kind", [
    ("Insufficient credits. Add more using https://openrouter.ai/settings/credits", "credits"),
    ("API Error: 401 {\"error\":{\"message\":\"User not found.\"}}", "auth"),
    ("Failed to authenticate. API Error: 401 OAuth token has expired.", "auth"),
])
def test_provider_failures_in_agent_text(text, kind):
    events = [{"type": "result", "subtype": "success", "result": text}]
    inv = V.classify("claude", [json.dumps(e) for e in events])
    assert inv and inv["kind"] == kind


def test_codex_backend_outage_fixture_is_invalid(tmp_path):
    events, stderr = codex_outage_events()
    tx = write_gz_transcript(tmp_path / "t" / "codex" / "cell.jsonl.gz", events, stderr_tail=stderr)
    row = result_row("codex|hookpkg31|tricentis_debug|2", transcript=str(tx.relative_to(tmp_path)),
                     metrics={"tool_calls": 3}, stderr_tail=stderr[-600:])
    inv = V.classify_row(row, tmp_path)
    assert inv is not None and inv["kind"] == "backend_outage"
    assert "3 tool calls" in inv["reason"]


def test_codex_timeouts_with_real_work_stay_valid(tmp_path):
    events, stderr = codex_outage_events()
    assert V.classify("codex", [json.dumps(e) for e in events], stderr, tool_calls=25) is None


def test_single_timeout_is_not_an_outage():
    assert V.classify("codex", [], "failed to refresh available models: request timed out", tool_calls=2) is None


def test_outage_rule_applies_to_codex_only():
    _, stderr = codex_outage_events()
    assert V.classify("opencode", [], stderr, tool_calls=2) is None


def test_tool_results_never_invalidate_a_session():
    """A page under test or a tool output that mentions credits must not count (only agent-authored text is read)."""
    events = [
        {"type": "user", "message": {"content": [{"type": "tool_result", "content":
                                                  "API Error: 402 requires more credits (text on the page)"}]}},
        {"type": "assistant", "message": {"model": "m", "content": [{"type": "tool_use", "name": "Bash",
                                                                      "input": {"command": "echo Insufficient credits"}}]}},
        {"type": "result", "subtype": "success", "result": "All 5 tests pass."},
    ]
    assert V.classify("claude", [json.dumps(e) for e in events], "", tool_calls=40) is None


def test_healthy_claude_session_is_valid():
    events = [{"type": "assistant", "message": {"model": "m", "content": [{"type": "text", "text": "Done."}]}},
              {"type": "result", "subtype": "success", "result": "The suite passes."}]
    assert V.classify("claude", [json.dumps(e) for e in events]) is None


def test_clean_results_relabels_invalid_and_drops_aborted(tmp_path):
    tx = write_gz_transcript(tmp_path / "transcripts" / "a.jsonl.gz", claude_402_events())
    res = write_jsonl(tmp_path / "results_live_x.jsonl", [
        result_row("claude|mcp|demoshop_order|1"),
        result_row("cc-or:qwen|mcp|demoshop_order|1", transcript="transcripts/a.jsonl.gz"),
        result_row("claude|mcp|demoshop_debug|1", status="aborted"),
    ])
    with res.open("a") as f:
        f.write('{"key": "torn')                        # torn last line of a killed run
    dropped, relabelled, bak = V.clean_results(res, now="T")
    assert (dropped, relabelled) == (2, 1)
    assert bak is not None and bak.name == "results_live_x.bak.T.jsonl" and bak.exists()
    rows = [json.loads(ln) for ln in res.read_text().splitlines()]
    assert [r["status"] for r in rows] == ["ok", "invalid"]
    assert rows[1]["invalid_kind"] == "credits" and rows[1]["primary_pass"] is False
    assert tx.exists()
    assert V.clean_results(res) == (0, 0, None)          # idempotent: nothing left to change


def test_clean_cli_prints_counts(tmp_path, capsys):
    res = write_jsonl(tmp_path / "r.jsonl", [result_row("claude|mcp|demoshop_order|1", status="aborted")])
    assert V.main(["clean", str(res)]) == 0
    assert capsys.readouterr().out.split() == ["1", "0"]


FINAL = ["results_live_v3main.jsonl", "results_live_v31sub.jsonl", "results_live_v31or.jsonl", "results_live_v32.jsonl"]


@needs(*[archived(f) for f in FINAL])
@pytest.mark.slow
def test_archived_final_results_have_no_invalid_sessions():
    """No false positives on the 425 scored round-6/7 rows."""
    for f in FINAL:
        assert V.scan_results(archived(f)) == [], f


@needs(archived("results_live_v31or.bak.20261010-131135.credits402.jsonl"),
       archived("results_live_v32.bak.20261010-131136.credits402.jsonl"),
       archived("results_live_v32.bak.20261010-132914.codexinfra.jsonl"))
@pytest.mark.slow
def test_archived_incident_rows_are_found():
    """The rows the round-7 incident removed by hand: 64 (v31or) + 12 (v32 Qwen) credit failures, 1 Codex outage."""
    v31or = V.scan_results(archived("results_live_v31or.bak.20261010-131135.credits402.jsonl"))
    assert len(v31or) == 64 and {r["kind"] for r in v31or} == {"credits"}
    v32 = V.scan_results(archived("results_live_v32.bak.20261010-131136.credits402.jsonl"))
    assert sum(r["kind"] == "credits" for r in v32) == 12
    assert all(r["key"].startswith("cc-or:qwen") for r in v32 if r["kind"] == "credits")
    infra = V.scan_results(archived("results_live_v32.bak.20261010-132914.codexinfra.jsonl"))
    assert [(r["key"], r["kind"]) for r in infra] == [("codex|hookpkg31|tricentis_debug|2", "backend_outage")]
