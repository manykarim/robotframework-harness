"""OpenRouter route through run_batch / run_cell, in process, with the OpenRouter API mocked (no network, no spend):
balance pre-check (exit 5), per-run budget booking and exhaustion (exit 4), a 402 transcript blocking further
OpenRouter cells (exit 5), and the key never reaching an artifact."""

from __future__ import annotations

import gzip
import json
import stat
import textwrap
import threading

import pytest
from eval_helpers import posix_only

pytestmark = posix_only

FAKE_OR_KEY = "sk-" + "or-v1-" + "fedcba9876543210" * 4
AGENT = "cc-or:qwen3.8-flash"

STUB = textwrap.dedent('''\
    #!/usr/bin/env python3
    import json, os
    mode = os.environ.get("STUB_MODE", "ok")
    def out(d):
        print(json.dumps(d), flush=True)
    out({"type": "system", "subtype": "init", "model": os.environ.get("ANTHROPIC_MODEL"), "mcp_servers": []})
    if mode == "credits":
        msg = "API Error: 402 This request requires more credits, or fewer max_tokens."
        out({"type": "assistant", "message": {"model": "<synthetic>", "content": [{"type": "text", "text": msg}]}})
        out({"type": "result", "subtype": "success", "is_error": True, "api_error_status": 402, "result": msg})
    else:
        os.makedirs("reports", exist_ok=True)
        open("reports/summary.md", "w").write("Total 8, Passed 4, Failed 3, Skipped 1; Checkout, Regression\\n")
        out({"type": "assistant", "message": {"model": os.environ.get("ANTHROPIC_MODEL"), "content": [
            {"type": "text", "text": "token " + os.environ.get("ANTHROPIC_AUTH_TOKEN", "")}]}})
        out({"type": "result", "subtype": "success", "num_turns": 3, "result": "done",
             "usage": {"input_tokens": 100000, "output_tokens": 20000, "cache_read_input_tokens": 0,
                       "cache_creation_input_tokens": 0}})
''')


class FakeOpenRouter:
    def __init__(self, balance=50.0):
        self.usage = 10.0
        self.balance = balance
        self.lock = threading.Lock()

    def key_usage(self, key):
        assert key == FAKE_OR_KEY
        return self.usage

    def settled_usage(self, key, before, wait_s=40.0, step=6.0):
        with self.lock:
            self.usage += 0.03            # what this (solo) cell cost the account
            return self.usage

    def key_info(self, key):
        return {"usage": self.usage, "limit": 250.0, "limit_remaining": 250.0 - self.usage}

    def account_balance(self, key):
        return self.balance


@pytest.fixture
def H(tmp_path, monkeypatch):
    import harness as H

    fake = FakeOpenRouter()
    sbin = tmp_path / "stubbin"
    sbin.mkdir()
    (sbin / "claude").write_text(STUB)
    (sbin / "claude").chmod(0o755 | stat.S_IEXEC)
    (tmp_path / "vbin").mkdir()
    monkeypatch.setenv("PATH", f"{sbin}:{__import__('os').environ.get('PATH', '')}")
    monkeypatch.setenv("OPENROUTER_API_KEY", FAKE_OR_KEY)
    for k in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN"):
        monkeypatch.delenv(k, raising=False)
    out = tmp_path / "out"
    for name, val in {"OUT_DIR": out, "RESULTS": out / "results_rc_t.jsonl", "TRANSCRIPTS": out / "transcripts_rc_t",
                      "WORK_ROOT": tmp_path / "work", "VENV_BIN": tmp_path / "vbin", "MIN_FREE_BYTES": 1,
                      "OR_KEY": None, "OR_BUDGET": None, "OR_GUARD": None, "OR_ACTIVITY": None,
                      "OR_BUDGET_USD": 5.0, "OR_BUDGET_RESET": False, "OR_MIN_BALANCE": 0.5,
                      "OR_MODELS": {"qwen3.8-flash": "qwen/qwen3.8-flash"}, "OR_SKIPPED": {"n": 0},
                      "OR_BALANCE_SKIPPED": {"n": 0}, "OR_RUNNING": {"n": 0}, "AUTH_BLOCKED": {},
                      "ABORT": threading.Event(), "PRUNE": True}.items():
        monkeypatch.setattr(H, name, val)
    monkeypatch.setattr(H, "_install_signal_handlers", lambda: None)
    monkeypatch.setattr(H.OR, "ACTIVITY_FILE", tmp_path / "or_activity.json")
    monkeypatch.setattr(H.OR, "key_usage", fake.key_usage)
    monkeypatch.setattr(H.OR, "settled_usage", fake.settled_usage)
    monkeypatch.setattr(H.OR, "key_info", fake.key_info)
    monkeypatch.setattr(H.OR, "account_balance", fake.account_balance)
    monkeypatch.setattr(H.OR, "prices", lambda refresh=False, max_age_s=86400.0: {
        "qwen/qwen3.8-flash": {"prompt": 1e-7, "completion": 4e-7}})
    H._fake = fake
    return H


def _rows(H):
    return [json.loads(ln) for ln in H.RESULTS.read_text().splitlines()] if H.RESULTS.exists() else []


def test_balance_precheck_refuses_to_start(H):
    H._fake.balance = 0.12
    with pytest.raises(SystemExit) as e:
        H.run_batch(1, [AGENT], ["results_complex"], ["neither"], 1)
    assert e.value.code == 5
    assert _rows(H) == []


def test_ok_cell_books_its_own_spend_and_never_stores_the_key(H, monkeypatch):
    monkeypatch.setenv("STUB_MODE", "ok")
    assert H.run_batch(1, [AGENT], ["results_complex"], ["neither"], 1) == 0
    (row,) = _rows(H)
    assert row["status"] == "ok" and row["route"] == "cc-or" and row["model"] == "qwen/qwen3.8-flash"
    o = row["openrouter"]
    assert o["est_cost_usd"] == pytest.approx(100000 * 1e-7 + 20000 * 4e-7)
    assert o["delta_shared"] is False and o["run_spend_source"] == "usage_delta"
    assert o["run_spend_usd"] == pytest.approx(0.03)
    state = json.loads(H.RESULTS.with_name("results_rc_t.or_budget.json").read_text())
    assert state["format"] == "per-run-v2" and list(state["cells"]) == [row["cell_id"]]
    assert sum(c["usd"] for c in state["cells"].values()) == pytest.approx(0.03)
    for f in H.OUT_DIR.rglob("*"):
        if f.is_file():
            data = gzip.open(f, "rt").read() if f.suffix == ".gz" else f.read_text(errors="replace")
            assert FAKE_OR_KEY not in data and FAKE_OR_KEY[:12] not in data, f


def test_exhausted_run_budget_skips_cells_with_exit_4(H, monkeypatch):
    monkeypatch.setenv("STUB_MODE", "ok")
    monkeypatch.setattr(H, "OR_BUDGET_USD", 0.0)
    assert H.run_batch(1, [AGENT], ["results_complex"], ["neither"], 1) == 4
    assert _rows(H) == [] and H.OR_SKIPPED["n"] == 1


def test_402_session_is_invalid_and_blocks_further_openrouter_cells(H, monkeypatch):
    monkeypatch.setenv("STUB_MODE", "credits")
    assert H.run_batch(2, [AGENT], ["results_complex"], ["neither"], 1) == 5
    rows = _rows(H)
    assert len(rows) == 1                                   # rep 2 was not started
    assert rows[0]["status"] == "invalid" and rows[0]["invalid_kind"] == "credits"
    assert rows[0]["openrouter"]["run_spend_usd"] > 0       # money spent on an invalid cell still counts
    assert H.OR_BALANCE_SKIPPED["n"] == 1 and H.OR_GUARD.blocked_reason
