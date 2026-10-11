"""rfmcp -- local Robot Framework helper for coding agents (research prototype, no MCP).

  rfmcp start [-v name:value] [-P pythonpath] [--tcp] [--idle SECONDS]   start the live RF session (idempotent)
  rfmcp stop | status                         stop is a cheap no-op when nothing runs
  rfmcp step [--no-guard] '<Keyword>    <arg>    ...'   run RF line(s) in the live session (one call at a time!)
  rfmcp step - <<'RF'                         several lines / quotes: quoted heredoc
  rfmcp run FILE.robot [--new|--lines A-B|--all|--rebase] [--test NAME] [--force] [--no-guard]
                                              run lines of a test file you edit yourself (default --new)
  rfmcp check FILE                            static errors + robocop + portability (no helper needed)
  rfmcp search "what to do" [--lib Browser] [-n 5]   find keywords
  rfmcp doc "Keyword Name" [--full]           keyword signature + doc
  rfmcp state [controls|aria|source|url|screenshot]  page inspection -> files under .rf/state/
  rfmcp vars [NAME ...]                       variables created in the session
  rfmcp wait JOB                              collect a step that ran longer than 25 s
  rfmcp guide [TOPIC]                         debug | explore | browser | selenium | requests | results | waits | visual | quoting
NO helper needed for: output.xml/results analysis (robotcode results, rfmcp guide results), static edits (rfmcp check).
Output: one compact JSON object (ok/status/msg/line/hints). Exit 0 ok, 1 failed, 3 no helper, 4 still running.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from . import fast, procs, proto

CLIENT_OPS = {"step", "run", "check", "search", "doc", "state", "vars", "wait", "interrupt"}


def _out(obj: Dict[str, Any]) -> None:
    sys.stdout.write(json.dumps(obj, separators=(",", ":"), default=str) + "\n")
    sys.stdout.flush()


def _sd() -> Path:
    return Path(fast.state_dir()).absolute()


def _live(d: Path) -> Optional[Dict[str, Any]]:
    st = proto.read_state(d)
    if st and proto.pid_alive(st.get("pid")) and not st.get("stopped"):
        return st
    return None


def cleanup(d: Path) -> Dict[str, Any]:
    """Kill leftovers of a dead helper (e.g. after kill -9): every process carrying its token."""
    st = proto.read_state(d) or {}
    if st.get("pid") and proto.pid_alive(st["pid"]) and not st.get("stopped"):
        return {"ok": False, "error": "helper alive; use stop"}
    tok = st.get("token_env")
    left = procs.token_procs(tok) if tok else []
    forced = procs.terminate(left) if left else []
    for f in (d / "endpoint",):
        try:
            f.unlink()
        except OSError:
            pass
    if st.get("transport") == "unix" and st.get("sock"):
        try:
            os.unlink(st["sock"])
        except OSError:
            pass
    return {"killed": len(left), "forced": len(forced)}


def start(d: Path, argv: List[str], quiet: bool = False) -> int:
    st = _live(d)
    if st:
        if not quiet:
            _out({"ok": True, "already_running": True, "pid": st["pid"], "cwd": st.get("cwd")})
        return 0
    cl = cleanup(d)
    proto.ensure_private_dir(d)
    t0 = time.perf_counter()
    cmd = [sys.executable, "-m", "rfmcp_skill.daemon", "--dir", str(d), "--root", os.getcwd(), *argv]
    env = dict(os.environ)
    env[procs.TOKEN_ENV] = os.urandom(8).hex()
    env.setdefault("PYTHONUNBUFFERED", "1")
    if (d / proto.STATE_NAME).exists():
        (d / proto.STATE_NAME).unlink()
    with open(d / "daemon.log", "ab") as log:
        p = subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT, env=env,
                             start_new_session=True, close_fds=True, cwd=os.getcwd())
    st = proto.wait_ready(d, p.pid, timeout=float(os.environ.get("RFMCP_START_TIMEOUT", "90")))
    ms = round((time.perf_counter() - t0) * 1000)
    if not st:
        procs.terminate(procs.alive([p.pid]) + procs.token_procs(env[procs.TOKEN_ENV]))
        tail = (d / "daemon.log").read_bytes()[-1200:].decode(errors="replace")
        _out({"ok": False, "error": "helper failed to start", "log_tail": tail})
        return 2
    if not quiet:
        _out({"ok": True, "started": True, "pid": st["pid"], "startup_ms": ms, "cwd": st.get("cwd"),
              "next": "rfmcp step 'Import Library    Browser'  (or write a .robot file and: rfmcp run FILE)",
              **({"cleaned_orphans": cl["killed"]} if cl.get("killed") else {})})
    return 0


def stop(d: Path, timeout: float = 20.0) -> int:
    st = _live(d)
    if not st:
        cl = cleanup(d) if (d / proto.STATE_NAME).exists() else {}
        _out({"ok": True, "running": False, "note": "nothing to stop",
              **({k: v for k, v in cl.items() if v} if cl else {})})
        return 0
    t0 = time.perf_counter()
    try:
        proto.request(st, {"op": "stop", "graceful": True}, timeout=5)
    except OSError:
        try:
            os.kill(st["pid"], 15)
        except OSError:
            pass
    t_end = time.monotonic() + timeout
    while time.monotonic() < t_end and proto.pid_alive(st["pid"]):
        time.sleep(0.02)
    forced = False
    if proto.pid_alive(st["pid"]):
        forced = True
        try:
            os.kill(st["pid"], 9)
        except OSError:
            pass
    left = procs.token_procs(st["token_env"])
    if left:
        procs.terminate(left)
    orphans = len(procs.token_procs(st["token_env"]))
    try:
        (d / "endpoint").unlink()
    except OSError:
        pass
    _out({"ok": True, "stopped": True, "stop_ms": round((time.perf_counter() - t0) * 1000), "forced": forced,
          "orphans": orphans, "killed_after_exit": len(left)})
    return 0


def client(cmd: str, args: List[str], d: Path) -> int:
    if cmd == "check" and not _live(d):  # static check needs no live session: do not start one
        return check_static(args)
    rc, buf = fast.call(cmd, args, str(d))
    if rc == 3 and cmd not in ("wait", "interrupt") and not _live(d):
        # auto-start once: agents often forget `rfmcp start`
        sys.stderr.write("rfmcp: no helper running -> starting it\n")
        if start(d, [], quiet=True) != 0:
            sys.stdout.buffer.write(buf)
            return 3
        rc, buf = fast.call(cmd, args, str(d))
    if cmd == "check" and rc in (0, 1):
        return _check_with_robocop(args, buf, rc)
    sys.stdout.buffer.write(buf if buf.endswith(b"\n") else buf + b"\n")
    sys.stdout.flush()
    return rc


def _analyzer_cli(path: Path) -> List[Dict[str, Any]]:
    """robotcode analyzer (errors only) without a helper: `robotcode analyze code --severity error FILE`."""
    import re

    rc_bin = Path(sys.executable).with_name("robotcode")
    try:
        r = subprocess.run([str(rc_bin), "analyze", "code", "--severity", "error", str(path)], cwd=os.getcwd(),
                           capture_output=True, text=True, timeout=120)
    except (OSError, subprocess.TimeoutExpired) as e:
        return [{"line": 0, "code": "AnalyzerUnavailable", "msg": repr(e)[:200]}]
    out = []
    for line in (r.stdout or "").splitlines():
        m = re.match(r"^(.*?):(\d+):(\d+): \[ERROR\] (\w+): (.*)$", line)
        if m:
            out.append({"line": int(m.group(2)), "col": int(m.group(3)), "code": m.group(4), "msg": m.group(5)[:300]})
    return out


def check_static(args: List[str]) -> int:
    """`rfmcp check FILE` with no helper running: analyzer + robocop + portability, no process left behind."""
    if not args:
        _out({"ok": False, "error": "usage: rfmcp check FILE"})
        return 2
    path = Path(args[0])
    if not path.is_file():
        _out({"ok": False, "error": f"no such file: {args[0]}"})
        return 1
    t0 = time.perf_counter()
    errs = _analyzer_cli(path)
    res: Dict[str, Any] = {"file": str(path), "ok": not errs, "errors": errs[:20],
                           "helper": "not running: static check only (variables set at run time may show as errors)"}
    buf = json.dumps(res).encode()
    rc = _check_with_robocop(args, buf, 0 if not errs else 1, t0=t0)
    return rc


def _check_with_robocop(args: List[str], buf: bytes, rc: int, t0: Optional[float] = None) -> int:
    """`rfmcp check` = analyzer errors (live-filtered) + robocop agent-profile findings + portability, one JSON."""
    try:
        res = json.loads(buf)
    except ValueError:
        sys.stdout.buffer.write(buf)
        return rc
    try:
        from .portable import issues as portable_issues

        port = portable_issues(Path(args[0]), Path.cwd())
    except Exception as e:  # never break check
        port = [{"line": 0, "code": "PortableCheckFailed", "msg": repr(e)[:200]}]
    if port:
        res["portable"] = port
        res["ok"] = False
    try:
        from .edithook import robocop_issues

        issues = robocop_issues([Path(args[0]).resolve()], fix=False)
    except Exception as e:  # robocop missing -> analyzer result only
        issues = [f"(robocop unavailable: {type(e).__name__})"]
    if issues:
        res["robocop"] = issues[:15]
        if any("auto-fixable" in i for i in issues):
            res["fix"] = (f"safe auto-fix: robocop check --fix --config "
                          f"{Path(__file__).with_name('data') / 'robocop-agent.toml'} {args[0]}")
        if any(" E " in i for i in issues):
            res["ok"] = False
    if t0 is not None:
        res["ms"] = round((time.perf_counter() - t0) * 1000)
    _out(res)
    return 0 if res.get("ok") else 1


def main(argv: Optional[List[str]] = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv[:1] == ["--dir"]:
        os.environ["RFMCP_DIR"], argv = argv[1], argv[2:]
    if not argv or argv[0] in ("-h", "--help", "help"):
        sys.stdout.write(__doc__ or "")
        return 0 if argv else 2
    cmd, args = argv[0], argv[1:]
    d = _sd()
    if cmd == "start":
        return start(d, args)
    if cmd == "stop":
        return stop(d)
    if cmd == "status":
        if not _live(d):
            _out({"ok": True, "running": False})
            return 0
        rc, buf = fast.call("status", [], str(d))
        sys.stdout.buffer.write(buf)
        return rc
    if cmd == "cleanup":
        _out({"ok": True, **cleanup(d)})
        return 0
    if cmd == "guide":
        from .guides import guide

        text, ok = guide(args[0] if args else "")
        sys.stdout.write(text if text.endswith("\n") else text + "\n")
        return 0 if ok else 2
    if cmd == "hook":
        from .edithook import main as hook_main

        return hook_main(args)
    if cmd in CLIENT_OPS:
        return client(cmd, args, d)
    _out({"ok": False, "error": f"unknown command '{cmd}'", "usage": "rfmcp --help"})
    return 2


if __name__ == "__main__":
    sys.exit(main())
