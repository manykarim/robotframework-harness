"""Lean/rich output budgets (rf_harness.runtime.leanfmt / richfmt): per-agent caps, overrides, must-keep rendering."""

from __future__ import annotations

import pytest

from rf_harness.runtime import leanfmt, richfmt


@pytest.mark.parametrize(("agent", "caps"), [("claude", (250, 700)), ("codex", (250, 700)), ("copilot", (250, 700)),
                                             ("opencode", (250, 600)), ("vscode", (250, 700)),
                                             ("unknown-agent", (250, 700))])
def test_default_lean_caps(agent, caps, monkeypatch):
    for a in ("CLAUDE", "CODEX", "COPILOT", "OPENCODE", "VSCODE"):
        monkeypatch.delenv(f"RFH_MAX_CTX_{a}", raising=False)
    assert leanfmt.caps(agent) == caps


def test_lean_caps_override_and_invalid_value(monkeypatch):
    monkeypatch.setenv("RFH_MAX_CTX_CLAUDE", "300,900")
    assert leanfmt.caps("claude") == (300, 900)
    monkeypatch.setenv("RFH_MAX_CTX_CLAUDE", "lots")
    assert leanfmt.caps("claude") == (250, 700)


def test_rich_caps(monkeypatch):
    monkeypatch.delenv("RFH_MAX_CTX_RICH", raising=False)
    monkeypatch.delenv("RFH_MAX_CTX_RICH_OPENCODE", raising=False)
    assert richfmt.caps("opencode") == (1200, 1200)
    monkeypatch.setenv("RFH_MAX_CTX_RICH_OPENCODE", "800,1000")
    assert richfmt.caps("opencode") == (800, 1000)
    monkeypatch.setenv("RFH_MAX_CTX_RICH", "900,900")             # the global one wins
    assert richfmt.caps("opencode") == (900, 900)


def test_render_keeps_must_lines_and_drops_optional_ones_over_budget():
    o = leanfmt.Out()
    o.add("L13 FAIL  Click    id=x", must=True)
    o.add("x" * 300)
    o.add("NEXT: fix line 13", must=True, nxt=True)
    text = o.render(120)
    assert text == "L13 FAIL  Click    id=x\nNEXT: fix line 13"
    assert len(text) <= 120


def test_render_adds_optional_lines_that_fit():
    o = leanfmt.Out()
    o.add("L3-L12 PASS (4 lines)", must=True)
    o.add('Page "Shop" login.html')
    assert o.render(250) == 'L3-L12 PASS (4 lines)\nPage "Shop" login.html'


def test_guidance_first_puts_next_on_top():
    o = leanfmt.Out()
    o.add("L13 FAIL", must=True)
    o.add("NEXT: fix it", must=True, nxt=True)
    assert o.render(200, guidance_first=True).splitlines()[0] == "NEXT: fix it"


def test_once_keys_are_reported_only_when_rendered():
    o = leanfmt.Out()
    o.add("must", must=True)
    o.add("y" * 500, key="sig:Click")
    o.render(100)
    assert "sig:Click" not in o.rendered_keys
    o2 = leanfmt.Out()
    o2.add("keyword: Click(selector)", key="sig:Click")
    o2.render(100)
    assert "sig:Click" in o2.rendered_keys
