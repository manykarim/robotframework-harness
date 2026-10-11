#!/usr/bin/env python3
"""Summarize a shim lsp.jsonl: server start/init latency, every document sync event and the latency to the next
publishDiagnostics for that uri, plus all server->client requests.  python3 lsp_timeline.py runs/<agent>/<cell>"""
import json
import sys
from pathlib import Path


def main(cell):
    p = Path(cell) / "lsp.jsonl"
    if not p.exists():
        print("no lsp.jsonl")
        return {}
    ev = [json.loads(l) for l in p.read_text().splitlines() if l.strip()]
    starts = [e for e in ev if e["kind"] == "start"]
    out = {"server_starts": len(starts), "events": []}
    # multiple shim instances append to the same log: t is per-instance, use wall
    w0 = ev[0]["wall"]
    init_req = {}
    for e in ev:
        t = round(e["wall"] - w0, 2)
        if e["kind"] == "c2s" and e.get("method") == "initialize":
            init_req[e.get("id")] = e["wall"]
            out["events"].append((t, "initialize", e.get("rootUri"), (e.get("clientInfo") or {}).get("name")))
        elif e["kind"] == "s2c_resp" and e.get("id") in init_req and "capabilities" in (e.get("result_preview") or ""):
            out["events"].append((t, "initialize_resp", round(e["wall"] - init_req[e["id"]], 2)))
        elif e["kind"] == "c2s" and e.get("method", "") and e["method"].startswith("textDocument/did"):
            extra = {k: e[k] for k in ("languageId", "version", "changes", "rewrote_full_change",
                                       "rewrote_languageId", "has_text") if k in e}
            out["events"].append((t, e["method"].split("/")[1], e["uri"][-28:], extra))
        elif e["kind"] == "c2s" and e.get("method") in ("textDocument/hover", "workspace/symbol",
                                                         "textDocument/definition", "textDocument/documentSymbol",
                                                         "textDocument/diagnostic", "workspace/didChangeConfiguration"):
            out["events"].append((t, e["method"], e.get("params") or e.get("settings") or ""))
        elif e["kind"] == "s2c" and e.get("method") == "textDocument/publishDiagnostics":
            errs = [d for d in e["diags"] if d[0] == 1]
            out["events"].append((t, "PUBLISH", e["uri"][-28:], f"v{e.get('version')}", f"n={e['n']}",
                                  f"err={len(errs)}", [d[3][:70] for d in errs][:4]))
        elif e["kind"] == "s2c" and e.get("method") not in (None,):
            out["events"].append((t, "s2c_req", e["method"]))
        elif e["kind"] == "s2c_resp" and e.get("result_preview") and ("contents" in e["result_preview"]
                                                                     or "location" in e["result_preview"]):
            out["events"].append((t, "resp", e["result_preview"][:160]))
        elif e["kind"] in ("exit", "client_eof", "server_eof"):
            out["events"].append((t, e["kind"]))
    for x in out["events"]:
        print(*x)
    return out


if __name__ == "__main__":
    main(sys.argv[1])
