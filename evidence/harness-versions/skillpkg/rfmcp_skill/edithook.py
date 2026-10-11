"""Post-edit hook: `rfmcp hook --agent claude|codex|copilot|opencode` (JSON payload on stdin).

For each edited *.robot / *.resource file:
  1. robocop with the agent profile (data/robocop-agent.toml): safe auto-fix of deprecated syntax
     (Run Keyword If, [Return], WITH NAME, Force Tags, ...), then report what is left (errors/warnings);
  2. robotcode static analysis, errors only: via the running helper's warm analyzer (~50 ms) when it is
     reachable, else `robotcode analyze code --severity error` (~1 s warm, 3-5 s cold);
  3. portability: Library/Resource imports that only resolve via ./lib ./resources / -P (rfmcp_skill.portable).
Prints <= ~1 KB of context in the agent's hook format; silent when the file is clean. Never blocks (exit 0).
  claude/codex : {"hookSpecificOutput":{"hookEventName":"PostToolUse","additionalContext":...}}
  copilot      : {"additionalContext": ...}   (top-level; Claude format is not forwarded by Copilot)
  opencode     : plain text (the .opencode plugin appends it to the edit tool's output)
"""
from __future__ import annotations

import contextlib
import io
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

SUFFIXES = {".robot", ".resource"}
LIMIT = 1000
CONFIG = Path(__file__).with_name("data") / "robocop-agent.toml"
SKIP_PARTS = {".rf", ".robotcode_cache", ".robocop_cache", "node_modules", ".venv", ".git"}
SAME_AS_ANALYZER = {"KW05", "ARG08", "IMP07", "IMP09", "KW06"}
EDIT_TOOLS = {"edit", "write", "multiedit", "create", "apply_patch", "patch", "str_replace", "str_replace_editor",
              "insert", "notebookedit", "replace", "write_file", "edit_file"}
FRAME_KW = re.compile(r"No keyword with name '([^']*frame[^']*)' found", re.I)


def _paths_from(obj: Any) -> List[str]:
    out: List[str] = []
    if isinstance(obj, str):
        with contextlib.suppress(json.JSONDecodeError, ValueError):
            obj = json.loads(obj)
    if isinstance(obj, dict):
        for k in ("file_path", "filePath", "path", "file", "target_file"):
            if isinstance(obj.get(k), str):
                out.append(obj[k])
        for k in ("edits", "files", "changes"):
            v = obj.get(k)
            if isinstance(v, list):
                for e in v:
                    out += _paths_from(e)
        text = obj.get("patch") or obj.get("input") or obj.get("command") or obj.get("patchText") or ""
        if isinstance(text, list):
            text = "\n".join(map(str, text))
        if isinstance(text, str):
            out += re.findall(r"^\*\*\* (?:Add|Update) File: (.+?)\s*$", text, flags=re.M)
            out += re.findall(r"^\*\*\* Move to: (.+?)\s*$", text, flags=re.M)
    return out


def edited_files(payload: Dict[str, Any], cwd: Path) -> List[Path]:
    paths: List[str] = []
    for key in ("tool_input", "toolArgs", "args", "input"):
        if key in payload:
            paths += _paths_from(payload[key])
    tool = str(payload.get("tool_name") or payload.get("toolName") or payload.get("tool") or "").lower()
    if not any(p.endswith(tuple(SUFFIXES)) for p in paths) and tool in (
            "apply_patch", "edit", "write", "multiedit", "create", "patch", "str_replace", "insert"):
        now = time.time()  # payload without paths: recently modified RF files under cwd
        for p in cwd.rglob("*"):
            if p.suffix in SUFFIXES and not (SKIP_PARTS & set(p.parts)) and now - p.stat().st_mtime < 90:
                paths.append(str(p))
    out: List[Path] = []
    for p in paths:
        path = Path(p) if os.path.isabs(p) else cwd / p
        if path.suffix in SUFFIXES and path.is_file() and not path.name.startswith("."):
            out.append(path.resolve())
    return list(dict.fromkeys(out))


def find_root(cwd: Path) -> Path:
    env_root = os.environ.get("CLAUDE_PROJECT_DIR")
    if env_root:
        return Path(env_root)
    for parent in [cwd, *cwd.parents]:
        if any((parent / n).exists() for n in ("robot.toml", ".git", "pyproject.toml")):
            return parent
    return cwd


def _robocop(files: List[Path], root: Path, fix: bool) -> list:
    from robocop.run import check_files

    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        return check_files(sources=[str(f) for f in files], root=root, configuration_file=CONFIG, fix=fix,
                           return_result=True, silent=True, skip_gitignore=True, exit_zero=True,
                           cache_dir=root / ".rf" / "robocop_cache")


def _fmt(d: Any, multi: bool) -> str:
    name = Path(str(d.source.path)).name + ":" if multi else ""
    return (f"{name}L{d.range.start.line} {d.severity.value} {d.rule.rule_id} {str(d.message)[:160]}"
            + (" (auto-fixable)" if getattr(d.rule, "fixable", False) else ""))


def robocop_issues(files: List[Path], fix: bool = True, root: Optional[Path] = None) -> List[str]:
    """fix=True: apply robocop's safe fixes first. Returns lines ('auto-fixed: ...' first)."""
    root = root or find_root(files[0].parent)
    wanted = {str(f) for f in files}
    multi = len(files) > 1

    def own(ds: list) -> list:
        return [d for d in ds if str(Path(str(d.source.path)).resolve()) in wanted]

    before = own(_robocop(files, root, fix=False))
    lines: List[str] = []
    if fix and any(getattr(d.rule, "fixable", False) for d in before):
        mtimes = {f: f.stat().st_mtime_ns for f in files}
        _robocop(files, root, fix=True)
        after = own(_robocop(files, root, fix=False))
        left = {(d.rule.rule_id, str(d.source.path)) for d in after}
        fixed = [d for d in before if getattr(d.rule, "fixable", False) and (d.rule.rule_id, str(d.source.path)) not in left]
        if fixed and any(f.stat().st_mtime_ns != mtimes[f] for f in files):
            lines.append("auto-fixed outdated syntax (file rewritten -- re-read it before your next edit): "
                         + "; ".join(sorted({f"L{d.range.start.line} {d.rule.rule_id} {d.rule.name}" for d in fixed}))[:300])
        before = after
    rank = {"E": 0, "W": 1, "I": 2}
    rows = sorted([d for d in before if str(d.severity.value) in ("E", "W")],
                  key=lambda d: (rank.get(str(d.severity.value), 3), d.range.start.line))
    return lines + [_fmt(d, multi) for d in rows]


def analyzer_errors(files: List[Path], root: Path) -> Tuple[List[str], str]:
    """-> (lines, source) using the live helper when reachable, else the robotcode CLI."""
    try:
        from . import fast

        sd = os.environ.get("RFMCP_DIR") or str(root / ".rf")
        ep = fast.endpoint(sd)
        if ep:
            out: List[str] = []
            for f in files:
                buf = fast.send(ep, {"op": "analyze", "path": str(f), "timeout": 6}, 10)
                r = json.loads(buf)
                if r.get("ok") is None:
                    raise TimeoutError("helper busy")
                for d in r.get("errors", []):
                    pre = f.name + ":" if len(files) > 1 else ""
                    out.append(f"{pre}L{d['line']}:{d['col']} {d['code']}: {d['msg'][:200]}")
            return out, "helper"
    except Exception:
        pass
    rc_bin = Path(sys.executable).with_name("robotcode")
    try:
        r = subprocess.run([str(rc_bin), "analyze", "code", "--severity", "error", *map(str, files)],
                           cwd=str(root), capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.TimeoutExpired):
        return [], "none"
    out = []
    for line in (r.stdout or "").splitlines():
        m = re.match(r"^(.*?):(\d+):(\d+): \[ERROR\] (\w+): (.*)$", line)
        if m:
            pre = Path(m.group(1)).name + ":" if len(files) > 1 else ""
            out.append(f"{pre}L{m.group(2)}:{m.group(3)} {m.group(4)}: {m.group(5)[:200]}")
    return out, "cli"


def run_checks(files: List[Path], root: Path) -> str:
    try:
        rc_lines = robocop_issues(files, fix=True, root=root)
    except Exception as e:  # robocop missing/broken: analyzer only
        rc_lines = [f"(robocop failed: {type(e).__name__})"]
    an, _src = analyzer_errors(files, root)
    err_lines = {int(m.group(1)) for m in (re.search(r"L(\d+)", a) for a in an) if m}
    fixed = [l for l in rc_lines if l.startswith("auto-fixed")]
    rest = [l for l in rc_lines if not l.startswith("auto-fixed")]
    rest = [l for l in rest if not (re.search(r"L(\d+) E (\w+)", l) and int(re.search(r"L(\d+)", l).group(1)) in err_lines
                                    and re.search(r" E (\w+)", l).group(1) in SAME_AS_ANALYZER)]
    port: List[str] = []
    try:
        from .portable import lines as portable_lines

        for f in files:
            port += [(f.name + ":" if len(files) > 1 else "") + x for x in portable_lines(f, root)]
    except Exception:
        pass
    if port:  # the import error the analyzer may also report on that line is the same problem
        plines = {m.group(1) for m in (re.match(r"(?:\S+:)?L(\d+) ", x) for x in port) if m}
        an = [a for a in an if not (re.search(r"L(\d+)", a) and re.search(r"L(\d+)", a).group(1) in plines)]
    if not (fixed or rest or an or port):
        return ""
    names = ", ".join(os.path.relpath(f, root) for f in files)
    parts = [f"Robot Framework check of {names} (rfmcp post-edit hook):"]
    parts += fixed
    if port:
        parts.append("NOT PORTABLE (the final plain `robot` run fails on these imports):")
        parts += port[:5]
    if an:
        parts.append("ERRORS (will fail at run time; fix before running):")
        parts += an[:10]
        fr = next((m.group(1) for m in (FRAME_KW.search(a) for a in an) if m), None)
        if fr and any("Browser" in f.read_text(errors="replace") for f in files):
            parts.append(f"HINT: Browser library has no '{fr}' keyword (no frame switching). Address elements inside "
                         "an iframe directly: `Fill Text    id=<frame id> >>> id=<field id>    text` (frame selector, >>>, "
                         "inner selector). See: rfmcp guide browser")
        elif any("KeywordNotFound" in a for a in an):
            parts.append("HINT: find the right keyword with `rfmcp search \"what it should do\"` / `rfmcp doc \"Name\"`")
    if rest:
        parts.append("robocop:")
        parts += rest[:8]
    text = "\n".join(parts)
    if len(text) > LIMIT:
        text = text[: LIMIT - 40].rsplit("\n", 1)[0] + "\n... (more: rfmcp check FILE)"
    return text


def main(argv: List[str]) -> int:
    agent = argv[argv.index("--agent") + 1] if "--agent" in argv else "claude"
    raw = sys.stdin.read() if not sys.stdin.isatty() else ""
    try:
        payload = json.loads(raw) if raw.strip() else {}
    except ValueError:
        payload = {}
    cwd = Path(payload.get("cwd") or os.getcwd())
    tool = str(payload.get("tool_name") or payload.get("toolName") or payload.get("tool") or "")
    if tool and tool.lower() not in EDIT_TOOLS:  # read-only tools (view/read/grep/bash) -> nothing to check
        return 0
    files = edited_files(payload, cwd)
    if os.environ.get("RFMCP_HOOK_LOG"):
        with open(os.environ["RFMCP_HOOK_LOG"], "a") as f:
            f.write(json.dumps({"t": time.time(), "agent": agent, "keys": sorted(payload)[:12],
                                "tool": payload.get("tool_name") or payload.get("toolName") or payload.get("tool"),
                                "files": [str(x) for x in files]}) + "\n")
    if not files:
        return 0
    try:
        text = run_checks(files, find_root(cwd))
    except Exception as e:  # never break the agent loop
        sys.stderr.write(f"rfmcp hook failed: {e!r}\n")
        return 0
    if not text:
        return 0
    if agent == "copilot":
        print(json.dumps({"additionalContext": text}))
    elif agent == "opencode":
        print(text)
    else:
        print(json.dumps({"hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": text}}))
    return 0
