"""Round 3 / robocop: run robocop on the round-1 corpus (copied to ../corpus1).

Modes (one robocop process per case, --no-cache = cold):
  A  default rule set
  B  --select project rules (KW05,KW06,ARG08,IMP07,IMP09) + ERR* + DEPR*
  C  default + --extend-select project rules  (what an agent profile would add)

Writes ../out/corpus1_detect.json
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
R3 = HERE.parent
CORPUS = R3 / "corpus1"
OUT = R3 / "out"
ENVS = {
    "rcexp": Path("~/workspace/robotcode-experiments/.venv/bin/robocop"),
    "wt": Path("~/workspace/rf-mcp-robotcode/.venv/bin/robocop"),
}
PROJECT = ["KW05", "KW06", "ARG08", "IMP07", "IMP09"]
# NB: robocop 9.1 does NOT accept comma lists in --select ("No rule selected", exit 0) -> repeat the flag
MODES = {
    "A": [],
    "B": [a for r in [*PROJECT, "ERR*", "DEPR*"] for a in ("--select", r)],
    "C": [a for r in PROJECT for a in ("--extend-select", r)],
}


def run(env: str, file: str, mode: str) -> dict:
    report = OUT / "tmp_report.json"
    report.unlink(missing_ok=True)
    cmd = [
        str(ENVS[env]), "check", "--no-cache", "--root", str(CORPUS),
        "--pythonpath", "libs", "--pythonpath", "resources",
        "--reports", "json_report", "-c", f"json_report.output_path={report}",
        "--exit-zero", "--silent", "--skip-gitignore", *MODES[mode], file,  # experiments/ is git-excluded
    ]
    t0 = time.perf_counter()
    p = subprocess.run(cmd, cwd=CORPUS, capture_output=True, text=True)
    dt = time.perf_counter() - t0
    try:
        issues = json.loads(report.read_text())
    except Exception:  # noqa: BLE001
        issues = []
    target = Path(file).as_posix()
    own = [i for i in issues if Path(i["source"]).as_posix() == target]
    return {
        "mode": mode, "project_total_issues": len(issues), "exit": p.returncode, "elapsed_s": round(dt, 3),
        "stderr": p.stderr[-800:],
        "issues": [
            {"rule": i["rule_id"], "name": i["rule_name"], "sev": i["severity"], "line": i["line"],
             "col": i["column"], "msg": i["description"][:200]}
            for i in own
        ],
    }


def main() -> None:
    manifest = json.loads((CORPUS / "manifest.json").read_text())
    only = set(sys.argv[1:])
    results = []
    for c in manifest:
        if only and c["id"] not in only:
            continue
        row = {"id": c["id"], "cls": c["cls"], "expect": c["expect"], "env": c["env"], "runs": {}}
        for mode in MODES:
            row["runs"][mode] = run(c["env"], c["file"], mode)
        results.append(row)
        print(c["id"], {m: [(i["rule"], i["line"]) for i in r["issues"]] for m, r in row["runs"].items()},
              flush=True)
    name = "corpus1_detect.json" if not only else "corpus1_detect_partial.json"
    (OUT / name).write_text(json.dumps(results, indent=1))


if __name__ == "__main__":
    main()
