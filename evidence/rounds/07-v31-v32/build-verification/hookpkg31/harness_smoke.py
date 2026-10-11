"""Smoke test of the A/B harness integration of the `hookpkg31` arm (or any arm; agent may be cc-or:<short> / oc-or:<short>
for the OpenRouter routes) WITHOUT the real fixtures (blind protocol):
a mini scenario built from verify/site + verify/repair is run through harness.run_cell() for one agent and arm,
results/transcripts go to a scratch dir (never to ab/harness/results*).

  PLAYWRIGHT_BROWSERS_PATH=~/.cache/ms-playwright python3 verify/harness_smoke.py [agent] [arm] [SCRATCH]
Prints the row fields the arm adds: hookpkg metrics (incl. the v3.1 output profile), contamination, helper/hook usage,
OpenRouter accounting (row["openrouter"]: tokens, estimate, /key usage delta).
"""
from __future__ import annotations

import json
import shutil
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
AB = HERE.parent.parent
sys.path.insert(0, str(AB / "harness"))
import harness as h  # noqa: E402

PROMPT = ("tests/checkout.robot used to pass and now fails. Repair it: keep all its tests and assertions, fix the "
          "test code. It must pass with a plain `robot -d results tests/checkout.robot` run. Finish with the final "
          "robot summary line.")


def main() -> int:
    agent = sys.argv[1] if len(sys.argv) > 1 else "claude"
    arm = sys.argv[2] if len(sys.argv) > 2 else "hookpkg31"
    scratch = Path(sys.argv[3] if len(sys.argv) > 3 else tempfile.mkdtemp(prefix="hooksmoke-")).resolve()
    fx = scratch / "fixtures"
    shutil.rmtree(fx, ignore_errors=True)
    (fx / "mini" / "tests").mkdir(parents=True)
    shutil.copytree(HERE / "site", fx / "mini" / "site")
    shutil.copy2(HERE / "repair" / "checkout.robot", fx / "mini" / "tests" / "checkout.robot")
    import os
    if os.environ.get("CLAUDE_MODEL"):                     # e.g. claude-haiku-5-5 (subscription)
        h.AGENT_MODELS["claude"] = os.environ["CLAUDE_MODEL"]
    h.FIXTURES_SRC = fx                                    # monkeypatched: never the real fixtures
    h.WORK_ROOT = Path.home() / ".cache" / "ab-eval" / "work_hooksmoke31"
    h.RESULTS = scratch / "results_smoke.jsonl"
    h.TRANSCRIPTS = scratch / "transcripts"
    h.PRUNE = True
    sc = h.Scenario(id="hooksmoke", skill="robotframework", tier="smoke", fixture="mini", prompt=PROMPT,
                    graders=[{"type": "robot_pass", "path": "tests/checkout.robot"},
                             {"type": "file_contains", "path": "tests/checkout.robot", "regex": "Express Shipping Costs Extra"}],
                    primary_metric="all", timeout_s=900, max_turns=40, browser=True)
    h.WORK_ROOT.mkdir(parents=True, exist_ok=True)
    reaper = h.Reaper(h.WORK_ROOT)
    reaper.start()
    try:
        row = h.run_cell(agent, arm, sc, 1, reaper)
    finally:
        reaper.stop()
        reaper.sweep()
    keep = {k: row.get(k) for k in ("key", "status", "error", "primary_pass", "n_pass", "n_checks", "contaminated",
                                     "helper_cli_calls", "hook_usage_hits", "hook_cross_hits", "has_hookpkg",
                                     f"{arm}_install", arm, "stepwise", "leak_markers", "turn_cap", "model",
                                     "base_agent", "route", "openrouter", "agent_info")}
    keep["metrics"] = {k: (row.get("metrics") or {}).get(k) for k in ("turns", "tool_calls", "cost_usd", "wall_s")}
    print(json.dumps(keep, indent=1, default=str))
    (scratch / "row.json").write_text(json.dumps(row, indent=1, default=str))
    return 0 if row.get("status") == "ok" else 1


if __name__ == "__main__":
    sys.exit(main())
