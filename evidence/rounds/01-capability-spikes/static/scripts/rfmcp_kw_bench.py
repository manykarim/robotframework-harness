"""In-process rf-mcp keyword tools benchmark (find_keywords / get_keyword_info /
check_library_availability / recommend_libraries) for comparison with robotcode CLI.

Run from the worktree:  uv run python experiments/robotcode-remote/static/scripts/rfmcp_kw_bench.py
Writes outputs/q2/rfmcp_bench.json
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "outputs" / "q2"
OUT.mkdir(parents=True, exist_ok=True)

t_import0 = time.perf_counter()
from robotmcp import server  # noqa: E402
from robotmcp.compat.fastmcp_compat import get_tool_fn  # noqa: E402

T_IMPORT = time.perf_counter() - t_import0

QUERIES = [
    ("click element", "Browser"),
    ("fill text", "Browser"),
    ("post json", "RequestsLibrary"),
    ("wait until visible", "SeleniumLibrary"),
    ("get text", None),
]
KW_INFO = [
    ("Click", "Browser"),
    ("Fill Text", "Browser"),
    ("POST On Session", "RequestsLibrary"),
    ("Wait Until Element Is Visible", "SeleniumLibrary"),
    ("Get Text", None),
]


def names_of(res: dict) -> list[str]:
    items = res.get("results") or res.get("result") or []
    if isinstance(items, dict):
        items = items.get("keywords") or items.get("results") or []
    out = []
    for it in items if isinstance(items, list) else []:
        if isinstance(it, dict):
            lib = it.get("library") or it.get("library_name") or ""
            out.append(f"{lib}.{it.get('name') or it.get('keyword')}")
        else:
            out.append(str(it))
    return out


async def timed(fn, **kw):
    t0 = time.perf_counter()
    try:
        r = await fn(**kw)
    except Exception as e:  # noqa: BLE001
        r = {"success": False, "exception": repr(e)}
    return r, time.perf_counter() - t0


async def main() -> None:
    fk = get_tool_fn(server.find_keywords)
    gk = get_tool_fn(server.get_keyword_info)
    cla = get_tool_fn(server.check_library_availability)
    rl = get_tool_fn(server.recommend_libraries)
    rows = []
    for strategy in ("semantic", "pattern"):
        for q, lib in QUERIES:
            for scoped in (False, True):
                if scoped and not lib:
                    continue
                kw = dict(query=q, strategy=strategy, context="web" if lib != "RequestsLibrary" else "api", limit=10)
                if scoped:
                    kw["library_name"] = lib
                r, dt = await timed(fk, **kw)
                js = json.dumps(r, default=str)
                rows.append({"tool": "find_keywords", "strategy": strategy, "query": q,
                             "library_name": kw.get("library_name"), "s": round(dt, 3), "chars": len(js),
                             "top": names_of(r)[:10], "success": r.get("success"), "raw": r})
                print(f"find_keywords {strategy:<8} {q!r:<22} lib={kw.get('library_name')!s:<16} {dt:6.3f}s {len(js):6d}ch "
                      f"top={names_of(r)[:5]}", flush=True)
    for name, lib in KW_INFO:
        kw = dict(mode="keyword", keyword_name=name)
        if lib:
            kw["library_name"] = lib
        r, dt = await timed(gk, **kw)
        js = json.dumps(r, default=str)
        rows.append({"tool": "get_keyword_info", "keyword": name, "library_name": lib, "s": round(dt, 3),
                     "chars": len(js), "success": r.get("success"), "raw": r})
        print(f"get_keyword_info {name!r:<32} lib={lib!s:<16} {dt:6.3f}s {len(js):6d}ch success={r.get('success')}", flush=True)
    r, dt = await timed(cla, libraries=["Browser", "SeleniumLibrary", "RequestsLibrary", "Collections", "NonExistentLib"])
    js = json.dumps(r, default=str)
    rows.append({"tool": "check_library_availability", "s": round(dt, 3), "chars": len(js), "raw": r})
    print(f"check_library_availability {dt:6.3f}s {len(js)}ch", flush=True)
    r, dt = await timed(rl, scenario="Log in to saucedemo.com in a browser, add an item to the cart, then verify the order via the REST API")
    js = json.dumps(r, default=str)
    rows.append({"tool": "recommend_libraries", "s": round(dt, 3), "chars": len(js), "raw": r})
    print(f"recommend_libraries {dt:6.3f}s {len(js)}ch", flush=True)
    meta = {"import_s": round(T_IMPORT, 3), "semantic_env": os.environ.get("ROBOTMCP_SEMANTIC_KEYWORDS"),
            "python": sys.version}
    tag = os.environ.get("BENCH_TAG", "default")
    (OUT / f"rfmcp_bench_{tag}.json").write_text(json.dumps({"meta": meta, "rows": rows}, indent=1, default=str))
    print("import_s", meta)


if __name__ == "__main__":
    asyncio.run(main())
