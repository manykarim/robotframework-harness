"""Capture exact robotcode REPL output for every corpus mistake.

Variants per mistake (each its own REPL process):
  plain : robotcode repl --plain --no-history -d DIR -o output.xml
  k     : same + -k/--show-keywords
Then for the plain variant: robotcode --format json results log -o output.xml

Output layout: runs/<id>/<variant>/{stdin.txt,stdout.txt,meta.json,output.xml}
               runs/<id>/plain/results_log.json

Run with any python (only uses subprocess):
  python capture.py [ID ...]
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from corpus import CORPUS  # noqa: E402

ROBOTCODE = "~/workspace/robotcode-experiments/.venv/bin/robotcode"
RUNS = HERE / "runs"
# run from a neutral cwd so the robotcode-experiments robot.toml is NOT picked up
CWD = HERE / "scratch" / "cwd"


def run_variant(m: dict, variant: str) -> dict:
    out = RUNS / m["id"] / variant
    out.mkdir(parents=True, exist_ok=True)  # REPL does not create -d itself
    stdin = "\n".join(m["preamble"] + m["steps"] + [".exit"]) + "\n"
    (out / "stdin.txt").write_text(stdin)
    cmd = [ROBOTCODE, "repl", "--plain", "--no-history", "-d", str(out), "-o", "output.xml"]
    if variant == "k":
        cmd.append("-k")
    env = dict(os.environ)
    t0 = time.monotonic()
    p = subprocess.run(cmd, input=stdin, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, cwd=CWD, env=env, timeout=240)
    dt = time.monotonic() - t0
    (out / "stdout.txt").write_text(p.stdout)  # merged stdout+stderr (FAIL lines go to stderr)
    meta = {"cmd": cmd, "exit": p.returncode, "duration_s": round(dt, 2), "streams": "merged"}
    if variant == "plain" and (out / "output.xml").exists():
        r = subprocess.run(
            [ROBOTCODE, "--format", "json", "results", "log", "-o", str(out / "output.xml")],
            capture_output=True, text=True, cwd=CWD, timeout=60,
        )
        (out / "results_log.json").write_text(r.stdout or r.stderr)
        meta["results_log_exit"] = r.returncode
    (out / "meta.json").write_text(json.dumps(meta, indent=2))
    return {"id": m["id"], "variant": variant, **meta}


def main(ids: list[str]) -> None:
    CWD.mkdir(parents=True, exist_ok=True)
    todo = [m for m in CORPUS if not ids or m["id"] in ids]
    jobs = [(m, v) for m in todo for v in ("plain", "k")]
    with ThreadPoolExecutor(max_workers=4) as ex:
        for res in ex.map(lambda mv: run_variant(*mv), jobs):
            print(json.dumps({k: res[k] for k in ("id", "variant", "exit", "duration_s")}), flush=True)


if __name__ == "__main__":
    main(sys.argv[1:])
