#!/usr/bin/env python3
"""Tiny stdio LSP shim between a coding agent and `robotcode language-server --stdio`.

Fixes two client/server mismatches found in round 3 (and logs all traffic for evidence):
  1. Full-text didChange ({"text": ...} without "range") -> robotcode advertises INCREMENTAL sync and
     silently drops such changes (Claude Code sends exactly this). Rewritten to one ranged change that
     replaces the whole previous text.
  2. languageId != "robotframework" for .robot/.resource (OpenCode sends "plaintext") -> robotcode ignores
     the document. Rewritten to "robotframework".
  3. Client advertises pull diagnostics (OpenCode) -> robotcode answers every textDocument/diagnostic with an
     empty report and pushes the real result later; the client takes the empty pull as final. The shim strips
     the pull capability from `initialize` so robotcode stays in push mode.
Optional: --min-severity N drops published diagnostics with severity > N (1=Error, 2=Warning, ...).

  rc_lsp_shim.py [--log FILE] [--passthrough] [--min-severity N] -- <server command ...>
"""
import json
import os
import signal
import subprocess
import sys
import threading
import time

RF_EXT = (".robot", ".resource")


def utf16_len(s):
    return len(s.encode("utf-16-le")) // 2


def pos_to_offset(text, line, char):
    lines = text.split("\n")
    if line >= len(lines):
        return len(text)
    off = sum(len(l) + 1 for l in lines[:line])
    l = lines[line]
    # utf-16 char -> python index
    u = 0
    for i, ch in enumerate(l):
        if u >= char:
            return off + i
        u += 2 if ord(ch) > 0xFFFF else 1
    return off + len(l)


def end_pos(text):
    lines = text.split("\n")
    return {"line": len(lines) - 1, "character": utf16_len(lines[-1])}


def read_msg(f):
    headers = {}
    while True:
        line = f.readline()
        if not line:
            return None
        line = line.decode("ascii", "replace").strip()
        if not line:
            break
        k, _, v = line.partition(":")
        headers[k.strip().lower()] = v.strip()
    n = int(headers.get("content-length", 0))
    body = f.read(n)
    return json.loads(body)


def write_msg(f, msg, lock):
    body = json.dumps(msg, ensure_ascii=False).encode("utf-8")
    with lock:
        f.write(b"Content-Length: %d\r\n\r\n" % len(body) + body)
        f.flush()


def main():
    argv = sys.argv[1:]
    log_path, passthrough, min_sev = None, False, None
    while argv and argv[0] != "--":
        a = argv.pop(0)
        if a == "--log":
            log_path = os.path.expandvars(argv.pop(0))
        elif a == "--passthrough":
            passthrough = True
        elif a == "--min-severity":
            min_sev = int(argv.pop(0))
    if argv and argv[0] == "--":
        argv.pop(0)
    if not argv:
        sys.exit("usage: rc_lsp_shim.py [--log FILE] [--passthrough] [--min-severity N] -- server cmd")
    t0 = time.time()
    logf = open(log_path, "a", buffering=1) if log_path else None
    loglock = threading.Lock()

    def log(kind, **kw):
        if logf:
            with loglock:
                logf.write(json.dumps({"t": round(time.time() - t0, 3), "wall": round(time.time(), 3),
                                       "kind": kind, **kw}) + "\n")

    log("start", cmd=argv, cwd=os.getcwd(), pid=os.getpid(), passthrough=passthrough)
    srv = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                           stderr=subprocess.PIPE if logf else None)
    log("server_pid", pid=srv.pid)
    docs = {}
    out_lock, in_lock = threading.Lock(), threading.Lock()
    stdin = sys.stdin.buffer
    stdout = sys.stdout.buffer

    def shutdown(*_):
        try:
            srv.terminate()
            srv.wait(timeout=5)
        except Exception:
            try:
                srv.kill()
            except Exception:
                pass
        log("exit", rc=srv.returncode)
        os._exit(0)

    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)

    def server_to_client():
        while True:
            msg = read_msg(srv.stdout)
            if msg is None:
                log("server_eof")
                os._exit(0)
            meth = msg.get("method")
            if meth == "textDocument/publishDiagnostics":
                diags = msg["params"].get("diagnostics", [])
                if min_sev is not None and not passthrough:
                    msg["params"]["diagnostics"] = [d for d in diags if d.get("severity", 1) <= min_sev]
                log("s2c", method=meth, uri=msg["params"]["uri"][-60:], version=msg["params"].get("version"),
                    n=len(diags), sent=len(msg["params"]["diagnostics"]),
                    diags=[(d.get("severity"), d.get("source"), d["range"]["start"]["line"] + 1,
                            d["message"][:100]) for d in diags])
            elif meth:
                log("s2c", method=meth, id=msg.get("id"))
            elif "id" in msg:
                res = msg.get("result")
                log("s2c_resp", id=msg["id"], error=msg.get("error"),
                    result_preview=json.dumps(res)[:300] if res is not None else None)
            write_msg(stdout, msg, out_lock)

    def stderr_pump():
        for line in srv.stderr:
            log("server_stderr", line=line.decode("utf-8", "replace").rstrip()[:500])

    threading.Thread(target=server_to_client, daemon=True).start()
    if logf:
        threading.Thread(target=stderr_pump, daemon=True).start()

    while True:
        msg = read_msg(stdin)
        if msg is None:
            log("client_eof")
            break
        meth = msg.get("method")
        info = {}
        try:
            p = msg.get("params") or {}
            if meth == "initialize":
                info = {"rootUri": p.get("rootUri"), "workspaceFolders": p.get("workspaceFolders"),
                        "clientInfo": p.get("clientInfo"), "initOpts": p.get("initializationOptions"),
                        "td_caps": sorted((p.get("capabilities", {}).get("textDocument") or {}).keys())}
                # 3. robotcode in pull mode answers textDocument/diagnostic with an EMPTY report and pushes the
                #    real diagnostics ~1-2 s later; OpenCode treats the empty pull as final. Force push mode.
                caps = p.get("capabilities") or {}
                if not passthrough and (caps.get("textDocument") or {}).get("diagnostic") is not None:
                    caps["textDocument"].pop("diagnostic", None)
                    (caps.get("workspace") or {}).pop("diagnostics", None)
                    info["stripped_pull_diagnostics"] = True
            elif meth == "textDocument/didOpen":
                td = p["textDocument"]
                info = {"uri": td["uri"][-60:], "languageId": td.get("languageId"), "version": td.get("version")}
                if not passthrough and td["uri"].endswith(RF_EXT) and td.get("languageId") != "robotframework":
                    td["languageId"] = "robotframework"
                    info["rewrote_languageId"] = True
                docs[td["uri"]] = td.get("text", "")
            elif meth == "textDocument/didChange":
                uri = p["textDocument"]["uri"]
                info = {"uri": uri[-60:], "version": p["textDocument"].get("version"),
                        "changes": ["full" if "range" not in c else "ranged" for c in p["contentChanges"]]}
                old = docs.get(uri, "")
                new_changes = []
                for c in p["contentChanges"]:
                    if "range" not in c:
                        new_changes.append({"range": {"start": {"line": 0, "character": 0}, "end": end_pos(old)},
                                            "text": c["text"]})
                        old = c["text"]
                    else:
                        r = c["range"]
                        a = pos_to_offset(old, r["start"]["line"], r["start"]["character"])
                        b = pos_to_offset(old, r["end"]["line"], r["end"]["character"])
                        old = old[:a] + c["text"] + old[b:]
                        new_changes.append(c)
                docs[uri] = old
                if not passthrough and info["changes"] != ["ranged"] * len(info["changes"]):
                    p["contentChanges"] = new_changes
                    info["rewrote_full_change"] = True
            elif meth == "textDocument/didClose":
                info = {"uri": p["textDocument"]["uri"][-60:]}
                docs.pop(p["textDocument"]["uri"], None)
            elif meth == "textDocument/didSave":
                info = {"uri": p["textDocument"]["uri"][-60:], "has_text": "text" in p}
            elif meth == "workspace/didChangeConfiguration":
                info = {"settings": p.get("settings")}
            elif meth in ("textDocument/hover", "workspace/symbol", "textDocument/definition",
                          "textDocument/documentSymbol", "textDocument/references"):
                info = {"params": json.dumps(p)[:300]}
            elif meth is None and "id" in msg:
                info = {"result_preview": json.dumps(msg.get("result"))[:300]}
        except Exception as e:  # never break the stream because of logging
            info["shim_error"] = repr(e)
        log("c2s", method=meth, id=msg.get("id"), **info)
        try:
            write_msg(srv.stdin, msg, in_lock)
        except BrokenPipeError:
            break
    try:
        srv.stdin.close()
        srv.wait(timeout=10)
    except Exception:
        srv.kill()
    log("exit", rc=srv.returncode)


if __name__ == "__main__":
    main()
