"""Exp 3: LSP keyword-knowledge features: hover, signatureHelp, completion, workspace/symbol, definition."""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from lsp_client import LSP  # noqa: E402

RC = "~/workspace/robotcode-experiments/.venv/bin/robotcode"
PROJ = HERE / "proj"
TEXT = """*** Settings ***
Library    Browser
Library    RequestsLibrary
Resource    shop.resource

*** Test Cases ***
Live
    Fill Text    id=user-name    standard_user
    When The User Logs In As "standard_user"
    POST On Session    booker    /booking    json=${None}
    Cli
    Get Text    css=.x    ==    y
"""
# 0-based positions
POS = {
    "hover Fill Text (Browser)": (7, 6),
    "hover embedded user kw (resource)": (8, 15),
    "hover POST On Session (Requests)": (9, 8),
    "hover argument value": (7, 20),
}


def size(x) -> int:
    return len(json.dumps(x))


def main() -> None:
    f = PROJ / "tests" / "_features.robot"
    f.write_text(TEXT)
    lsp = LSP(RC, PROJ, log=HERE / "logs" / "exp3_lsp.stderr")
    lsp.initialize({"robocop": {"enabled": False}})
    caps = lsp.init_result.get("capabilities", {})
    u, v, t0 = lsp.open(f)
    lsp.wait_diags(u, v, t0, timeout=120, settle=1.0)
    out = {"capabilities": sorted(caps.keys()),
           "completion_trigger": caps.get("completionProvider"),
           "signature_trigger": caps.get("signatureHelpProvider")}
    for label, (ln, ch) in POS.items():
        dt, r = lsp.pos_req("textDocument/hover", f, ln, ch)
        val = ((r.get("result") or {}).get("contents") or {})
        val = val.get("value") if isinstance(val, dict) else val
        out[label] = {"s": dt, "chars": len(val or ""), "head": (val or "")[:400]}
        print(f"{label}: {dt}s {len(val or '')} chars")
    # signature help inside Fill Text args (after 'id=user-name    ') and in Get Text assertion op
    for label, (ln, ch) in {"sig Fill Text arg2": (7, 33), "sig Get Text assertion_operator": (11, 27),
                            "sig POST On Session json=": (9, 45)}.items():
        dt, r = lsp.pos_req("textDocument/signatureHelp", f, ln, ch)
        res = r.get("result") or {}
        sigs = res.get("signatures") or []
        out[label] = {"s": dt, "chars": size(res), "n_sigs": len(sigs), "active_param": res.get("activeParameter"),
                      "label": sigs[0]["label"][:300] if sigs else None,
                      "params": [p.get("label") for p in (sigs[0].get("parameters") or [])][:15] if sigs else None,
                      "doc_chars": len(json.dumps(sigs[0].get("documentation"))) if sigs else 0}
        print(f"{label}: {out[label]}")
    # completion at 'Cli|'
    dt, r = lsp.pos_req("textDocument/completion", f, 10, 7)
    res = r.get("result")
    items = res.get("items") if isinstance(res, dict) else (res or [])
    out["completion Cli|"] = {"s": dt, "items": len(items), "chars": size(res),
                              "is_incomplete": res.get("isIncomplete") if isinstance(res, dict) else None,
                              "labels_matching_cli": [i["label"] for i in items if i["label"].lower().startswith("cli")][:20],
                              "kinds": sorted({i.get("kind") for i in items}),
                              "sample": items[0] if items else None}
    print("completion:", {k: v for k, v in out["completion Cli|"].items() if k != "sample"})
    if items:
        cand = next((i for i in items if i["label"].lower().startswith("click")), items[0])
        t = time.perf_counter()
        rr = lsp.request("completionItem/resolve", cand)
        out["completion resolve"] = {"s": round(time.perf_counter() - t, 4), "label": cand["label"],
                                     "chars_before": size(cand), "chars_after": size(rr.get("result"))}
        print("resolve:", out["completion resolve"])
    # workspace/symbol
    for q in ("Fill Text", "Logs In", "Click", "Booking"):
        t = time.perf_counter()
        r = lsp.request("workspace/symbol", {"query": q})
        res = r.get("result") or []
        out[f"workspace/symbol {q}"] = {"s": round(time.perf_counter() - t, 4), "n": len(res),
                                        "names": [(s["name"], Path(s["location"]["uri"]).name if "location" in s else None) for s in res][:10]}
        print(f"workspace/symbol {q!r}: {out[f'workspace/symbol {q}']}")
    # definition
    for label, (ln, ch) in {"def embedded user kw": (8, 15), "def Fill Text": (7, 6)}.items():
        dt, r = lsp.pos_req("textDocument/definition", f, ln, ch)
        res = r.get("result") or []
        locs = [(x.get("targetUri") or x.get("uri"), (x.get("targetRange") or x.get("range") or {}).get("start")) for x in res]
        out[label] = {"s": dt, "locs": [(str(Path(a).name) if a else a, b) for a, b in locs]}
        print(label, out[label])
    # documentSymbol
    dt, r = lsp.pos_req("textDocument/documentSymbol", f, 0, 0) if False else (None, None)
    t = time.perf_counter()
    r = lsp.request("textDocument/documentSymbol", {"textDocument": {"uri": u}})
    out["documentSymbol"] = {"s": round(time.perf_counter() - t, 4), "chars": size(r.get("result"))}
    lsp.shutdown()
    f.unlink()
    (HERE / "results" / "exp3_features.json").write_text(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
