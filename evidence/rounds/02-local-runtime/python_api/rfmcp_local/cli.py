"""Fast client CLI. STDLIB ONLY (no robot/robotcode import) except `batch` and in-process paths.

  python -m rfmcp_local start [--dir .rf] [--python PY] [--wrapper "xvfb-run -a"] [daemon opts...]
  python -m rfmcp_local step '<cell>' ['<cell2>' ...] [--timeout S] [--text]
  python -m rfmcp_local vars [NAME ...] [--all]
  python -m rfmcp_local status | interrupt | stop [--timeout 30] | cleanup | build [-o FILE]
  python -m rfmcp_local batch FILE|- [daemon opts]        (in-process, no daemon)
"""
from __future__ import annotations

import json
import os
import shlex
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from . import procs, proto


def _out(obj: Dict[str, Any], text: bool = False) -> None:
    if not text:
        sys.stdout.write(json.dumps(obj, separators=(",", ":"), default=str) + "\n")
        return
    for s in obj.get("steps", []):
        line = f"{s.get('status', '?'):7} {s.get('kw')}  {'  '.join(s.get('args', []))}"
        if "ret" in s:
            line += f"  -> {s['ret']}"
        if "msg" in s:
            line += f"\n        {s['msg']}"
        if "refused" in s:
            line += f"\n        refused: {json.dumps(s['refused'])}"
        sys.stdout.write(line + "\n")
    for k in ("errors", "console", "error", "vars"):
        if k in obj:
            sys.stdout.write(f"{k}: {json.dumps(obj[k])}\n")


def _live_state(d: Path) -> Optional[Dict[str, Any]]:
    st = proto.read_state(d)
    if st and proto.pid_alive(st.get("pid")) and st.get("ready") is not None and not st.get("stopped"):
        return st
    return None


def cleanup(d: Path, quiet: bool = False) -> Dict[str, Any]:
    """Kill leftovers of a dead helper (e.g. after kill -9): every process carrying its token."""
    st = proto.read_state(d) or {}
    if st.get("pid") and proto.pid_alive(st["pid"]) and not st.get("stopped"):
        return {"ok": False, "error": "helper alive; use stop", "pid": st["pid"]}
    tok = st.get("token_env")
    left = procs.token_procs(tok) if tok else []
    forced = procs.terminate(left) if left else []
    if st.get("transport") == "unix" and st.get("sock"):
        try:
            os.unlink(st["sock"])
        except OSError:
            pass
    return {"ok": True, "killed": len(left), "forced": len(forced)}


def start(d: Path, argv: List[str], daemon_cmd: Optional[List[str]] = None) -> int:
    """daemon_cmd: command prefix that runs the daemon in the foreground (default: python -m rfmcp_local.daemon;
    the robotcode plugin passes `python -m robotcode.cli [-p ..] [--wrapper ..] rfmcp-serve`)."""
    python, wrapper, rest = sys.executable, None, []
    it = iter(argv)
    for a in it:
        if a == "--python":
            python = next(it)
        elif a == "--wrapper":
            wrapper = next(it)
        else:
            rest.append(a)
    if _live_state(d):
        st = proto.read_state(d)
        _out({"ok": True, "already_running": True, "pid": st["pid"]})
        return 0
    cl = cleanup(d)
    proto.ensure_private_dir(d)
    t0 = time.perf_counter()
    cmd = [*(daemon_cmd or [python, "-m", "rfmcp_local.daemon"]), "--dir", str(d), *rest]
    if wrapper and not daemon_cmd:
        cmd = [*shlex.split(wrapper), *cmd]
    log = open(d / "daemon.log", "ab")
    env = dict(os.environ)
    env.setdefault("PYTHONPATH", "")
    pkg_root = str(Path(__file__).resolve().parent.parent)
    if pkg_root not in env["PYTHONPATH"].split(os.pathsep):  # spike: package not installed everywhere
        env["PYTHONPATH"] = os.pathsep.join([p for p in (pkg_root, env["PYTHONPATH"]) if p])
    env[procs.TOKEN_ENV] = os.urandom(8).hex()
    if (d / proto.STATE_NAME).exists():
        (d / proto.STATE_NAME).unlink()
    p = subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT, env=env,
                         start_new_session=True, close_fds=True)
    st = proto.wait_ready(d, p.pid, timeout=float(os.environ.get("RFMCP_START_TIMEOUT", "60")))
    ms = round((time.perf_counter() - t0) * 1000)
    if not st:
        procs.terminate(procs.alive([p.pid]) + procs.token_procs(env[procs.TOKEN_ENV]))
        tail = (d / "daemon.log").read_bytes()[-1500:].decode(errors="replace")
        _out({"ok": False, "error": "helper failed to start", "log_tail": tail, "cleanup": cl})
        return 2
    _out({"ok": True, "pid": st["pid"], "pgid": st["pgid"], "startup_ms": ms, "transport": st["transport"],
          "hooks": st.get("hooks"), "cleaned": cl.get("killed", 0)})
    return 0


def stop(d: Path, timeout: float, graceful: bool = False) -> int:
    st = _live_state(d)
    if not st:
        _out({"ok": True, "running": False, **cleanup(d)})
        return 0
    t0 = time.perf_counter()
    try:
        proto.request(st, {"op": "stop", "graceful": graceful}, timeout=5)
    except OSError as e:
        os.kill(st["pid"], 15)
    t_end = time.monotonic() + timeout
    while time.monotonic() < t_end and proto.pid_alive(st["pid"]):
        time.sleep(0.02)
    forced = False
    if proto.pid_alive(st["pid"]):
        forced = True
        os.kill(st["pid"], 9)
    exit_ms = round((time.perf_counter() - t0) * 1000)
    left = procs.token_procs(st["token_env"])
    killed = procs.terminate(left) if left else []
    st2 = proto.read_state(d) or {}
    _out({"ok": True, "stop_ms": exit_ms, "forced": forced, "orphans_after_exit": len(left),
          "helper_cleanup_ms": st2.get("cleanup_ms"), "helper_killed_children": st2.get("leftover"),
          "browser_close_ms": st2.get("browser_close_ms"), "graceful": graceful})
    return 0


def build(d: Path, argv: List[str]) -> int:
    """Journal -> .robot: passing cells only; `Import Library X` hoisted into *** Settings ***."""
    name, out = "Recorded", None
    it = iter(argv)
    for a in it:
        if a == "--name":
            name = next(it)
        elif a in ("-o", "--output"):
            out = next(it)
    settings, body = [], []
    for line in (d / "journal.jsonl").read_text().splitlines():
        j = json.loads(line)
        if not j.get("ok"):
            continue
        for cell in j["cells"] or []:
            for ln in cell.split("\n"):
                parts = [p for p in ln.strip().split("  ") if p.strip()]
                if parts and parts[0].strip().lower() in ("import library", "import resource", "import variables"):
                    kind = parts[0].strip().split()[1].capitalize()
                    entry = "    ".join([kind] + [p.strip() for p in parts[1:]])
                    if entry not in settings:
                        settings.append(entry)
                elif ln.strip():
                    body.append("    " + "    ".join(p.strip() for p in parts) if not ln.startswith(" ") else ln)
    text = "*** Settings ***\n" + "\n".join(settings) + f"\n\n*** Test Cases ***\n{name}\n" + "\n".join(body) + "\n"
    if out:
        Path(out).write_text(text)
        _out({"ok": True, "path": out, "lines": len(body)})
    else:
        sys.stdout.write(text)
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    d_arg, timeout, text = None, None, False
    rest: List[str] = []
    it = iter(argv)
    for a in it:
        if a == "--dir":
            d_arg = next(it)
        elif a == "--timeout":
            timeout = float(next(it))
        elif a == "--text":
            text = True
        else:
            rest.append(a)
    if not rest:
        sys.stdout.write(__doc__ or "")
        return 2
    cmd, args = rest[0], rest[1:]
    d = proto.state_dir(d_arg)
    if cmd == "start":
        return start(d, args)
    if cmd == "stop":
        return stop(d, timeout or 30.0, graceful="--graceful" in args)
    if cmd == "cleanup":
        _out(cleanup(d))
        return 0
    if cmd == "build":
        return build(d, args)
    if cmd == "batch":
        from .batch import main as batch_main  # heavy: imports robot/robotcode

        return batch_main(args)
    st = _live_state(d)
    if not st:
        _out({"ok": False, "error": "no helper running", "hint": "python -m rfmcp_local start"})
        return 3
    if cmd == "step":
        cells = [sys.stdin.read() if a == "-" else a for a in args]
        req = {"op": "step", "cells": cells, "timeout": timeout or 600}
    elif cmd == "vars":
        req = {"op": "vars", "all": "--all" in args, "names": [a for a in args if a != "--all"]}
    elif cmd in ("status", "interrupt", "ping"):
        req = {"op": cmd}
    elif cmd == "result":
        req = {"op": "result", "id": int(args[0])}
    else:
        _out({"ok": False, "error": f"unknown command {cmd}"})
        return 2
    try:
        resp = proto.request(st, req, timeout=(timeout or 600) + 5)
    except OSError as e:
        _out({"ok": False, "error": f"transport: {e}"})
        return 3
    _out(resp, text)
    return 0 if resp.get("ok") is not False else 1
