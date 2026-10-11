"""rf-mcp run_test_suite (in-process tool call) on the same suites, for size/latency comparison."""
import asyncio, json, sys, time
from pathlib import Path
from robotmcp import server
from robotmcp.compat.fastmcp_compat import get_tool_fn

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "outputs" / "q3"

async def main():
    fn = get_tool_fn(server.run_test_suite)
    rows = {}
    for name, suite, opts in [
        ("api_s05", ROOT / "corpus/suites/s05_booker_runtime_fail.robot", {}),
        ("ui_s02", ROOT / "corpus/suites/s02_saucedemo_bdd_valid.robot", {"variables": {"BASE_URL": "https://www.saucedemo.com"}}),
        ("dry_s03", ROOT / "corpus/suites/s03_saucedemo_bdd_broken.robot", {"variables": {"BASE_URL": "https://www.saucedemo.com"}}),
    ]:
        for level in ("minimal", "standard", "detailed"):
            mode = "dry" if name.startswith("dry") else "full"
            t0 = time.perf_counter()
            r = await fn(suite_file_path=str(suite), mode=mode, output_level=level, execution_options=dict(opts))
            dt = time.perf_counter() - t0
            js = json.dumps(r, default=str)
            rows[f"{name}_{level}"] = {"s": round(dt, 2), "chars": len(js), "raw": r}
            print(f"{name:<8} {mode:<4} {level:<9} {dt:6.2f}s {len(js):7d} chars ~{len(js)//4} tok keys={list(r)[:12]}", flush=True)
    (OUT / "rfmcp_run_test_suite.json").write_text(json.dumps(rows, indent=1, default=str))

asyncio.run(main())
