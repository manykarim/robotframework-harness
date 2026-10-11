#!/usr/bin/env python3
"""Drive a stock `robotcode repl --plain` across separate shell calls (experiment, stdlib only).

  rfrepl.py start  --dir D [--rc ROBOTCODE] [--load toml|env|import] [--mode rdwr|keeper]
                   [--output output.xml] [--cwd PROJECT] [-- extra robotcode-repl args]
  rfrepl.py step   --dir D [--timeout S] [--id ID] 'CELL'      (CELL '-' = stdin)
  rfrepl.py wait   --dir D ID [--timeout S]                     (resume a timed-out step)
  rfrepl.py status --dir D
  rfrepl.py stop   --dir D [--grace S]
  rfrepl.py build  --dir D -o suite.robot [--name NAME]

Protocol: each step writes   "# rfmcp-step: ID\\n<cell without blank lines>\\n\\n# rfmcp-end: ID\\n"
into D/in.fifo. The REPL treats '#' lines as comments (no-op, not kept by `.save`); the
rfmcp listener's read_line hook turns them into begin/end records in D/steps.jsonl and
tags every top-level step record in between with ID. The blank line closes any unfinished
FOR/IF/TRY block so a broken cell can never wedge the REPL.
"""

import errno
import fcntl
import json
import os
import re
import signal
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEFAULT_RC = "~/workspace/robotcode-experiments/.venv/bin/robotcode"
LISTENER = HERE / "proj" / "rfmcp_listener.py"


def _paths(d):
    d = Path(d).absolute()
    return {
        "dir": d,
        "fifo": d / "in.fifo",
        "jsonl": d / "steps.jsonl",
        "log": d / "repl.log",
        "pid": d / "repl.pid",
        "lock": d / "lock",
        "seq": d / "seq",
        "out": d / "out",
    }


def _alive(pid):
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _zombie(pid):
    try:
        with open(f"/proc/{pid}/stat") as fh:
            return fh.read().rsplit(")", 1)[1].split()[0] == "Z"
    except OSError:
        return True


def _read_pgid(p):
    try:
        f = p["pid"].read_text().split()
        return int(f[2]) if len(f) > 2 else int(f[0])
    except Exception:
        return None


def _read_pid(p):
    try:
        return int(p["pid"].read_text().split()[0])
    except Exception:
        return None


def _scan(path, off, pred, timeout, poll=0.002, pid=None):
    """Read JSON lines appended after byte offset `off` until pred(rec) is true.
    Returns (records, True|False|"dead")."""
    deadline = time.monotonic() + timeout
    next_check = time.monotonic() + 0.2
    recs, buf = [], b""
    with open(path, "rb") as fh:
        fh.seek(off)
        while True:
            chunk = fh.read()
            if chunk:
                buf += chunk
                *lines, buf = buf.split(b"\n")
                for ln in lines:
                    if not ln.strip():
                        continue
                    rec = json.loads(ln)
                    recs.append(rec)
                    if pred(rec):
                        return recs, True
            elif time.monotonic() > deadline:
                return recs, False
            elif pid and time.monotonic() > next_check:
                next_check = time.monotonic() + 0.2
                if not _alive(pid) or _zombie(pid):
                    return recs, "dead"
            else:
                time.sleep(poll)


def _write_fifo(p, data):
    inbox = p["dir"] / "inbox"
    if inbox.exists():
        with open(inbox, "ab") as fh:  # caller holds the lock; O_APPEND keeps writes whole
            fh.write(data.encode("utf-8"))
        return True
    try:
        fd = os.open(p["fifo"], os.O_WRONLY | os.O_NONBLOCK)
    except OSError as e:
        if e.errno in (errno.ENXIO, errno.ENOENT):
            return False
        raise
    try:
        os.set_blocking(fd, True)
        os.write(fd, data.encode("utf-8"))
    finally:
        os.close(fd)
    return True


# ------------------------------------------------------------------ start
def cmd_start(a, extra):
    import subprocess

    p = _paths(a.dir)
    p["dir"].mkdir(parents=True, exist_ok=True)
    p["out"].mkdir(parents=True, exist_ok=True)
    pid = _read_pid(p)
    if pid and _alive(pid):
        print(json.dumps({"ok": False, "error": f"already running pid={pid}"}))
        return 3
    for k in ("fifo",):
        try:
            p[k].unlink()
        except FileNotFoundError:
            pass
    os.mkfifo(p["fifo"], 0o600)
    p["jsonl"].touch()
    off = p["jsonl"].stat().st_size
    env = dict(os.environ, RFMCP_JSONL=str(p["jsonl"]), PYTHONUNBUFFERED="1", PYTHONWARNINGS="ignore")
    gopts, ropts = [], ["repl", "--plain", "--no-history", "-d", str(p["out"])]
    if a.load == "toml":
        gopts += ["-p", "listen"]
    elif a.load == "env":
        env["ROBOT_OPTIONS"] = f"--listener {LISTENER}"
    if a.output:
        ropts += ["-o", a.output]
    ropts += extra
    t0 = time.monotonic()
    if a.mode == "rdwr":
        # REPL holds both ends of its own stdin FIFO -> never sees EOF, no keeper process
        fd = os.open(p["fifo"], os.O_RDWR)
        proc = subprocess.Popen(
            [a.rc, *gopts, *ropts], stdin=fd, stdout=open(p["log"], "ab"), stderr=subprocess.STDOUT,
            start_new_session=True, env=env, cwd=a.cwd,
        )
        os.close(fd)
        keeper = None
    elif a.mode == "inbox":
        # portable: feeder.py tails D/inbox into the REPL's stdin (no FIFO); bash leads the group
        inbox = p["dir"] / "inbox"
        inbox.touch()
        script = '"$0" "$1" "$2" | "${@:3}" & echo $! > "$2.replpid"; wait'
        lead = subprocess.Popen(
            ["bash", "-c", script, sys.executable, str(HERE / "feeder.py"), str(inbox), a.rc, *gopts, *ropts],
            stdin=subprocess.DEVNULL, stdout=open(p["log"], "ab"), stderr=subprocess.STDOUT,
            start_new_session=True, env=env, cwd=a.cwd,
        )
        rp = Path(str(inbox) + ".replpid")
        for _ in range(200):
            if rp.exists() and rp.read_text().strip():
                break
            time.sleep(0.01)

        class P:  # noqa: N801
            pid = int(rp.read_text().strip())
        proc, keeper = P, None
        p["pid"].write_text(f"{proc.pid} - {lead.pid}\n")
    else:
        # classic: a keeper `sleep` holds the write end; it lives in the REPL's own
        # session/process group (bash wrapper execs into robotcode, keeping the pid)
        script = 'sleep infinity > "$0" & echo $! > "$0.keeper"; exec "$@" < "$0"'
        proc = subprocess.Popen(
            ["bash", "-c", script, str(p["fifo"]), a.rc, *gopts, *ropts], stdin=subprocess.DEVNULL,
            stdout=open(p["log"], "ab"), stderr=subprocess.STDOUT, start_new_session=True, env=env, cwd=a.cwd,
        )
        for _ in range(100):
            kp = Path(str(p["fifo"]) + ".keeper")
            if kp.exists() and kp.read_text().strip():
                break
            time.sleep(0.01)

        class K:  # noqa: N801
            pid = int(kp.read_text().strip())
        keeper = K
    if a.mode != "inbox":
        p["pid"].write_text(f"{proc.pid} {keeper.pid if keeper else '-'} {proc.pid}\n")
    p["seq"].write_text("0")
    if a.load == "import":
        _write_fifo(p, f"Import Library    {LISTENER}\n")
    recs, ok = _scan(p["jsonl"], off, lambda r: r.get("t") == "idle", a.timeout)
    ms = round((time.monotonic() - t0) * 1000)
    print(json.dumps({"ok": ok, "pid": proc.pid, "pgid": _read_pgid(p), "keeper": keeper.pid if keeper else None,
                      "ready_ms": ms, "hooked": any(r.get("hooked") for r in recs if r.get("t") == "ready")}))
    return 0 if ok else 4


# ------------------------------------------------------------------ step
def _summ(node):
    out = {k: node[k] for k in ("type", "name", "owner", "args", "assign", "status", "message", "return", "values")
           if node.get(k) not in (None, [], "", {})}
    if node.get("type") == "KEYWORD":
        out.pop("type", None)
    fails = []

    def walk(n):
        for c in n.get("items", []) or []:
            if c.get("status") == "FAIL" and c.get("type") == "KEYWORD":
                fails.append({"name": c.get("name"), "message": c.get("message")})
            walk(c)

    walk(node)
    if fails and node.get("status") == "PASS":
        out["caught_failures"] = fails[:5]
    msgs = [m for m in node.get("msgs", []) if m["level"] in ("WARN", "ERROR")]
    if msgs:
        out["warnings"] = [m["text"] for m in msgs][:5]
    shots = [m["text"] for m in node.get("msgs", []) if m.get("html") and ".png" in m["text"]]
    if shots:
        out["screenshots"] = [re.findall(r'src="([^"]+)"', s)[0] if 'src="' in s else s for s in shots]
    return out


def _finish(recs, sid, ok, t0, timeout):
    steps = [r for r in recs if r.get("t") == "step" and r.get("id") == sid]
    steps = [s for s in steps if s.get("owner") != "robotcode.repl.Repl"]
    end = next((r for r in recs if r.get("t") == "end" and r.get("id") == sid), None)
    if ok == "dead":
        status = "DEAD"
    elif not ok:
        status = "TIMEOUT"
    elif not steps:
        status = "NOOP"
    else:
        status = "FAIL" if any(s.get("status") == "FAIL" for s in steps) else "PASS"
    res = {"id": sid, "status": status, "ms": round((time.monotonic() - t0) * 1000, 1),
           "steps": [_summ(s) for s in steps]}
    if end and end.get("skipped_src"):
        res["skipped_after_failure"] = [x for x in end["skipped_src"].split("\n") if x.strip()]
    if ok == "dead":
        res["hint"] = "the REPL process exited during this step (see repl.log); run start again"
    elif not ok:
        res["hint"] = f"still running? resume with: rfrepl.py wait --dir ... {sid} (timeout was {timeout}s)"
    print(json.dumps(res, ensure_ascii=False))
    return {"PASS": 0, "NOOP": 0, "FAIL": 1, "DEAD": 3}.get(status, 4)


def _fold(lines):
    """The plain REPL executes a line as soon as it parses, so `...` continuation
    lines would run as separate (broken) statements: fold them into the previous line."""
    out = []
    for ln in lines:
        st = ln.lstrip()
        if out and (st == "..." or re.match(r"\.\.\.(  |\t)", st)):
            rest = st[3:].strip()
            out[-1] = out[-1].rstrip() + ("    " + rest if rest else "")
        else:
            out.append(ln)
    return out


def cmd_step(a, extra):
    p = _paths(a.dir)
    t0 = time.monotonic()
    cell = sys.stdin.read() if a.cell == "-" else a.cell
    lines = _fold([ln.rstrip("\r") for ln in cell.split("\n") if ln.strip()])
    if not lines:
        print(json.dumps({"status": "NOOP"}))
        return 0
    pid = _read_pid(p)
    if not pid or not _alive(pid):
        print(json.dumps({"status": "DEAD", "error": "repl not running; run start"}))
        return 3
    with open(p["lock"], "a+") as lk:
        fcntl.flock(lk, fcntl.LOCK_EX)  # serialize concurrent agents/shells
        seq = int(p["seq"].read_text() or 0) + 1
        p["seq"].write_text(str(seq))
        sid = a.id or f"s{seq}"
        off = p["jsonl"].stat().st_size
        payload = f"# rfmcp-step: {sid}\n" + "\n".join(lines) + f"\n\n# rfmcp-end: {sid}\n"
        if not _write_fifo(p, payload):
            print(json.dumps({"status": "DEAD", "error": "no reader on fifo"}))
            return 3
        recs, ok = _scan(p["jsonl"], off, lambda r: r.get("t") == "end" and r.get("id") == sid, a.timeout,
                         pid=pid)
    return _finish(recs, sid, ok, t0, a.timeout)


def cmd_wait(a, extra):
    p = _paths(a.dir)
    t0 = time.monotonic()
    # search from the begin record of this id
    off = 0
    with open(p["jsonl"], "rb") as fh:
        pos = 0
        for ln in fh:
            if f'"t": "begin", "id": "{a.id}"'.encode() in ln:
                off = pos
            pos += len(ln)
    recs, ok = _scan(p["jsonl"], off, lambda r: r.get("t") == "end" and r.get("id") == a.id, a.timeout)
    return _finish(recs, a.id, ok, t0, a.timeout)


# ------------------------------------------------------------------ status / stop
def cmd_status(a, extra):
    p = _paths(a.dir)
    pid = _read_pid(p)
    print(json.dumps({"pid": pid, "alive": bool(pid and _alive(pid))}))
    return 0


def _group_members(pgid):
    import subprocess

    out = subprocess.run(["ps", "-eo", "pid=,pgid=,comm="], capture_output=True, text=True).stdout
    return [ln.split(None, 2) for ln in out.splitlines() if ln.split()[1] == str(pgid)]


def cmd_stop(a, extra):
    p = _paths(a.dir)
    pid = _read_pid(p)
    res = {"pid": pid}
    if not pid:
        print(json.dumps({"error": "no pid"}))
        return 3
    t0 = time.monotonic()
    if _alive(pid):
        res["sent_exit"] = _write_fifo(p, "\n.exit\n")
        deadline = time.monotonic() + a.grace
        while _alive(pid) and time.monotonic() < deadline:
            time.sleep(0.05)
            try:
                os.waitpid(pid, os.WNOHANG)
            except ChildProcessError:
                pass
    res["exit_ms"] = round((time.monotonic() - t0) * 1000)
    res["repl_alive_after_grace"] = _alive(pid)
    pgid = _read_pgid(p) or pid
    time.sleep(0.1)
    left = _group_members(pgid)
    res["group_left_after_exit"] = [m[2] for m in left]
    if left:
        try:
            os.killpg(pgid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        time.sleep(0.2)
        res["group_left_after_kill"] = [m[2] for m in _group_members(pgid)]
    for extra_file in ("inbox", "inbox.replpid"):
        try:
            (p["dir"] / extra_file).unlink()
        except FileNotFoundError:
            pass
    try:
        p["fifo"].unlink()
    except FileNotFoundError:
        pass
    print(json.dumps(res))
    return 0


# ------------------------------------------------------------------ build
_IMPORT_HEADS = {"import library": "Library", "import resource": "Resource", "import variables": "Variables",
                 "library": "Library", "resource": "Resource", "variables": "Variables"}
_SEP = re.compile(r"  +|\t")


def cmd_build(a, extra):
    p = _paths(a.dir)
    recs = [json.loads(ln) for ln in p["jsonl"].read_text().splitlines() if ln.strip()]
    status = {}
    for r in recs:
        if r.get("t") == "step" and r.get("id") and r.get("owner") != "robotcode.repl.Repl":
            status.setdefault(r["id"], []).append(r["status"])
    settings, body, skipped = [], [], []
    ends = [r for r in recs if r.get("t") == "end"]
    if a.first:
        ends = ends[: a.first]
    for r in ends:
        if not r.get("src"):
            continue
        sts = status.get(r["id"], [])
        if not sts or any(s != "PASS" for s in sts):
            skipped.append(r["id"])
            continue
        src = r["src"]
        if "\n" not in src:
            cells = _SEP.split(src.strip())
            head = _IMPORT_HEADS.get(cells[0].casefold())
            if head and str(LISTENER) not in src:
                settings.append("    ".join([head, *cells[1:]]))
                continue
            if head:
                continue
        body.append("\n".join("    " + ln.strip() if not ln.startswith(" ") else "    " + ln for ln in src.split("\n")))
    text = ""
    if settings:
        text += "*** Settings ***\n" + "\n".join(dict.fromkeys(settings)) + "\n\n"
    text += f"*** Test Cases ***\n{a.name}\n" + "\n".join(body) + "\n"
    Path(a.o).write_text(text)
    print(json.dumps({"written": a.o, "steps": len(body), "imports": len(settings), "skipped": skipped}))
    return 0


def main():
    argv = sys.argv[1:]
    # fast path for the hot command (no argparse import): step --dir D [--timeout S] CELL
    if argv[:1] == ["step"] and len(argv) in (4, 6) and argv[1] == "--dir":
        class A:  # noqa: N801
            dir, id, timeout, cell = argv[2], None, 120.0, argv[-1]
        if len(argv) == 6 and argv[3] == "--timeout":
            A.timeout = float(argv[4])
        if len(argv) == 4 or argv[3] == "--timeout":
            return cmd_step(A, [])
    import argparse

    extra = []
    if "--" in argv:
        i = argv.index("--")
        argv, extra = argv[:i], argv[i + 1:]
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("start")
    s.add_argument("--dir", required=True)
    s.add_argument("--rc", default=DEFAULT_RC)
    s.add_argument("--load", choices=["toml", "env", "import"], default="toml")
    s.add_argument("--mode", choices=["rdwr", "keeper", "inbox"], default="rdwr")
    s.add_argument("--output")
    s.add_argument("--cwd", default=str(HERE / "proj"))
    s.add_argument("--timeout", type=float, default=60)
    s = sub.add_parser("step")
    s.add_argument("--dir", required=True)
    s.add_argument("--timeout", type=float, default=120)
    s.add_argument("--id")
    s.add_argument("cell")
    s = sub.add_parser("wait")
    s.add_argument("--dir", required=True)
    s.add_argument("--timeout", type=float, default=120)
    s.add_argument("id")
    s = sub.add_parser("status")
    s.add_argument("--dir", required=True)
    s = sub.add_parser("stop")
    s.add_argument("--dir", required=True)
    s.add_argument("--grace", type=float, default=30)
    s = sub.add_parser("build")
    s.add_argument("--dir", required=True)
    s.add_argument("-o", required=True)
    s.add_argument("--name", default="Recorded Steps")
    s.add_argument("--first", type=int, help="only the first N steps")
    a = ap.parse_args(argv)
    return globals()[f"cmd_{a.cmd}"](a, extra)


if __name__ == "__main__":
    sys.exit(main())
