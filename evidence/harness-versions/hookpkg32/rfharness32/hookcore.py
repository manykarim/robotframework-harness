"""Hook-side helpers. STDLIB ONLY: imported by hook.py, which runs as `python -S hook.py` (no site, ~30 ms start).

payloads (Claude / Codex / Copilot / OpenCode shapes) -> edited files + proposed content (Write, Edit, MultiEdit,
apply_patch, str_replace, create), daemon start/ensure/request, session store, output.xml summary, rendering.
"""
from __future__ import annotations

import contextlib
import difflib
import fcntl
import hashlib
import json
import os
import re
import shlex
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

PKG_ROOT = Path(__file__).resolve().parent.parent       # hookpkg/ (contains rfharness32/)
RF_SUFFIXES = (".robot", ".resource")
TEST_HEADER = re.compile(r"^\*+\s*(test\s*cases?|tasks?)\s*\**\s*$", re.I | re.M)
SKIP_DIRS = {".rf", ".git", ".venv", "venv", "node_modules", "__pycache__", "results", "output", ".robotcode_cache",
             ".robocop_cache", "grader_out", "browser"}
EDIT_TOOLS = {"write", "edit", "multiedit", "create", "apply_patch", "patch", "str_replace", "str_replace_editor",
              "insert", "edit_file", "write_file", "replace", "multi_edit"}
SHELL_TOOLS = {"bash", "shell", "exec_command", "local_shell", "run_in_terminal", "command_execution", "terminal"}


def env_f(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, default))
    except ValueError:
        return default


BUDGET = env_f("RFH32_BUDGET", 90.0)          # max seconds a PostToolUse hook waits for live results
GATE_TIMEOUT = env_f("RFH32_GATE_TIMEOUT", 2.5)
IDLE_EXIT = env_f("RFH32_IDLE_EXIT", 1200.0)
MAX_CTX = int(env_f("RFH32_MAX_CONTEXT", 2048))


# ------------------------------------------------------------------------------------------------ roots / dirs
def find_root(payload: Dict[str, Any]) -> Path:
    env_root = os.environ.get("RFH32_ROOT") or os.environ.get("CLAUDE_PROJECT_DIR")
    if env_root and Path(env_root).is_dir():
        return Path(env_root).resolve()
    cwd = Path(payload.get("cwd") or os.getcwd()).resolve()
    for p in [cwd, *list(cwd.parents)[:6]]:          # an already-initialized parent wins (agent cd'ed into tests/)
        if (p / ".rf" / "hook32").is_dir():
            return p
    return cwd


class Dirs:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.rf = root / ".rf"
        self.exec = self.rf / "exec32"
        self.lint = self.rf / "lint32"
        self.docs = self.rf / "docs"
        self.state = self.rf / "state"
        self.hook = self.rf / "hook32"
        self.snap = self.hook / "snap"

    def make(self) -> "Dirs":
        for d in (self.rf, self.hook, self.snap, self.state):
            d.mkdir(parents=True, exist_ok=True)
        gi = self.rf / ".gitignore"
        if not gi.exists():
            gi.write_text("*\n")
        return self


def rel(path: Path, root: Path) -> str:
    try:
        return os.path.relpath(path, root)
    except ValueError:
        return str(path)


def sha(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8", "replace")).hexdigest()[:16]


def read(path: Path) -> Optional[str]:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


def is_test_file(path: Path, text: Optional[str] = None) -> bool:
    if path.suffix != ".robot" or path.name.startswith("."):
        return False
    text = read(path) if text is None else text
    return bool(text and TEST_HEADER.search(text))


def rf_files(root: Path, limit: int = 300) -> List[Path]:
    out: List[Path] = []
    for dp, dns, fns in os.walk(root):
        dns[:] = [d for d in dns if d not in SKIP_DIRS and not d.startswith(".")]
        for fn in fns:
            if fn.endswith(RF_SUFFIXES) and not fn.startswith("."):
                out.append(Path(dp) / fn)
                if len(out) >= limit:
                    return out
    return out


# ------------------------------------------------------------------------------------------------ payloads
def tool_name(p: Dict[str, Any]) -> str:
    return str(p.get("tool_name") or p.get("toolName") or p.get("tool") or "")


def tool_input(p: Dict[str, Any]) -> Dict[str, Any]:
    for k in ("tool_input", "toolArgs", "args", "input"):
        v = p.get(k)
        if isinstance(v, str):
            if "*** Begin Patch" in v and not v.lstrip().startswith("{"):
                return {"command": v, "_raw_patch": True}     # copilot apply_patch: toolArgs = raw patch text
            with contextlib.suppress(ValueError):
                v = json.loads(v)
        if isinstance(v, dict):
            return v
    return {}


def make_patch(path_str: str, old: Optional[str], new: str) -> str:
    """V4A apply_patch text turning `old` into `new` (Add File when old is None; context hunks otherwise)."""
    nl = new.rstrip("\n").split("\n")
    if old is None:
        return "*** Begin Patch\n*** Add File: %s\n%s\n*** End Patch" % (path_str, "\n".join("+" + l for l in nl))
    ol = old.rstrip("\n").split("\n")
    body: List[str] = []
    for group in difflib.SequenceMatcher(None, ol, nl, autojunk=False).get_grouped_opcodes(3):
        body.append("@@")
        for tag, i1, i2, j1, j2 in group:
            if tag == "equal":
                body += [" " + l for l in ol[i1:i2]]
            else:
                body += ["-" + l for l in ol[i1:i2]]
                body += ["+" + l for l in nl[j1:j2]]
    return "*** Begin Patch\n*** Update File: %s\n%s\n*** End Patch" % (path_str, "\n".join(body))


def _abs(p: str, cwd: Path) -> Path:
    q = Path(os.path.expanduser(p))
    return (q if q.is_absolute() else cwd / q).resolve()


def _first(d: Dict[str, Any], *keys: str) -> Optional[str]:
    for k in keys:
        v = d.get(k)
        if isinstance(v, str):
            return v
    return None


def patch_text(inp: Dict[str, Any]) -> Optional[str]:
    for k in ("command", "patch", "patchText", "input"):
        v = inp.get(k)
        if isinstance(v, list):  # codex local_shell form ["apply_patch", "*** Begin Patch ..."]
            v = next((x for x in v if isinstance(x, str) and "*** Begin Patch" in x), None)
        if isinstance(v, str) and "*** Begin Patch" in v:
            return v
    return None


def parse_patch(text: str) -> List[Dict[str, Any]]:
    """apply_patch (Codex/OpenCode) envelope -> [{op: add|update|delete, path, move_to, hunks|lines}]"""
    files: List[Dict[str, Any]] = []
    cur: Optional[Dict[str, Any]] = None
    for line in text.splitlines():
        m = re.match(r"^\*\*\* (Add|Update|Delete) File: (.+?)\s*$", line)
        if m:
            cur = {"op": m.group(1).lower(), "path": m.group(2), "lines": [], "hunks": [], "move_to": None}
            files.append(cur)
            continue
        if line.startswith("*** End Patch") or line.startswith("*** Begin Patch"):
            cur = None if line.startswith("*** End") else cur
            continue
        if cur is None:
            continue
        m = re.match(r"^\*\*\* Move to: (.+?)\s*$", line)
        if m:
            cur["move_to"] = m.group(1)
            continue
        if line.startswith("*** End of File"):
            continue
        if cur["op"] == "add":
            if line.startswith("+"):
                cur["lines"].append(line[1:])
            continue
        if cur["op"] == "update":
            if line.startswith("@@"):
                cur["hunks"].append([])
                continue
            if not cur["hunks"]:
                cur["hunks"].append([])
            if line[:1] in (" ", "+", "-"):
                cur["hunks"][-1].append((line[:1], line[1:]))
            elif line == "":
                cur["hunks"][-1].append((" ", ""))
    return files


def apply_hunks(text: str, hunks: List[List[Tuple[str, str]]]) -> Optional[str]:
    lines = text.split("\n")
    pos = 0
    for h in hunks:
        old = [t for k, t in h if k in (" ", "-")]
        new = [t for k, t in h if k in (" ", "+")]
        if not old:
            lines[pos:pos] = new
            pos += len(new)
            continue
        idx = None
        for norm in (lambda s: s, lambda s: s.rstrip(), lambda s: s.strip()):
            target = [norm(x) for x in old]
            for i in range(pos, len(lines) - len(old) + 1):
                if [norm(x) for x in lines[i:i + len(old)]] == target:
                    idx = i
                    break
            if idx is not None:
                break
        if idx is None:
            return None
        lines[idx:idx + len(old)] = new
        pos = idx + len(new)
    return "\n".join(lines)


class Proposed:
    """One RF file an edit tool is about to change."""

    def __init__(self, path: Path, current: Optional[str], new: Optional[str], kind: str, edit: Optional[dict] = None):
        self.path, self.current, self.new, self.kind, self.edit = path, current, new, kind, edit


def proposed_edits(tool: str, inp: Dict[str, Any], cwd: Path) -> List[Proposed]:
    """-> files (RF only) with current + proposed content. new=None when it cannot be computed."""
    t = tool.lower()
    out: List[Proposed] = []
    pt = patch_text(inp)
    if pt is not None:
        for f in parse_patch(pt):
            path = _abs(f["path"], cwd)
            dest = _abs(f["move_to"], cwd) if f.get("move_to") else path
            if not (str(path).endswith(RF_SUFFIXES) or str(dest).endswith(RF_SUFFIXES)):
                continue
            cur = read(path)
            if f["op"] == "add":
                out.append(Proposed(dest, read(dest), "\n".join(f["lines"]) + "\n", "patch"))
            elif f["op"] == "update":
                new = apply_hunks(cur, f["hunks"]) if cur is not None else None
                out.append(Proposed(dest, cur, new, "patch"))
        return out
    fp = _first(inp, "file_path", "filePath", "path", "file", "target_file", "filename")
    if not fp or not fp.endswith(RF_SUFFIXES):
        return out
    path = _abs(fp, cwd)
    cur = read(path)
    content = _first(inp, "content", "file_text", "text", "contents")
    cmd = str(inp.get("command") or "").lower()
    if t in ("write", "create", "write_file") or (content is not None and "old_string" not in inp
                                                  and "oldString" not in inp and "old_str" not in inp
                                                  and cmd in ("", "create")):
        out.append(Proposed(path, cur, content, "write"))
        return out
    edits = inp.get("edits")
    if isinstance(edits, list) and edits:  # MultiEdit
        new = cur
        for e in edits:
            if new is None or not isinstance(e, dict):
                new = None
                break
            o = _first(e, "old_string", "oldString", "old_str")
            n = _first(e, "new_string", "newString", "new_str") or ""
            if o is None or (o and o not in new):
                new = None
                break
            new = new.replace(o, n) if e.get("replace_all") or e.get("replaceAll") else new.replace(o, n, 1)
        out.append(Proposed(path, cur, new, "multiedit"))
        return out
    o = _first(inp, "old_string", "oldString", "old_str")
    n = _first(inp, "new_string", "newString", "new_str")
    if cmd == "insert" and n is not None and cur is not None:
        try:
            at = int(inp.get("insert_line") or 0)
        except (TypeError, ValueError):
            at = 0
        ls = cur.split("\n")
        ls[at:at] = n.split("\n")
        out.append(Proposed(path, cur, "\n".join(ls), "insert"))
        return out
    if o is not None and cur is not None:
        if o and o not in cur:
            out.append(Proposed(path, cur, None, "edit"))
        else:
            ra = bool(inp.get("replace_all") or inp.get("replaceAll"))
            new = cur.replace(o, n or "") if ra else cur.replace(o, n or "", 1)
            out.append(Proposed(path, cur, new, "edit", {"old": o, "new": n or "", "all": ra,
                                                          "keys": [k for k in ("old_string", "oldString", "old_str")
                                                                   if k in inp][:1] +
                                                                  [k for k in ("new_string", "newString", "new_str")
                                                                   if k in inp][:1]}))
        return out
    out.append(Proposed(path, cur, None, t or "edit"))
    return out


def edited_rf_files(tool: str, inp: Dict[str, Any], cwd: Path, response: Any = None) -> List[Path]:
    """PostToolUse: RF files the tool changed (paths from input; apply_patch from the patch text)."""
    paths: List[Path] = []
    pt = patch_text(inp)
    if pt is not None:
        for f in parse_patch(pt):
            if f["op"] == "delete":
                continue
            p = _abs(f.get("move_to") or f["path"], cwd)
            if str(p).endswith(RF_SUFFIXES):
                paths.append(p)
    else:
        fp = _first(inp, "file_path", "filePath", "path", "file", "target_file", "filename")
        if fp and fp.endswith(RF_SUFFIXES):
            paths.append(_abs(fp, cwd))
    if not paths and isinstance(response, (str, dict)):   # tool response lists the files (codex: "M path")
        s = response if isinstance(response, str) else json.dumps(response)
        for m in re.finditer(r"(?m)^[AM] (\S+\.(?:robot|resource))\s*$", s):
            paths.append(_abs(m.group(1), cwd))
    return [p for p in dict.fromkeys(paths) if p.is_file() and not p.name.startswith(".")]


def shell_command(tool: str, inp: Dict[str, Any]) -> Optional[str]:
    if tool.lower() not in SHELL_TOOLS and "command" not in inp:
        return None
    c = inp.get("command") or inp.get("cmd")
    if isinstance(c, list):
        c = " ".join(map(str, c))
    return c if isinstance(c, str) and "*** Begin Patch" not in c else None


_ROBOT_RE = re.compile(r"(?:^|[\s;&|(/\"'`])(?:robot|robotcode(?:\s+--?\S+)*\s+robot|python3?\s+-m\s+robot)(?:\s|$)")


def robot_invocations(cmd: str) -> List[List[str]]:
    """shell command -> argv lists of plain robot runs (no --dryrun, no rebot / robotcode results)."""
    out = []
    for part in re.split(r"&&|\|\||;|\n|\|", cmd):
        part = part.strip()
        if not _ROBOT_RE.search(" " + part):
            continue
        try:
            argv = shlex.split(part)
        except ValueError:
            argv = part.split()
        idx = None
        for i, a in enumerate(argv):
            b = os.path.basename(a)
            if b == "robot" or (b == "robot" and i and argv[i - 1] == "-m"):
                idx = i
                break
        if idx is None:
            continue
        args = argv[idx + 1:]
        if "--dryrun" in args or any(a in ("--version", "--help", "-h") for a in args):
            continue
        out.append(args)
    return out


def output_xml_for(args: List[str], cwd: Path) -> Optional[Path]:
    outdir, output = None, "output.xml"
    i = 0
    while i < len(args):
        a = args[i]
        nxt = args[i + 1] if i + 1 < len(args) else None
        if a in ("-d", "--outputdir") and nxt:
            outdir, i = nxt, i + 2
            continue
        if a.startswith("--outputdir="):
            outdir = a.split("=", 1)[1]
        elif a in ("-o", "--output") and nxt:
            output, i = nxt, i + 2
            continue
        elif a.startswith("--output="):
            output = a.split("=", 1)[1]
        i += 1
    if output.upper() == "NONE":
        return None
    o = Path(output)
    if not o.is_absolute():
        o = _abs(outdir, cwd) / o if outdir else cwd / o
    return o


def newest_output_xml(root: Path, since: float) -> Optional[Path]:
    best = None
    for dp, dns, fns in os.walk(root):
        dns[:] = [d for d in dns if d not in (".rf", ".git", ".venv", "node_modules") and not d.startswith(".")]
        if dp.count(os.sep) - str(root).count(os.sep) > 4:
            dns[:] = []
        for fn in fns:
            if fn.endswith(".xml") and "output" in fn:
                p = Path(dp) / fn
                try:
                    m = p.stat().st_mtime
                except OSError:
                    continue
                if m >= since and (best is None or m > best[0]):
                    best = (m, p)
    return best[1] if best else None


# ------------------------------------------------------------------------------------------------ output.xml
def summarize_output(xml: Path) -> Optional[Dict[str, Any]]:
    """stdlib parse of a robot output.xml -> {total, passed, failed, skipped, by_source{}, failures[]}"""
    import xml.etree.ElementTree as ET

    try:
        tree = ET.parse(str(xml))
    except Exception as e:
        return {"error": f"cannot parse {xml.name}: {e}"}
    root = tree.getroot()
    res: Dict[str, Any] = {"total": 0, "passed": 0, "failed": 0, "skipped": 0, "by_source": {}, "failures": []}

    def status(el):
        st = el.find("status")
        return (st.get("status") if st is not None else None), ((st.text or "").strip() if st is not None else "")

    def fail_kw(el, depth=0):
        for ch in el:
            if ch.tag in ("kw", "for", "if", "try", "while", "group", "iter", "branch"):
                s, m = status(ch)
                if s == "FAIL":
                    name = ch.get("name") or ch.tag.upper()
                    lib = ch.get("owner") or ch.get("library") or ""
                    args = [a.text or "" for a in ch.findall("arg")][:4]
                    inner = fail_kw(ch, depth + 1) if depth < 6 else None
                    return {"kw": name, "lib": lib, "args": args, "msg": m[:300],
                            **({"inner": inner} if inner and inner.get("kw") != name else {})}
        return None

    def walk(suite, src):
        src = suite.get("source") or src
        for ch in suite:
            if ch.tag == "suite":
                walk(ch, src)
            elif ch.tag == "test":
                s, m = status(ch)
                res["total"] += 1
                key = {"PASS": "passed", "FAIL": "failed", "SKIP": "skipped"}.get(s or "", "failed")
                res[key] += 1
                bs = res["by_source"].setdefault(src or "?", {"total": 0, "failed": 0, "passed": 0})
                bs["total"] += 1
                bs["failed" if key == "failed" else "passed"] += 1 if key != "skipped" else 0
                if key == "failed":
                    setup = None
                    res["failures"].append({"test": ch.get("name"), "source": src, "line": ch.get("line"),
                                            "msg": m[:500], "kw": fail_kw(ch), **({"setup": setup} if setup else {})})
            elif ch.tag in ("kw",) and ch.get("type") in ("SETUP", "TEARDOWN"):
                s, m = status(ch)
                if s == "FAIL":
                    res.setdefault("suite_errors", []).append({"source": src, "type": ch.get("type"),
                                                              "kw": ch.get("name"), "msg": m[:300]})

    for s in root.findall("suite"):
        walk(s, None)
    errs = root.find("errors")
    if errs is not None:
        res["errors"] = [(m.text or "")[:200] for m in errs.findall("msg") if m.get("level") == "ERROR"][:3]
    return res


# ------------------------------------------------------------------------------------------------ session store
class Store:
    """.rf/hook32/session.json under an flock: edited files, verified hashes, stop-gate counters, pending jobs."""

    def __init__(self, d: Dirs) -> None:
        self.path = d.hook / "session.json"
        self.lock_path = d.hook / "session.lock"
        self._fd: Optional[int] = None
        self.data: Dict[str, Any] = {}

    def __enter__(self) -> "Store":
        self._fd = os.open(self.lock_path, os.O_CREAT | os.O_RDWR, 0o600)
        fcntl.flock(self._fd, fcntl.LOCK_EX)
        try:
            self.data = json.loads(self.path.read_text())
        except (OSError, ValueError):
            self.data = {}
        return self

    def __exit__(self, *exc: Any) -> None:
        try:
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(self.data, default=str))
            os.replace(tmp, self.path)
        finally:
            if self._fd is not None:
                fcntl.flock(self._fd, fcntl.LOCK_UN)
                os.close(self._fd)


def snapshot_path(d: Dirs, path: Path) -> Path:
    return d.snap / (hashlib.sha1(str(path).encode()).hexdigest()[:16] + ".txt")


def save_snapshot(d: Dirs, path: Path, text: Optional[str]) -> None:
    if text is None:
        return
    p = snapshot_path(d, path)
    tmp = p.with_suffix(".tmp%d" % os.getpid())
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, p)


def load_snapshot(d: Dirs, path: Path) -> Optional[str]:
    return read(snapshot_path(d, path))


# ------------------------------------------------------------------------------------------------ daemons
try:                                    # package import (daemons): no sys.path change
    from . import procs, proto
except ImportError:                     # `python -S hook.py`: stdlib-only copies imported by file name
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import procs  # type: ignore  # noqa: E402
    import proto  # type: ignore  # noqa: E402

DAEMON_MODULE = {"exec": "rfharness32.execd", "lint": "rfharness32.lintd"}


def _ancestors(pid: int) -> List[Tuple[int, str]]:
    """[(pid, comm + ' ' + argv0/1 basenames)] from pid upwards."""
    out = []
    for _ in range(12):
        try:
            with open(f"/proc/{pid}/stat") as f:
                data = f.read()
            comm = data[data.index("(") + 1:data.rindex(")")]
            ppid = int(data.rsplit(")", 1)[1].split()[1])
            with open(f"/proc/{pid}/cmdline", "rb") as f:
                argv = [a.decode(errors="replace") for a in f.read().split(b"\0")[:2] if a]
        except (OSError, ValueError, IndexError):
            break
        out.append((pid, " ".join([comm] + [os.path.basename(a) for a in argv])))
        if ppid <= 1:
            break
        pid = ppid
    return out


_SKIP_COMM = re.compile(r"^(sh|bash|dash|zsh|fish|env|timeout|nohup|setsid|stdbuf|uv|uvx|python[\d.]*|sudo|script)$")
_AGENT_COMM = re.compile(r"(claude|codex|opencode|copilot|node|bun|cursor|gemini|MainThread)", re.I)


def agent_pid() -> int:
    """The agent process that runs this hook (first ancestor that is not a shell/python); 0 = do not watch."""
    if os.environ.get("RFH32_WATCH_PID"):
        try:
            return int(os.environ["RFH32_WATCH_PID"])
        except ValueError:
            return 0
    for pid, desc in _ancestors(os.getppid()):
        if _SKIP_COMM.match(desc.split(" ")[0]):
            continue
        return pid if _AGENT_COMM.search(desc) else 0
    return 0


def daemon_state(d: Dirs, kind: str) -> Optional[Dict[str, Any]]:
    sd = d.exec if kind == "exec" else d.lint
    st = proto.read_state(sd)
    if st and proto.pid_alive(st.get("pid")) and not st.get("stopped"):
        return st
    return None


def _python() -> str:
    return os.environ.get("RFH32_PYTHON") or sys.executable


def start_daemon(d: Dirs, kind: str, wait: float = 0.0) -> Optional[Dict[str, Any]]:
    """Idempotent, detached. wait>0: block until ready (or timeout). Returns the state when ready."""
    sd = d.exec if kind == "exec" else d.lint
    sd.mkdir(parents=True, exist_ok=True)
    lock = os.open(d.hook / f"start-{kind}.lock", os.O_CREAT | os.O_RDWR, 0o600)
    try:
        fcntl.flock(lock, fcntl.LOCK_EX)
        st = daemon_state(d, kind)
        starting = sd / "starting.pid"
        try:                       # a daemon launched moment ago may not have written its state yet
            spid = int(starting.read_text())
            fresh = time.time() - starting.stat().st_mtime < 90 and proto.pid_alive(spid)
        except (OSError, ValueError):
            fresh = False
        if st is None and not fresh:
            old = proto.read_state(sd) or {}
            if old.get("token_env"):     # leftovers of a killed daemon (kill -9): its children carry the token
                left = procs.token_procs(old["token_env"])
                if left:
                    procs.terminate(left, grace=1.0)
            with contextlib.suppress(OSError):
                (sd / proto.STATE_NAME).unlink()
            env = dict(os.environ)
            env[procs.TOKEN_ENV] = os.urandom(8).hex()
            env["PYTHONPATH"] = str(PKG_ROOT) + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
            env.setdefault("PYTHONUNBUFFERED", "1")
            for k in ("PYTHONSTARTUP", "PYTHONSAFEPATH"):
                env.pop(k, None)
            cmd = [_python(), "-m", DAEMON_MODULE[kind], "--dir", str(sd), "--root", str(d.root),
                   "--watch-pid", str(agent_pid()), "--idle", str(IDLE_EXIT)]
            with open(sd / "daemon.log", "ab") as log:
                p = subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT, env=env,
                                     start_new_session=True, close_fds=True, cwd=str(d.root))
            with open(starting, "w") as f:
                f.write(str(p.pid))
    finally:
        fcntl.flock(lock, fcntl.LOCK_UN)
        os.close(lock)
    if wait <= 0:
        return daemon_state(d, kind)
    t_end = time.monotonic() + wait
    while time.monotonic() < t_end:
        st = proto.read_state(sd)
        if st and st.get("ready") and proto.pid_alive(st.get("pid")):
            return st
        if st and st.get("stopped"):
            return None
        time.sleep(0.05)
    return None


def request(st: Dict[str, Any], req: Dict[str, Any], timeout: float) -> Dict[str, Any]:
    try:
        return proto.request(st, req, timeout=timeout)
    except Exception as e:
        return {"ok": False, "error": f"daemon not reachable: {type(e).__name__}: {e}"[:300], "unreachable": True}


def stop_daemons(d: Dirs, wait: float = 2.0) -> Dict[str, Any]:
    info: Dict[str, Any] = {}
    sts = {}
    for kind in ("exec", "lint"):
        st = daemon_state(d, kind)
        if st:
            sts[kind] = st
            r = request(st, {"op": "stop", "graceful": True}, timeout=2)
            if r.get("unreachable"):
                with contextlib.suppress(OSError):
                    os.kill(st["pid"], 15)
    t_end = time.monotonic() + wait
    while time.monotonic() < t_end and any(proto.pid_alive(s["pid"]) for s in sts.values()):
        time.sleep(0.05)
    for kind, st in sts.items():
        info[kind] = "stopped" if not proto.pid_alive(st["pid"]) else "stopping"
    return info


def cleanup_gen_files(root: Path) -> int:
    n = 0
    for dp, dns, fns in os.walk(root):
        dns[:] = [x for x in dns if x not in SKIP_DIRS and not x.startswith(".")]
        for fn in fns:
            if fn.startswith(".") and (fn.endswith(".live.resource") or ".rfh-gate" in fn):
                with contextlib.suppress(OSError):
                    os.unlink(os.path.join(dp, fn))
                    n += 1
    return n


# ------------------------------------------------------------------------------------------------ rendering
class Result:
    """kind: none | context | deny | rewrite | block"""

    def __init__(self, kind: str = "none", text: str = "", updated: Optional[Dict[str, Any]] = None) -> None:
        self.kind, self.text, self.updated = kind, text, updated


def clip(text: str, n: int = MAX_CTX) -> str:
    if len(text) <= n:
        return text
    cut = text[: n - 30]
    return cut[: cut.rfind("\n")] + "\n... (truncated)"


CLAUDE_EVENTS = {"session-start": "SessionStart", "pre-tool": "PreToolUse", "post-tool": "PostToolUse",
                 "stop": "Stop", "session-end": "SessionEnd", "prompt": "UserPromptSubmit"}
AGENT_MAX_CTX = {"opencode": int(env_f("RFH32_MAX_CONTEXT_OPENCODE", 1200))}


def render(agent: str, event: str, r: Result, payload: Dict[str, Any]) -> str:
    if r.kind == "none" or (not r.text and r.kind not in ("rewrite",)):
        return ""
    ev = CLAUDE_EVENTS.get(event, event)
    if payload.get("hook_event_name") in ("PostToolUse", "PostToolUseFailure"):
        ev = payload["hook_event_name"]
    text = clip(r.text, AGENT_MAX_CTX.get(agent, MAX_CTX))
    if agent == "opencode":     # the JS plugin interprets this
        return json.dumps({"action": r.kind, "text": text, **({"args": r.updated} if r.updated else {})})
    if agent == "copilot":
        if r.kind == "deny":
            return json.dumps({"permissionDecision": "deny", "permissionDecisionReason": text})
        if r.kind == "rewrite":
            mod = r.updated
            if isinstance(mod, dict) and mod.get("_raw_patch"):
                mod = mod.get("command")
            return json.dumps({"permissionDecision": "allow", "modifiedArgs": mod,
                               **({"additionalContext": text} if text else {})})
        if r.kind == "block":
            return json.dumps({"decision": "block", "reason": text})
        return json.dumps({"additionalContext": text})
    # claude + codex (codex 0.161 accepts the Claude hook wire format)
    if r.kind == "deny":
        return json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
                                                  "permissionDecisionReason": text}})
    if r.kind == "rewrite":
        mode = str(payload.get("permission_mode") or "")
        dec = "allow" if mode in ("bypassPermissions", "acceptEdits", "dontAsk") or agent == "codex" else "ask"
        up = {k: v for k, v in (r.updated or {}).items() if not k.startswith("_")}
        out = {"hookEventName": "PreToolUse", "permissionDecision": dec, "permissionDecisionReason": text,
               "updatedInput": up}
        if text:
            out["additionalContext"] = text
        return json.dumps({"hookSpecificOutput": out})
    if r.kind == "block":
        return json.dumps({"decision": "block", "reason": text})
    return json.dumps({"hookSpecificOutput": {"hookEventName": ev, "additionalContext": text}})


def log_event(d: Dirs, rec: Dict[str, Any]) -> None:
    path = os.environ.get("RFH32_HOOK_LOG") or str(d.hook / "hooks.jsonl")
    try:
        with open(path, "a") as f:
            f.write(json.dumps({"ts": round(time.time(), 3), **rec}, default=str) + "\n")
    except OSError:
        pass


def changed_line_numbers(old: Optional[str], new: str) -> Optional[List[int]]:
    if old is None:
        return None
    a = [x.rstrip() for x in old.splitlines()]
    b = [x.rstrip() for x in new.splitlines()]
    out: List[int] = []
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
        if tag in ("replace", "insert"):
            out.extend(range(j1 + 1, j2 + 1))
        elif tag == "delete":
            out.extend(x for x in (j1, j1 + 1) if 1 <= x <= max(len(b), 1))
    return sorted(set(out))
