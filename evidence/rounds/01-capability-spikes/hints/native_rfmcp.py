"""Run every corpus mistake through NATIVE rf-mcp (real MCP tool layer, in-process).

Translates each REPL line into manage_session / execute_step calls, the way an agent
using rf-mcp would, and records the execute_step payload (error + hints) of every
step. The mistake step runs with detail_level="full" so ALL hints are visible; what
"minimal"/"standard" would show is re-derived offline with rf-mcp's own ranker.

  cd ~/workspace/rf-mcp-robotcode && uv run python experiments/robotcode-remote/hints/native_rfmcp.py [ID ...]

Output: runs/<id>/native/result.json
Note: rf-mcp venv = RF 7.3.2 + Browser 19.12.7 (robotcode venv = RF 7.5 + Browser 20.5.0).
"""

from __future__ import annotations

import asyncio
import json
import sys
import time
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from corpus import CORPUS  # noqa: E402
from parse_robotcode import split_line  # noqa: E402

from fastmcp import Client  # noqa: E402
from robotmcp.server import mcp  # noqa: E402

RUNS = HERE / "runs"


def _payload(res):
    if getattr(res, "structured_content", None):
        return res.structured_content
    if getattr(res, "data", None) is not None:
        return res.data
    try:
        return json.loads(res.content[0].text)
    except Exception:  # noqa: BLE001
        return {"raw": str(res)}


async def run_one(client: Client, m: dict) -> dict:
    sid = f"hints-{m['id'].lower()}"
    init_libs = [lib for lib in m["libraries"] if lib not in ("Screenshot", "ShopHelpers", "Process")]
    log = {"id": m["id"], "session_id": sid, "init_libraries": init_libs, "steps": []}
    r = await client.call_tool("manage_session", {"action": "init", "session_id": sid, "libraries": init_libs},
                               raise_on_error=False)
    log["init"] = {"ok": not r.is_error}
    lines = m["preamble"] + m["steps"]
    mistake_idx = len(lines) - 1
    if m["id"] == "M41":
        mistake_idx = len(lines) - 2
    browser_timeout = None
    for i, line in enumerate(lines):
        d = split_line(line)
        kw, args, assign = d["keyword"], d["args"], d["assign"]
        if kw.lower() == "import library" and args and args[0] in init_libs:
            # rf-mcp already imported it at init; keep only a Browser timeout if given
            for a in args[1:]:
                if a.startswith("timeout="):
                    browser_timeout = a.split("=", 1)[1]
            log["steps"].append({"line": line, "skipped": "already imported by manage_session init"})
            continue
        params = {"keyword": kw, "arguments": args, "session_id": sid, "raise_on_failure": False,
                  "detail_level": "full" if i == mistake_idx else "minimal"}
        if assign:
            params["assign_to"] = assign[0].strip("${}&@=").strip("{}") if len(assign) == 1 else \
                [a.strip("$&@{}=") for a in assign]
        t0 = time.monotonic()
        try:
            res = await client.call_tool("execute_step", params, raise_on_error=False)
            payload = _payload(res)
        except Exception as e:  # noqa: BLE001
            payload = {"exception": repr(e), "tb": traceback.format_exc()[-2000:]}
        entry = {"line": line, "params": params, "is_mistake": i == mistake_idx,
                 "duration_s": round(time.monotonic() - t0, 2), "response": payload}
        log["steps"].append(entry)
        if kw == "New Browser" and browser_timeout:
            await client.call_tool("execute_step", {"keyword": "Set Browser Timeout", "arguments": [browser_timeout],
                                                    "session_id": sid, "raise_on_failure": False},
                                   raise_on_error=False)
    if "Browser" in init_libs:
        await client.call_tool("execute_step", {"keyword": "Close Browser", "arguments": ["ALL"],
                                                "session_id": sid, "raise_on_failure": False},
                               raise_on_error=False)
    return log


async def main(ids):
    todo = [m for m in CORPUS if not ids or m["id"] in ids]
    async with Client(mcp) as client:
        for m in todo:
            t0 = time.monotonic()
            try:
                log = await run_one(client, m)
            except Exception as e:  # noqa: BLE001
                log = {"id": m["id"], "fatal": repr(e), "tb": traceback.format_exc()[-3000:]}
            out = RUNS / m["id"] / "native"
            out.mkdir(parents=True, exist_ok=True)
            (out / "result.json").write_text(json.dumps(log, indent=2, default=str))
            mistake = next((s for s in log.get("steps", []) if s.get("is_mistake")), {})
            resp = mistake.get("response") or {}
            print(json.dumps({"id": m["id"], "s": round(time.monotonic() - t0, 1),
                              "success": resp.get("success"), "error": str(resp.get("error"))[:100],
                              "hints": [(h.get("title") or h.get("type")) if isinstance(h, dict) else str(h)[:60]
                                        for h in (resp.get("hints") or [])]}),
                  flush=True)


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1:]))
