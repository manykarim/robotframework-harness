"""Helpers for the offline tests of the evaluation harness (eval/); imported as `eval_helpers`.

The eval scripts are plain stdlib scripts that import each other by module name, so eval/ goes on sys.path.
Archived research results (round 6 / round 7) are read-only fixtures referenced by absolute path; tests that need
them are skipped when the research checkout is not present (CI).
"""

from __future__ import annotations

import gzip
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
EVAL = ROOT / "eval"
if str(EVAL) not in sys.path:
    sys.path.insert(0, str(EVAL))

RESEARCH_AB = Path("/home/many/workspace/rf-mcp-robotcode/experiments/robotcode-remote/ab")
SRC_HARNESS_DIR = RESEARCH_AB / "harness"

posix_only = pytest.mark.skipif(sys.platform == "win32", reason="the eval harness is POSIX-only (fcntl, /proc, signals)")


def archived(name: str) -> Path:
    return SRC_HARNESS_DIR / name


def needs(*paths: Path):
    """skipif marker: the archived research files are not available (e.g. on CI)."""
    missing = [str(p) for p in paths if not Path(p).exists()]
    return pytest.mark.skipif(bool(missing), reason=f"archived research data not available: {', '.join(missing)}")


def write_gz_transcript(path: Path, events: list[dict], stderr_tail: str | None = None) -> Path:
    """A transcript in the harness' archive format: agent JSONL events + __harness_calls__ (+ __stderr_tail__)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, "wt", encoding="utf-8") as g:
        for e in events:
            g.write(json.dumps(e) + "\n")
        g.write(json.dumps({"__harness_calls__": []}) + "\n")
        if stderr_tail is not None:
            g.write(json.dumps({"__stderr_tail__": stderr_tail}) + "\n")
    return path


def claude_402_events() -> list[dict]:
    """The round-7 incident shape: Claude Code against OpenRouter after the account balance ran out."""
    msg = ("API Error: 402 This request requires more credits, or fewer max_tokens. You requested up to 32000 tokens, "
           "but can only afford 27823.")
    return [
        {"type": "system", "subtype": "init", "model": "qwen/qwen3.8-flash", "mcp_servers": []},
        {"type": "assistant", "message": {"model": "qwen/qwen3.8-flash", "content": [
            {"type": "tool_use", "name": "Bash", "input": {"command": "robot tests/shop_order.robot"}}]}},
        {"type": "assistant", "message": {"model": "<synthetic>", "content": [{"type": "text", "text": msg}]}},
        {"type": "result", "subtype": "success", "is_error": True, "api_error_status": 402, "result": msg,
         "num_turns": 3, "usage": {"input_tokens": 10, "output_tokens": 5}},
    ]


def codex_outage_events() -> tuple[list[dict], str]:
    """The round-7 Codex backend outage: 3 tool calls, reconnect errors, timeouts in stderr."""
    events = [{"type": "thread.started"}]
    for i in range(3):
        events.append({"type": "item.completed", "item": {"type": "command_execution", "command": f"ls {i}",
                                                          "exit_code": 0}})
    events += [{"type": "error", "message": "Reconnecting... 5/5 (workspace routing discovery failed)"},
               {"type": "turn.failed", "error": {"message": "workspace routing discovery failed"}}]
    stderr = ("ERROR codex_models_manager::manager: failed to refresh available models: request timed out\n"
              "ERROR codex_models_manager::manager: failed to refresh available models: request timed out\n"
              'ERROR rmcp::transport::worker: worker quit with fatal: Transport channel closed, when '
              'Client(HttpRequest(HttpRequest("http/request failed: error sending request for url (https://x)")))\n')
    return events, stderr


def result_row(key: str, status: str = "ok", primary: bool = True, transcript: str | None = None, **kw) -> dict:
    agent, arm, scen, rep = key.split("|")
    row = {"key": key, "agent": agent, "arm": arm, "scenario": scen, "rep": int(rep), "status": status,
           "primary_pass": primary, "kind": "explore", "live": True, "verdicts": [], "n_checks": 0, "n_pass": 0,
           "metrics": {"tool_calls": 30, "turns": 20, "wall_s": 100.0, "cost_usd": 0.1},
           "started_at": "2026-10-10T08:00:00+00:00", "finished_at": "2026-10-10T08:10:00+00:00"}
    if transcript:
        row["transcript"] = transcript
    row.update(kw)
    return row


def write_jsonl(path: Path, rows: list[dict]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    return path
