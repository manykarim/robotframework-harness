"""Per-case static validation: `robotcode analyze code` vs `robot --dryrun`.

Usage: python3 run_static.py            (runs all cases, both envs)
Writes ../outputs/static_results.json and prints a table.
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
CORPUS = ROOT / "corpus"
OUT = ROOT / "outputs"

ENVS = {
    "rcexp": Path("~/workspace/robotcode-experiments/.venv/bin"),
    "wt": Path("~/workspace/rf-mcp-robotcode/.venv/bin"),
}


def analyze(env: str, files: list[str], extra: list[str] | None = None) -> dict:
    rc_bin = str(ENVS[env] / "robotcode")
    cmd = [rc_bin, "analyze", "code", "--output-format", "json", *(extra or []), *files]
    t0 = time.perf_counter()
    p = subprocess.run(cmd, cwd=CORPUS, capture_output=True, text=True)
    dt = time.perf_counter() - t0
    try:
        data = json.loads(p.stdout)
    except json.JSONDecodeError:
        data = {"raw": p.stdout[-2000:], "stderr": p.stderr[-2000:]}
    return {"cmd": " ".join(cmd[1:]), "exit": p.returncode, "elapsed_s": round(dt, 3),
            "stdout_chars": len(p.stdout), "data": data}


def dryrun(env: str, file: str, extra: list[str] | None = None) -> dict:
    py = str(ENVS[env] / "python")
    cmd = [py, str(HERE / "dryrun_case.py"), file, "--pythonpath", "libs", "--pythonpath", "resources",
           "--variable", "BASE_URL:https://www.saucedemo.com", *(extra or [])]
    t0 = time.perf_counter()
    p = subprocess.run(cmd, cwd=CORPUS, capture_output=True, text=True)
    dt = time.perf_counter() - t0
    try:
        data = json.loads(p.stdout.strip().splitlines()[-1])
    except Exception:  # noqa: BLE001
        data = {"raw": p.stdout[-1500:], "stderr": p.stderr[-1500:]}
    data["wall_s"] = round(dt, 3)
    return data


def summarize_diags(res: dict) -> list[dict]:
    diags = []
    for _file, items in (res["data"].get("diagnostics") or {}).items():
        for d in items:
            diags.append({"code": d.get("code"), "sev": d.get("severity"),
                          "line": d["range"]["start"]["line"] + 1,
                          "msg": d.get("message", "").splitlines()[0][:220]})
    return diags


def dry_verdict(d: dict) -> tuple[str, list[str]]:
    msgs = [e for e in d.get("errors", [])]
    fails = [f"{t['name']}: {t['message'][:220]}" for t in d.get("tests", []) if t["status"] == "FAIL"]
    verdict = "error" if fails or any(m.startswith("ERROR") for m in msgs) else (
        "warn" if msgs else "ok")
    return verdict, fails + msgs


def main() -> None:
    manifest = json.loads((CORPUS / "manifest.json").read_text())
    results = []
    for c in manifest:
        runs = [("", [])]
        if c["id"] == "v06_cli_variable":
            runs.append(("+cli-var", ["-v", "FROM_CLI:x"]))
        for suffix, extra in runs:
            a = analyze(c["env"], [c["file"]], extra)
            diags = summarize_diags(a)
            dr_extra = ["--variable", "FROM_CLI:x"] if suffix else []
            d = dryrun(c["env"], c["file"], dr_extra)
            dv, dmsgs = dry_verdict(d)
            sev = {x["sev"] for x in diags}
            av = "error" if 1 in sev else ("warn" if 2 in sev else ("info" if sev else "ok"))
            results.append({
                "id": c["id"] + suffix, "env": c["env"], "cls": c["cls"], "expect": c["expect"],
                "analyze_exit": a["exit"], "analyze_s": a["elapsed_s"], "analyze_chars": a["stdout_chars"],
                "analyze_verdict": av, "diags": diags,
                "dryrun_rc": d.get("rc"), "dryrun_s": d.get("wall_s"), "dryrun_verdict": dv,
                "dryrun_msgs": dmsgs[:6], "dryrun_raw": d if "raw" in d else None,
            })
            r = results[-1]
            print(f"{r['id']:<42} exp={r['expect']:<5} an={av:<5}(x{a['exit']},{a['elapsed_s']:.2f}s) "
                  f"dry={dv:<5}({d.get('wall_s')}s) | "
                  + "; ".join(f"{x['code']}:{x['msg'][:70]}" for x in diags)[:200], flush=True)
    (OUT / "static_results.json").write_text(json.dumps(results, indent=1))


if __name__ == "__main__":
    sys.exit(main())
