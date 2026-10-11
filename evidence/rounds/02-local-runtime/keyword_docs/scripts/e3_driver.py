"""E3 driver: fresh process per (mode, lib); wall time includes interpreter start."""
import json, subprocess, time, sys
from pathlib import Path
K = Path("~/workspace/rf-mcp-robotcode/experiments/robotcode-remote/round2/keyword_docs")
PYX = "~/workspace/robotcode-experiments/.venv/bin/python"  # RF 7.5 + Browser + Requests
PYW = "~/workspace/rf-mcp-robotcode/.venv/bin/python"       # RF 7.3.2 + Selenium
OUT = K / "outputs/e3"; (OUT / "cache_x").mkdir(parents=True, exist_ok=True); (OUT / "cache_w").mkdir(exist_ok=True)
rows = []
def run(py, mode, lib, cdir):
    s = time.perf_counter()
    p = subprocess.run([py, str(K / "scripts/e3_api_probe.py"), mode, lib, str(cdir)], capture_output=True, text=True)
    w = time.perf_counter() - s
    try: r = json.loads(p.stdout.strip().splitlines()[-1])
    except Exception: r = {"mode": mode, "lib": lib, "fail": p.stderr[-300:]}
    rows.append({"wall_s": round(w, 3), "venv": "x" if py == PYX else "w", **r})
def bare(py, code, label):
    s = time.perf_counter(); subprocess.run([py, "-c", code]); rows.append({"wall_s": round(time.perf_counter() - s, 3), "mode": label, "venv": "x" if py == PYX else "w"})
for lib in ["Browser", "RequestsLibrary", "BuiltIn", "Collections", "String"]:
    for mode in ["rf", "rc", "rcpk", "rfjs", "rfjs"]:
        run(PYX, mode, lib, OUT / "cache_x")
    run(PYX, "rcdb", lib, K / "project")
for lib in ["SeleniumLibrary", "BuiltIn"]:
    for mode in ["rf", "rc", "rcpk", "rfjs", "rfjs"]:
        run(PYW, mode, lib, OUT / "cache_w")
for py in (PYX, PYW):
    bare(py, "pass", "bare_python"); bare(py, "import robot.libdocpkg", "import_robot_libdocpkg")
    bare(py, "import robotcode.robot.diagnostics.library_doc", "import_rc_library_doc")
(OUT / "e3.json").write_text(json.dumps(rows, indent=1, default=str))
for r in rows:
    print(f'{r["venv"]} {r.get("mode"):22} {r.get("lib",""):16} wall={r["wall_s"]:6.2f}s n={r.get("n","")} import={r.get("import_s","")} build={r.get("build_s","")} warm={r.get("warm_rebuild_s","")} pkl={r.get("pickle_bytes","")} spec={r.get("spec_bytes","")} {r.get("errors","") or ""}{r.get("fail","")}')
