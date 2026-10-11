#!/usr/bin/env python3
"""rfstep: tiny stdlib-only one-shot client for `robotcode repl-server`.

Each invocation opens ONE connection to an already running repl-server
(TCP or unix socket from `--pipe-server`), sends ONE `executeCell` request,
prints a compact per-keyword summary and exits.  All RF state (browser,
sessions, variables) lives in the long-running repl-server process, so every
agent shell call can be a separate short-lived process.

Usage:
  rfstep.py run   --port 6701 'Click  css=#login'            # one cell (may be multi-line)
  rfstep.py run   --pipe /tmp/rs.sock --file steps.robot       # cell from a file
  echo 'Log  hi' | rfstep.py run --port 6701 -                  # cell from stdin
  rfstep.py run   --port 6701 --journal j.jsonl --json 'Get Url'
  rfstep.py build --journal j.jsonl --name 'My Test' > suite.robot
  rfstep.py stop  --port 6701                                   # shutdown the server

Exit codes: 0 = all keywords PASS, 1 = a keyword FAILED, 2 = input/parse error
(no keyword ran), 3 = connection / protocol error.
"""
import argparse
import json
import os
import re
import socket
import sys
import time

MIME_LOG = "x-application/robotframework-repl-log"
MIME_ERR = "application/vnd.code.notebook.stderr"


# ---------------------------------------------------------------- transport
def _connect(args):
    if args.pipe:
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.settimeout(args.timeout)
        s.connect(args.pipe)
        return s
    return socket.create_connection((args.host, args.port), timeout=args.timeout)


def rpc(args, method, params, rid=1):
    body = json.dumps({"jsonrpc": "2.0", "id": rid, "method": method, "params": params}).encode()
    s = _connect(args)
    try:
        s.sendall(b"Content-Length: %d\r\n\r\n" % len(body) + body)
        buf = b""
        while True:
            while b"\r\n\r\n" not in buf:
                chunk = s.recv(65536)
                if not chunk:
                    raise ConnectionError("server closed connection before responding")
                buf += chunk
            head, rest = buf.split(b"\r\n\r\n", 1)
            m = re.search(rb"Content-Length:\s*(\d+)", head, re.I)
            n = int(m.group(1))
            while len(rest) < n:
                chunk = s.recv(65536)
                if not chunk:
                    raise ConnectionError("truncated response")
                rest += chunk
            msg, buf = json.loads(rest[:n]), rest[n:]
            if msg.get("id") == rid:
                return msg
    finally:
        s.close()


# ---------------------------------------------------------------- summarise
_RET = re.compile(r"^Return: (.*)$", re.S)


def summarize_kw(node, depth=0, max_depth=2):
    """Reduce a KeywordResultData node to what an agent needs."""
    out = {
        "kw": node.get("name") or node.get("type"),
        "lib": node.get("owner") or None,
        "type": node.get("type"),
        "args": node.get("args") or [],
        "assign": node.get("assign") or [],
        "status": node.get("status"),
        "elapsed": node.get("elapsed_time"),
    }
    msgs, children = [], []
    for it in node.get("items", []):
        if it.get("node_type") == "message":
            lvl, text = it.get("level"), it.get("message", "")
            m = _RET.match(text)
            if lvl == "TRACE" and m:
                out["return"] = m.group(1)
            elif lvl in ("INFO", "WARN", "ERROR", "FAIL"):
                msgs.append(f"{lvl}: {text}" if lvl != "INFO" else text)
        elif it.get("node_type") == "keyword" and depth < max_depth:
            children.append(summarize_kw(it, depth + 1, max_depth))
    if node.get("status") == "FAIL":
        out["message"] = node.get("message")
    if msgs:
        out["log"] = [m if len(m) < 400 else m[:400] + "...<truncated>" for m in msgs]
    if children:
        out["body"] = children
    return {k: v for k, v in out.items() if v not in (None, [], "")}


def summarize(result):
    """Turn an ExecutionResult into {status, keywords, errors}."""
    if result is None:
        return {"status": "ERROR", "errors": ["empty result"], "keywords": []}
    kws, errors = [], []
    for item in result.get("items") or []:
        if item["mime"] == MIME_LOG:
            root = json.loads(item["data"])
            for n in root.get("items", []):
                if n.get("node_type") == "keyword":
                    kws.append(summarize_kw(n))
                elif n.get("node_type") == "message":
                    errors.append(f'{n.get("level")}: {n.get("message")}')
        elif item["mime"] == MIME_ERR:
            errors.append(item["data"])
    succ = result.get("success")
    status = "PASS" if succ is True else "FAIL" if succ is False else ("ERROR" if errors else "NOOP")
    return {"status": status, "keywords": kws, "errors": errors}


def render_text(summary):
    lines = [f'== {summary["status"]}']

    def walk(k, ind):
        sig = "  ".join(k.get("assign", []) + [k.get("kw", "")] + list(k.get("args", [])))
        lines.append(f'{"  " * ind}[{k.get("status")}] {sig}  ({k.get("elapsed", "")})')
        if "return" in k and k["return"] != "None":
            lines.append(f'{"  " * ind}    => {k["return"][:300]}')
        for m in k.get("log", []):
            lines.append(f'{"  " * ind}    | {m}')
        if k.get("message"):
            lines.append(f'{"  " * ind}    !! {k["message"]}')
        for c in k.get("body", []):
            walk(c, ind + 1)

    for k in summary["keywords"]:
        walk(k, 0)
    for e in summary["errors"]:
        lines.append(f"!! {e}")
    return "\n".join(lines)


# ---------------------------------------------------------------- commands
def cmd_run(args):
    if args.file:
        source = open(args.file, encoding="utf-8").read()
    elif args.cell == "-" or args.cell is None:
        source = sys.stdin.read()
    else:
        source = args.cell
    source = source.rstrip("\n")
    t0 = time.perf_counter()
    try:
        resp = rpc(args, "executeCell", {"source": source, "language_id": "robotframework"})
    except (OSError, ConnectionError, ValueError) as e:
        print(json.dumps({"status": "ERROR", "errors": [f"connection: {e}"]}) if args.json else f"!! connection: {e}")
        return 3
    wall = time.perf_counter() - t0
    if "error" in resp:
        print(json.dumps({"status": "ERROR", "errors": [resp["error"]]}))
        return 3
    summary = summarize(resp.get("result"))
    summary["wall_s"] = round(wall, 3)
    if args.journal:
        with open(args.journal, "a", encoding="utf-8") as fh:
            fh.write(json.dumps({"ts": time.time(), "test": args.test, "source": source,
                                 "status": summary["status"], "wall_s": summary["wall_s"],
                                 "keywords": [{"kw": k.get("kw"), "status": k.get("status")}
                                              for k in summary["keywords"]]}) + "\n")
    print(json.dumps(summary, ensure_ascii=False) if args.json else render_text(summary))
    return {"PASS": 0, "FAIL": 1, "ERROR": 2, "NOOP": 2}[summary["status"]]


_IMPORT = re.compile(r"^\s*Import (Library|Resource|Variables)\s{2,}(.+)$", re.I)


def cmd_build(args):
    """journal (jsonl) -> .robot suite, keeping only PASS cells (like rf-mcp build_test_suite)."""
    settings, tests = [], {}
    for line in open(args.journal, encoding="utf-8"):
        e = json.loads(line)
        if e["status"] != "PASS":
            continue
        tname = e.get("test") or args.name
        body = tests.setdefault(tname, [])
        for src_line in e["source"].split("\n"):
            m = _IMPORT.match(src_line)
            if m:
                s = f"{m.group(1).title()}    {re.sub(r'  +', '    ', m.group(2).strip())}"
                if s not in settings:
                    settings.append(s)
            elif src_line.strip():
                body.append("    " + re.sub(r"(?<=\S)  +(?=\S)", "    ", src_line.rstrip()))
    out = ["*** Settings ***", *settings, "", "*** Test Cases ***"]
    for t, body in tests.items():
        out += [t, *body, ""]
    sys.stdout.write("\n".join(out))
    return 0


def cmd_stop(args):
    try:
        rpc(args, "shutdown", None)
    except Exception as e:  # noqa: BLE001
        print(f"shutdown: {e}")
    return 0


def main(argv=None):
    p = argparse.ArgumentParser(prog="rfstep")
    sub = p.add_subparsers(dest="cmd", required=True)
    for name in ("run", "stop"):
        sp = sub.add_parser(name)
        sp.add_argument("--host", default="127.0.0.1")
        sp.add_argument("--port", type=int, default=int(os.environ.get("RFSTEP_PORT", "6601")))
        sp.add_argument("--pipe", default=os.environ.get("RFSTEP_PIPE"))
        sp.add_argument("--timeout", type=float, default=float(os.environ.get("RFSTEP_TIMEOUT", "300")))
        if name == "run":
            sp.add_argument("cell", nargs="?")
            sp.add_argument("--file")
            sp.add_argument("--json", action="store_true")
            sp.add_argument("--journal", default=os.environ.get("RFSTEP_JOURNAL"))
            sp.add_argument("--test", default=os.environ.get("RFSTEP_TEST"))
    bp = sub.add_parser("build")
    bp.add_argument("--journal", required=True)
    bp.add_argument("--name", default="Recorded Test")
    args = p.parse_args(argv)
    return {"run": cmd_run, "build": cmd_build, "stop": cmd_stop}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
