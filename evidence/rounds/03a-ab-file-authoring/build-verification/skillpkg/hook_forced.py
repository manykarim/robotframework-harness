"""Does the post-edit hook's text reach the model? Agent writes a file with planted errors verbatim, must not run
anything, and quotes what it was told. python3 verify/hook_forced.py WORKROOT codex opencode ..."""
from __future__ import annotations

import json
import subprocess
import sys
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from agents_run import VENV_BIN, build_cmd, clean_env, prepare  # noqa: E402

SNIPPET = """*** Settings ***
Library    Browser
Force Tags    smoke

*** Test Cases ***
Planted Errors
    New Page    about:blank
    Run Keyword If    True    Log    hello
    Clik    id=submit
    Select Frame    id=checkout"""

PROMPT = ("Create the file tests/planted.robot with EXACTLY this content, copied verbatim INCLUDING its mistakes:\n"
          f"```\n{SNIPPET}\n```\nIMPORTANT: do NOT run robot, robotcode, rfmcp, python or any command - only "
          "create/edit files. If after your edit you are told about problems in the file, fix every reported ERROR "
          "with further edits. When finished reply DONE and quote verbatim every problem report you received after "
          "your edits (or NO_REPORTS_SEEN).")


def run(agent: str, root: Path, out: dict) -> None:
    cell = root / f"forced_{agent}"
    ws, home, info, creds = prepare(agent, cell)
    cmd, env = build_cmd(agent, ws, home, cell, info, PROMPT)
    with open(cell / "agent_stdout.log", "w") as f:
        try:
            subprocess.run(cmd, cwd=ws, env=env, stdout=f, stderr=subprocess.STDOUT, timeout=600)
        except subprocess.TimeoutExpired:
            pass
    log = (cell / "agent_stdout.log").read_text(errors="replace")
    final = (ws / "tests" / "planted.robot").read_text() if (ws / "tests" / "planted.robot").exists() else ""
    hl = cell / "hook.jsonl"
    r = {"hook_calls": len(hl.read_text().splitlines()) if hl.exists() else 0,
         "model_saw_hook_text": "rfmcp post-edit hook" in log,
         "quoted_reports": "NO_REPORTS_SEEN" not in log[-3000:],
         "final_has_Clik": "Clik" in final, "final_has_Select_Frame": "Select Frame" in final,
         "final_uses_IF": "    IF    " in final, "final_uses_frame_piercing": ">>>" in final}
    an = subprocess.run([str(VENV_BIN / "robotcode"), "analyze", "code", "--severity", "error", "tests/planted.robot"],
                        cwd=ws, capture_output=True, text=True, env={**clean_env(), **info["extra_env"]})
    r["errors_left"] = an.stdout.count("[ERROR]")
    for c in creds:
        c.unlink(missing_ok=True)
    out[agent] = r
    print(agent, json.dumps(r), flush=True)


if __name__ == "__main__":
    root, agents, res = Path(sys.argv[1]), sys.argv[2:], {}
    ts = [threading.Thread(target=run, args=(a, root, res)) for a in agents]
    [t.start() for t in ts]
    [t.join() for t in ts]
    p = Path(__file__).with_name("results_hook_forced.json")
    prev = json.loads(p.read_text()) if p.exists() else {}
    prev.update(res)
    p.write_text(json.dumps(prev, indent=1))
