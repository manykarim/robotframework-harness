#!/usr/bin/env python3
"""Quick-start check (design D8, tasks 5.3 / 7.2; stdlib only): run the documented quick-start commands for one agent
in a fresh temporary project, time every step, print one JSON result.

    python3 eval/quickstart_check.py --agent claude --dry-run          # only print the planned commands (JSON)
    python3 eval/quickstart_check.py --agent codex                     # run them (installer from this checkout)
    python3 eval/quickstart_check.py --agent claude --with-agent --real-home   # + a real agent session

Steps (the user-facing ones are what the per-agent quick start documents; the check runs the installer from this
checkout via --runtime-source instead of PyPI):
  1. project   `uv venv <project>/.venv`                                  (the user's own project environment)
  2. install   `rf-harness install --agents <agent> --mode files --scope project --project <project> --yes
                --runtime-source <repo>`
  3. doctor    `rf-harness doctor --agents <agent> --project <project>`
  4. robot     `<project>/.venv/bin/robot --outputdir <project>/results tests/demo.robot`   (plain robot on a demo test)
  5. session   (only with --with-agent) one headless agent session that edits the demo test and runs robot; passes
               when harness feedback (the `[rfh]` marker) shows up in the transcript

The result passes when every executed step exits 0, the documented steps are at most five commands, and the total
duration stays under the limit (default 300 s). Agent homes are isolated in <project>/.agent_home unless --real-home
(a real agent session needs the user's credentials). Exit 0 = ok, 1 = a step failed or a limit was exceeded.
"""
from __future__ import annotations

import argparse
import json
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parent
AGENTS = ("claude", "codex", "copilot", "vscode", "opencode")
VENV_BIN = "Scripts" if os.name == "nt" else "bin"
MAX_COMMANDS = 5
LIMIT_S = 300.0
DEMO_TEST = """*** Test Cases ***
Quick Start Demo
    ${greeting}=    Set Variable    Hello, Robot Framework
    Should Contain    ${greeting}    Robot Framework
"""
SESSION_PROMPT = ("Add a second test case 'Quick Start Sum' to tests/demo.robot that checks that 2 + 3 equals 5 "
                  "(use Evaluate and Should Be Equal As Integers), then run `robot -d results tests/demo.robot` "
                  "until it passes.")
FEEDBACK_MARKER = "[rfh]"


def installer_cmd(python: str) -> list[str]:
    return [python, "-m", "rf_harness.installer.cli"]


def agent_session_cmd(agent: str, project: Path) -> list[str] | None:
    if agent == "claude":
        return ["claude", "-p", SESSION_PROMPT, "--output-format", "stream-json", "--verbose",
                "--include-hook-events", "--dangerously-skip-permissions", "--max-turns", "15"]
    if agent == "codex":
        return ["codex", "exec", "--json", "--skip-git-repo-check", "-C", str(project),
                "--dangerously-bypass-approvals-and-sandbox", SESSION_PROMPT]
    if agent == "opencode":
        return ["opencode", "run", "--dir", str(project), "--format", "json", "--dangerously-skip-permissions",
                SESSION_PROMPT]
    if agent == "copilot":
        return ["copilot", "-p", SESSION_PROMPT, "--allow-all", "--no-ask-user", "--output-format", "json",
                "-C", str(project)]
    return None          # vscode: no headless CLI session; verified manually


def plan(agent: str, project: Path, repo: Path, python: str, with_agent: bool) -> list[dict]:
    """The steps, in order: {name, cmd, cwd, documented (counts toward the five-command budget), timeout_s}."""
    steps = [
        {"name": "project", "cmd": ["uv", "venv", str(project / ".venv")], "documented": True, "timeout_s": 120},
        {"name": "install", "cmd": installer_cmd(python) + [
            "install", "--agents", agent, "--mode", "files", "--scope", "project", "--project", str(project), "--yes",
            "--runtime-source", str(repo)], "documented": True, "timeout_s": 600},
        {"name": "doctor", "cmd": installer_cmd(python) + ["doctor", "--agents", agent, "--project", str(project)],
         "documented": True, "timeout_s": 120},
        {"name": "robot", "cmd": [str(project / ".venv" / VENV_BIN / "robot"), "--outputdir", str(project / "results"),
                                  str(project / "tests" / "demo.robot")], "documented": True, "timeout_s": 120},
    ]
    if with_agent:
        cmd = agent_session_cmd(agent, project)
        steps.append({"name": "session", "cmd": cmd, "documented": False, "timeout_s": 600,
                      "note": None if cmd else f"{agent}: no headless session; verify in the IDE"})
    for s in steps:
        s["cwd"] = str(project)
    return steps


def step_env(project: Path, repo: Path, real_home: bool) -> dict:
    env = dict(os.environ)
    env["PYTHONPATH"] = str(repo / "src") + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    env["VIRTUAL_ENV"] = str(project / ".venv")
    env["PATH"] = f"{project / '.venv' / VENV_BIN}{os.pathsep}{env.get('PATH', '')}"
    if not real_home:
        home = project / ".agent_home"
        env.update({"CLAUDE_CONFIG_DIR": str(home), "CODEX_HOME": str(home), "COPILOT_HOME": str(home),
                    "OPENCODE_CONFIG": str(home / "opencode.json")})
    return env


def run_steps(steps: list[dict], project: Path, repo: Path, real_home: bool) -> list[dict]:
    project.mkdir(parents=True, exist_ok=True)
    (project / "tests").mkdir(exist_ok=True)
    (project / "tests" / "demo.robot").write_text(DEMO_TEST, encoding="utf-8")
    if not real_home:
        (project / ".agent_home").mkdir(exist_ok=True)
    env = step_env(project, repo, real_home)
    out = []
    for s in steps:
        rec = {k: s[k] for k in ("name", "documented")}
        rec["cmd"] = shlex.join(s["cmd"]) if s.get("cmd") else None
        if not s.get("cmd"):
            rec.update(rc=None, skipped=True, note=s.get("note"))
            out.append(rec)
            continue
        t0 = time.monotonic()
        try:
            p = subprocess.run(s["cmd"], cwd=s["cwd"], env=env, capture_output=True, text=True,
                               timeout=s["timeout_s"], stdin=subprocess.DEVNULL)
            rc, text = p.returncode, (p.stdout or "") + (p.stderr or "")
        except subprocess.TimeoutExpired as exc:
            rc, text = None, f"timeout after {s['timeout_s']} s: {exc}"
        except OSError as exc:
            rc, text = None, f"{type(exc).__name__}: {exc}"
        rec.update(rc=rc, duration_s=round(time.monotonic() - t0, 2), output_tail=text[-800:])
        if s["name"] == "session":
            rec["feedback_seen"] = FEEDBACK_MARKER in text
        out.append(rec)
        if rc != 0:
            break                    # later steps depend on this one
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="run (or --dry-run: print) the documented quick-start commands")
    ap.add_argument("--agent", required=True, choices=AGENTS)
    ap.add_argument("--dry-run", action="store_true", help="only print the planned commands as JSON")
    ap.add_argument("--project", default=None, help="project dir (default: a new temporary directory)")
    ap.add_argument("--runtime-source", default=str(REPO_ROOT), help="checkout installed as the runtime")
    ap.add_argument("--python", default=sys.executable, help="interpreter that runs the installer")
    ap.add_argument("--with-agent", action="store_true", help="add one real headless agent session (step 5)")
    ap.add_argument("--real-home", action="store_true", help="use the user's agent homes (needed for --with-agent)")
    ap.add_argument("--limit-s", type=float, default=LIMIT_S)
    ap.add_argument("--keep", action="store_true", help="keep the temporary project")
    args = ap.parse_args(argv)
    repo = Path(args.runtime_source).resolve()
    tmp_created = args.project is None
    project = (Path(args.project) if args.project
               else Path(tempfile.gettempdir()) / f"rfh-quickstart-{args.agent}-<random>")
    if not args.dry_run and tmp_created:
        project = Path(tempfile.mkdtemp(prefix=f"rfh-quickstart-{args.agent}-"))
    steps = plan(args.agent, project.resolve() if not args.dry_run else project, repo, args.python, args.with_agent)
    documented = sum(1 for s in steps if s["documented"])
    result: dict = {"agent": args.agent, "project": str(project), "runtime_source": str(repo),
                    "documented_commands": documented, "max_commands": MAX_COMMANDS, "limit_s": args.limit_s}
    if args.dry_run:
        result.update(dry_run=True, steps=[{"name": s["name"], "documented": s["documented"],
                                            "cmd": shlex.join(s["cmd"]) if s.get("cmd") else None,
                                            **({"note": s["note"]} if s.get("note") else {})} for s in steps])
        print(json.dumps(result, indent=1))
        return 0
    t0 = time.monotonic()
    try:
        recs = run_steps(steps, project, repo, args.real_home)
    finally:
        total = round(time.monotonic() - t0, 2)
        if tmp_created and not args.keep:
            shutil.rmtree(project, ignore_errors=True)
    failed = [r["name"] for r in recs if r.get("rc") not in (0, None) or (r.get("rc") is None and not r.get("skipped"))]
    if len(recs) < len(steps):
        failed += [s["name"] for s in steps[len(recs):] if s["name"] not in failed]
    ok = not failed and documented <= MAX_COMMANDS and total <= args.limit_s
    session = next((r for r in recs if r["name"] == "session"), None)
    if session and not session.get("skipped") and not session.get("feedback_seen"):
        ok = False
    result.update(dry_run=False, ok=ok, total_s=total, under_limit=total <= args.limit_s, steps=recs,
                  failed_steps=failed)
    print(json.dumps(result, indent=1))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
