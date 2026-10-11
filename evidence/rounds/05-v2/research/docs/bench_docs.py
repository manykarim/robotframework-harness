"""Round-5: latency/size of `robotcode libdoc ... show <kw>` and whole-library outputs (n reps)."""
import json, os, statistics, subprocess, sys, time
BV = "~/workspace/robotcode-experiments/.venv/bin"
SV = "~/workspace/rf-mcp-robotcode/.venv/bin"
N = int(sys.argv[1]) if len(sys.argv) > 1 else 6
cases = [
    ("Browser", "Get Text", BV), ("Browser", "Click", BV), ("Browser", "Get Aria Snapshot", BV),
    ("SeleniumLibrary", "Click Element", SV), ("SeleniumLibrary", "Wait Until Element Is Visible", SV),
    ("RequestsLibrary", "GET On Session", BV), ("BuiltIn", "Should Be Equal", BV), ("Collections", "Get From Dictionary", BV),
    ("resources/shop.resource", "Add Product To Cart", BV), ("libs/ArgLib.py::advanced", "Advanced Keyword", BV),
    ("Browser::timeout=5s", "Get Text", BV),
]
rows = []
def run(cmd):
    ts, out = [], b""
    for _ in range(N):
        t0 = time.perf_counter(); p = subprocess.run(cmd, capture_output=True); ts.append((time.perf_counter() - t0) * 1000)
        out = p.stdout
    return ts, out, p.returncode, p.stderr[:200].decode(errors="replace")
for lib, kw, venv in cases:
    ts, out, rc, err = run([f"{venv}/robotcode", "libdoc", lib, "show", kw])
    rows.append({"kind": "show_kw", "lib": lib, "kw": kw, "median_ms": round(statistics.median(ts)), "min_ms": round(min(ts)),
                 "bytes": len(out), "lines": out.count(b"\n"), "rc": rc, "err": err})
for lib, venv in (("Browser", BV), ("SeleniumLibrary", SV), ("RequestsLibrary", BV), ("BuiltIn", BV), ("resources/shop.resource", BV)):
    ts, out, rc, err = run([f"{venv}/robotcode", "libdoc", lib, "show"])
    rows.append({"kind": "show_all_md", "lib": lib, "median_ms": round(statistics.median(ts)), "bytes": len(out), "rc": rc})
    ts, out, rc, err = run([f"{venv}/robotcode", "libdoc", lib, "list"])
    rows.append({"kind": "list", "lib": lib, "median_ms": round(statistics.median(ts)), "bytes": len(out), "rc": rc})
    fn = f"out/{lib.replace('/', '_')}.json"
    ts, out, rc, err = run([f"{venv}/robotcode", "libdoc", "--format", "JSON", lib, fn])
    rows.append({"kind": "json_file", "lib": lib, "median_ms": round(statistics.median(ts)), "bytes": os.path.getsize(fn) if os.path.exists(fn) else None, "rc": rc, "err": err})
# plain libdoc (no robotcode) for comparison
ts, out, rc, err = run([f"{BV}/python", "-m", "robot.libdoc", "Browser", "show", "Get Text"])
rows.append({"kind": "plain_libdoc_show_kw", "lib": "Browser", "median_ms": round(statistics.median(ts)), "bytes": len(out), "rc": rc})
with open("docs_latency.json", "w") as f:
    json.dump(rows, f, indent=1)
for r in rows:
    print(r)
