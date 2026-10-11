"""Injected hook context per edit: v2 (rfharness2) vs v3 (rfharness3) on the SAME scripted Claude session (no LLM).

  PLAYWRIGHT_BROWSERS_PATH=~/.cache/ms-playwright python3 verify/compare_ctx.py [WORKROOT]
Journey on the local verify site: passing writes, hidden radio, iframe field, slow confirmation (4 s), value failure,
a failing and a green plain robot run. Prints chars per PostToolUse output (edits / robot runs) and hook wall time,
writes verify/compare_ctx.json.
"""
from __future__ import annotations

import json
import shutil
import statistics
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from simlib import Sim, shell_with_hooks  # noqa: E402

VENV = Path("~/workspace/rf-mcp-robotcode/.venv/bin")
HOOKS = {"v2": HERE.parent.parent / "hookpkg2" / "rfharness2" / "hook.py",
         "v3": HERE.parent / "rfharness3" / "hook.py"}
HEAD = """*** Settings ***
Library    Browser
Suite Setup    New Browser    chromium    headless=True

*** Variables ***
${URL}    file://${CURDIR}/../site/login.html

*** Test Cases ***
Order Journey
    New Page    ${URL}
    Click    text=Accept all
    Fill Text    id=username    alice
"""
STEPS = [
    ("signin", "    Fill Text    id=username    alice\n",
     "    Fill Text    id=username    alice\n    Fill Text    id=password    secret\n    Click    data-test=signin\n"
     "    Get Text    id=greeting    ==    Hello, alice\n"),
    ("hidden radio", "    Get Text    id=greeting    ==    Hello, alice\n",
     "    Get Text    id=greeting    ==    Hello, alice\n    Check Checkbox    id=ship-express\n"),
    ("label fix", "    Check Checkbox    id=ship-express\n",
     "    Click    label[for=\"ship-express\"]\n    Select Options By    id=country    label    Norway\n"),
    ("iframe miss", "    Select Options By    id=country    label    Norway\n",
     "    Select Options By    id=country    label    Norway\n    Fill Text    id=card    4242\n"),
    ("iframe fix + slow", "    Fill Text    id=card    4242\n",
     "    Fill Text    id=pay-frame >>> id=card    4242\n    Click    id=pay-frame >>> id=confirm-card\n"
     "    Click    data-test=place-order\n    Get Text    id=confirmation    contains    Total: 55.00 EUR\n"),
    ("value miss", "    Get Text    id=confirmation    contains    Total: 55.00 EUR\n",
     "    Get Text    id=confirmation    contains    Total: 55.00 EUR\n    Get Text    id=result    ==    Finished\n"),
    ("value fix", "    Get Text    id=result    ==    Finished\n", "    Get Text    id=result    ==    Done\n"),
]


def ctx(o: dict) -> str:
    h = (o or {}).get("hookSpecificOutput") or {}
    return h.get("additionalContext", "") or (o or {}).get("reason", "")


def run(version: str, root: Path) -> dict:
    ws = root / version
    shutil.rmtree(ws, ignore_errors=True)
    (ws / "tests").mkdir(parents=True)
    shutil.copytree(HERE / "site", ws / "site")
    subprocess.run(["git", "init", "-q"], cwd=ws)
    s = Sim("claude", ws, hook=HOOKS[version])
    s.hook("start", {"source": "startup"})
    time.sleep(3)
    f = ws / "tests" / "journey.robot"
    rows = []
    r = s.edit("write", f, content=HEAD)
    rows.append({"step": "first write", "chars": len(r.get("text", "")), "ms": r.get("post_ms"), "text": r.get("text", "")})
    for name, old, new in STEPS:
        r = s.edit("edit", f, old=old, new=new)
        rows.append({"step": name, "chars": len(r.get("text", "")), "ms": r.get("post_ms"), "text": r.get("text", "")})
    robot = []
    bad = ws / "tests" / "broken.robot"
    bad.write_text(HEAD.replace("Order Journey", "Broken") + "    Click    id=signin-button\n")
    b = shell_with_hooks(s, f"{VENV}/robot -d results/b tests/broken.robot")
    robot.append({"step": "failing plain run", "chars": len(b.get("text", "")), "ms": b.get("post_ms"), "text": b.get("text", "")})
    b = shell_with_hooks(s, f"{VENV}/robot -d results/j tests/journey.robot")
    robot.append({"step": "green plain run", "chars": len(b.get("text", "")), "ms": b.get("post_ms"), "text": b.get("text", "")})
    s.hook("end", {"reason": "other"})
    time.sleep(1.5)
    edits = [x["chars"] for x in rows]
    return {"edits": rows, "robot": robot, "edit_chars_total": sum(edits), "edit_chars_mean": round(statistics.mean(edits)),
            "edit_chars_max": max(edits), "robot_chars": [x["chars"] for x in robot],
            "hook_ms_edit_median": statistics.median([x["ms"] for x in rows if x["ms"] is not None]),
            "hook_ms_edit_total": sum(x["ms"] for x in rows if x["ms"] is not None)}


def main() -> int:
    root = Path(sys.argv[1] if len(sys.argv) > 1 else "/tmp/rfh-compare").resolve()
    root.mkdir(parents=True, exist_ok=True)
    res = {v: run(v, root) for v in ("v2", "v3")}
    print(f"{'step':22} {'v2 chars':>9} {'v3 chars':>9} {'v2 ms':>7} {'v3 ms':>7}")
    for a, b in zip(res["v2"]["edits"] + res["v2"]["robot"], res["v3"]["edits"] + res["v3"]["robot"]):
        print(f"{a['step']:22} {a['chars']:9d} {b['chars']:9d} {a['ms'] or 0:7d} {b['ms'] or 0:7d}")
    for v in ("v2", "v3"):
        print(v, {k: res[v][k] for k in ("edit_chars_total", "edit_chars_mean", "edit_chars_max", "robot_chars",
                                         "hook_ms_edit_median", "hook_ms_edit_total")})
    (HERE / "compare_ctx.json").write_text(json.dumps(res, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
