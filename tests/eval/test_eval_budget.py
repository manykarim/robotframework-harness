"""Round-7 fixes (a) + (b): per-run OpenRouter budgets and the account-balance guard (no network)."""

from __future__ import annotations

import json
import threading

import openrouter as OR
import pytest
from eval_helpers import posix_only


def test_cell_spend_prefers_a_solo_delta_and_falls_back_to_the_estimate():
    assert OR.cell_spend(0.20, 0.18, shared=False) == (0.18, "usage_delta")
    assert OR.cell_spend(0.20, 0.55, shared=True) == (0.20, "estimate")        # delta shared with other cells
    assert OR.cell_spend(0.20, 5.00, shared=False) == (0.20, "estimate")       # implausible: foreign spend leaked in
    assert OR.cell_spend(None, 0.30, shared=False) == (0.30, "usage_delta")
    assert OR.cell_spend(None, 0.30, shared=True) == (0.30, "usage_delta_shared")
    assert OR.cell_spend(None, None, shared=False) == (0.0, "none")


class FakeAccount:
    """One OpenRouter key shared by several runs: /key usage only ever grows (account-wide)."""

    def __init__(self):
        self.usage = 100.0
        self.lock = threading.Lock()

    def spend(self, usd):
        with self.lock:
            self.usage += usd


@posix_only
def test_two_concurrent_runs_keep_separate_budgets(tmp_path):
    """Spec: two runs share one key; run A spends $25; run B's remaining budget is unchanged by that spend."""
    acct = FakeAccount()
    act = OR.Activity(tmp_path / "or_activity.json")          # machine-wide registry, shared by both runs
    a = OR.RunBudget(30.0, tmp_path / "results_live_a.or_budget.json")
    b = OR.RunBudget(5.0, tmp_path / "results_live_b.or_budget.json")

    def cell(run, token, est, real):
        act.enter(token)
        before = acct.usage
        acct.spend(real)
        return before, token, est, run

    # A1 ($25) and B1 ($0.40) overlap: both deltas are polluted -> both runs book their own estimates
    a1 = cell(a, "A1", 25.0, 25.0)
    b1 = cell(b, "B1", 0.40, 0.40)
    for before, token, est, run in (a1, b1):
        shared = act.leave(token)
        assert shared is True
        delta = acct.usage - before
        usd, src = OR.cell_spend(est, delta, shared)
        run.record(token, usd, src)
    assert a.spent() == 25.0
    assert b.spent() == 0.40                   # NOT 25.40: A's spend never reaches B's budget
    assert b.remaining() == pytest.approx(4.60)
    assert b.allow() and not OR.RunBudget(25.0, tmp_path / "results_live_a.or_budget.json").allow()

    # B2 runs alone: its provider-booked delta is its own and is used
    act.enter("B2")
    before = acct.usage
    acct.spend(0.37)
    shared = act.leave("B2")
    assert shared is False
    usd, src = OR.cell_spend(0.50, acct.usage - before, shared)
    assert (round(usd, 2), src) == (0.37, "usage_delta")
    b.record("B2", usd, src)
    assert b.spent() == pytest.approx(0.77)
    assert a.spent() == 25.0


def test_budget_state_survives_restarts_and_is_per_run(tmp_path):
    state = tmp_path / "results_live_t.or_budget.json"
    b = OR.RunBudget(1.0, state)
    b.record("cell-1", 0.6, "estimate", key="cc-or:q|mcp|x|1")
    again = OR.RunBudget(1.0, state)
    assert again.spent() == 0.6
    again.record("cell-1", 0.6, "estimate")                     # idempotent per cell id
    assert again.spent() == 0.6
    again.record("cell-2", 0.5, "usage_delta")
    assert not again.allow() and again.exhausted
    data = json.loads(state.read_text())
    assert data["format"] == "per-run-v2" and "baseline_usage" not in data
    assert set(data["cells"]) == {"cell-1", "cell-2"}
    assert OR.RunBudget(1.0, state, reset=True).spent() == 0.0


def test_legacy_global_baseline_state_is_ignored(tmp_path):
    state = tmp_path / "s.json"
    state.write_text(json.dumps({"baseline_usage": 455.17, "budget_usd": 50, "started": "x"}))
    b = OR.RunBudget(50.0, state)
    assert b.legacy_ignored and b.spent() == 0.0


def test_spend_is_recovered_from_the_results_file(tmp_path):
    res = tmp_path / "results_live_t.jsonl"
    res.write_text(json.dumps({"key": "k", "cell_id": "c9", "status": "invalid",
                               "openrouter": {"run_spend_usd": 0.42, "run_spend_source": "estimate"}}) + "\n")
    b = OR.RunBudget(10.0, tmp_path / "lost_state.json", results=res)
    assert b.spent() == 0.42                 # invalid cells cost money too


def test_account_guard_blocks_on_low_account_balance():
    g = OR.AccountGuard("k", 0.5, key_info_fn=lambda k: {"usage": 32.28, "limit_remaining": 217.7},
                        balance_fn=lambda k: -0.17)       # round-7: key limit fine, account empty
    ok, why = g.check(fresh=True)
    assert not ok and "account balance" in why


def test_account_guard_blocks_on_key_limit_and_passes_otherwise():
    low_key = OR.AccountGuard("k", 0.5, key_info_fn=lambda k: {"limit_remaining": 0.2}, balance_fn=lambda k: 80.0)
    assert not low_key.ok(fresh=True)
    fine = OR.AccountGuard("k", 0.5, key_info_fn=lambda k: {"limit_remaining": None}, balance_fn=lambda k: 80.0)
    assert fine.ok(fresh=True)
    unknown = OR.AccountGuard("k", 0.5, key_info_fn=lambda k: {}, balance_fn=lambda k: None)
    assert unknown.ok(fresh=True)                          # endpoint errors do not block
    fine.block("cc-or:q: provider error: 'API Error: 402'")
    assert fine.check(fresh=True) == (False, "cc-or:q: provider error: 'API Error: 402'")   # sticky


def test_balance_check_exit_codes(monkeypatch):
    monkeypatch.setattr(OR, "load_key", lambda env_file=None: "sk-test-not-a-real-key")
    monkeypatch.setattr(OR, "key_info", lambda k: {"usage": 1.0, "limit_remaining": None})
    monkeypatch.setattr(OR, "account_balance", lambda k: 0.10)
    rc, msg = OR.balance_check(0.5)
    assert rc == OR.EXIT_BALANCE == 5 and "0.10" in msg and "sk-test" not in msg
    monkeypatch.setattr(OR, "account_balance", lambda k: 12.0)
    assert OR.balance_check(0.5)[0] == 0
    monkeypatch.setattr(OR, "key_info", lambda k: {})
    assert OR.balance_check(0.5)[0] == 1
    monkeypatch.setattr(OR, "load_key", lambda env_file=None: None)
    assert OR.balance_check(0.5)[0] == 1
