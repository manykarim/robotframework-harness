#!/usr/bin/env python3
"""PostToolUse hook: lint the .robot/.resource file an agent just wrote with Robocop (agent profile) and feed
compact findings back to the model.

Run with the project's Python (the one that has robocop + the RF libraries installed), e.g.
  .venv/bin/python robocop_hook.py --agent claude      (Claude Code: tool_input.file_path)
  .venv/bin/python robocop_hook.py --agent codex       (Codex: apply_patch -> parses '*** Update File: x')
  .venv/bin/python robocop_hook.py --agent copilot     (Copilot CLI: toolArgs.path)
Env:
  ROBOCOP_AGENT_CONFIG  path of the agent profile toml (default: robot.toml/robocop.toml discovery)
  ROBOCOP_HOOK_AUTOFIX  "1" -> apply robocop's safe fixes (DEPR*, SPC19-22, NAME09) before reporting
  ROBOCOP_HOOK_PYTHONPATH  os.pathsep-separated extra --pythonpath entries (resources/, libs/)
Exit 0 always (PostToolUse cannot block); silent when the file is clean.
"""

from __future__ import annotations

import contextlib
import io
import json
import os
import re
import sys
import time
from pathlib import Path

SUFFIXES = {".robot", ".resource"}
MAX_LINES = 25


def edited_files(payload: dict, agent: str) -> list[Path]:
    cwd = Path(payload.get("cwd") or os.getcwd())
    paths: list[str] = []
    if agent == "copilot":
        args = payload.get("toolArgs") or {}
        if isinstance(args, str):
            with contextlib.suppress(json.JSONDecodeError):
                args = json.loads(args)
        if isinstance(args, dict):
            paths += [args.get(k) for k in ("path", "file_path", "filePath") if args.get(k)]
    else:
        ti = payload.get("tool_input") or {}
        if isinstance(ti, dict):
            paths += [ti.get(k) for k in ("file_path", "filePath", "path") if ti.get(k)]
            patch = ti.get("patch") or ti.get("input") or ti.get("command") or ""
        else:
            patch = str(ti)
        if isinstance(patch, list):
            patch = "\n".join(map(str, patch))
        paths += re.findall(r"^\*\*\* (?:Add|Update) File: (.+)$", str(patch), flags=re.M)
    out = []
    for p in paths:
        path = Path(p)
        path = path if path.is_absolute() else cwd / path
        if path.suffix in SUFFIXES and path.is_file():
            out.append(path.resolve())
    return list(dict.fromkeys(out))


def find_root(path: Path) -> Path:
    env_root = os.environ.get("CLAUDE_PROJECT_DIR")
    if env_root:
        return Path(env_root)
    for parent in path.parents:
        if any((parent / n).exists() for n in ("robot.toml", "robocop.toml", "pyproject.toml", ".git")):
            return parent
    return path.parent


def lint(files: list[Path]) -> tuple[list, float]:
    from robocop.run import check_files  # imported lazily: ~0.3 s

    root = find_root(files[0])
    cfg = os.environ.get("ROBOCOP_AGENT_CONFIG")
    pp = [p for p in os.environ.get("ROBOCOP_HOOK_PYTHONPATH", "").split(os.pathsep) if p]
    t0 = time.perf_counter()
    with contextlib.redirect_stdout(io.StringIO()):
        if os.environ.get("ROBOCOP_HOOK_AUTOFIX") == "1":
            check_files(sources=[str(f) for f in files], root=root, configuration_file=Path(cfg) if cfg else None,
                        fix=True, return_result=True, silent=True, skip_gitignore=True, exit_zero=True,
                        python_path=pp or None, cache_dir=root / ".robocop_cache")
        diags = check_files(sources=[str(f) for f in files], root=root,
                            configuration_file=Path(cfg) if cfg else None, return_result=True, silent=True,
                            skip_gitignore=True, exit_zero=True, python_path=pp or None,
                            cache_dir=root / ".robocop_cache")
    wanted = {str(f) for f in files}
    # project rules report the whole project -> keep only the edited file(s)
    own = [d for d in diags if str(Path(str(d.source.path)).resolve()) in wanted]
    return own, time.perf_counter() - t0


def render(diags: list, files: list[Path]) -> str:
    sev_rank = {"E": 0, "W": 1, "I": 2}
    rows = sorted(diags, key=lambda d: (sev_rank.get(str(d.severity.value), 3), d.range.start.line))
    lines = []
    for d in rows[:MAX_LINES]:
        name = Path(str(d.source.path)).name if len(files) > 1 else ""
        fix = " (auto-fixable)" if getattr(d.rule, "fixable", False) else ""
        lines.append(f"{name}L{d.range.start.line}:{d.range.start.character} {d.severity.value} {d.rule.rule_id} "
                     f"{d.message}{fix}")
    more = f"\n... {len(rows) - MAX_LINES} more" if len(rows) > MAX_LINES else ""
    head = f"robocop: {len(rows)} issue(s) in {', '.join(f.name for f in files)}"
    hint = ""
    if any(getattr(d.rule, "fixable", False) for d in rows):
        hint = f"\nSafe auto-fix: robocop check --fix {' '.join(str(f) for f in files)}"
    return head + "\n" + "\n".join(lines) + more + hint


def main() -> None:
    agent = sys.argv[sys.argv.index("--agent") + 1] if "--agent" in sys.argv else "claude"
    payload = json.loads(sys.stdin.read() or "{}")
    files = edited_files(payload, agent)
    if not files:
        return
    try:
        diags, dt = lint(files)
    except Exception as e:  # noqa: BLE001 - never break the agent loop
        print(f"robocop hook failed: {e}", file=sys.stderr)
        return
    if not diags:
        return
    text = render(diags, files)
    if agent == "copilot":
        print(json.dumps({"additionalContext": text}))
    else:  # Claude Code and Codex share the hookSpecificOutput shape
        print(json.dumps({"hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": text}}))
    if os.environ.get("ROBOCOP_HOOK_DEBUG"):
        print(f"[lint {dt:.3f}s]", file=sys.stderr)


if __name__ == "__main__":
    main()
