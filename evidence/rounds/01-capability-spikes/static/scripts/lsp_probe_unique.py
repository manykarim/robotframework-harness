"""LSP push-diagnostics latency with a fresh document URI per step (avoids cross-step attribution)."""
import json, os, signal, sys, time, queue
from pathlib import Path
sys.argv = [sys.argv[0], sys.argv[1], sys.argv[2], "reopen", "3.0"]
sys.path.insert(0, str(Path(__file__).parent))
import lsp_probe as L  # reuse Client + STEPS

def main():
    c = L.Client()
    t0 = time.perf_counter()
    c.request("initialize", {"processId": None, "rootUri": L.ROOT.as_uri(),
                             "capabilities": {"textDocument": {"publishDiagnostics": {"versionSupport": True}}}})
    c.notify("initialized", {})
    print(f"initialize {time.perf_counter()-t0:.2f}s")
    rows = []
    for rep in range(2):
        for i, (label, text) in enumerate(L.STEPS, start=1):
            uri = (L.ROOT / "cases" / f"_lsp_{rep}_{i}.robot").as_uri()
            t = time.perf_counter()
            c.notify("textDocument/didOpen", {"textDocument": {"uri": uri, "languageId": "robotframework", "version": 1, "text": text}})
            last, diags, n, end = None, [], 0, time.time() + 20
            while time.time() < end:
                try:
                    ts, m = c.q.get(timeout=1.5 if last else 1.0)
                except queue.Empty:
                    if last: break
                    continue
                if m.get("method") == "textDocument/publishDiagnostics" and m["params"]["uri"] == uri:
                    last, n = ts - t, n + 1
                    diags = [f"{d.get('code')}: {d['message'][:70]}" for d in m["params"]["diagnostics"] if "-" not in str(d.get("code"))]
                elif "method" in m and "id" in m:
                    c.send({"jsonrpc": "2.0", "id": m["id"], "result": None})
            rows.append({"rep": rep, "step": label, "last_publish_s": last, "publishes": n, "diags": diags})
            print(f"rep{rep} {label:<42} last publish {last if last is None else round(last,3)}s ({n}) {diags}", flush=True)
    c.request("shutdown", None); c.notify("exit", None)
    try: os.killpg(c.p.pid, signal.SIGTERM)
    except ProcessLookupError: pass
    (L.ROOT.parent / "outputs" / "q4" / "lsp_probe_unique.json").write_text(json.dumps(rows, indent=1))

main()
