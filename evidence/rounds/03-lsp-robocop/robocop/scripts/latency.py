"""Round 3 / robocop: latency + output size for linting one agent-written file (latency/small/e3.robot, 3 errors).

Cold = new robocop process per call. Warm = in-process Python API (robocop.run.check_files(return_result=True)).
Project-size effect: e3.robot dropped into projects of 36 / 180 agent-written files (project rules parse +
lint the whole project root even when one file is passed).
Writes ../out/latency.json
"""

from __future__ import annotations

import json
import shutil
import statistics
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
R3 = HERE.parent
LAT = R3 / "latency"
VENV = Path("~/workspace/robotcode-experiments/.venv/bin")
WT = Path("~/workspace/rf-mcp-robotcode/.venv/bin")
PROFILE = str(R3 / "configs" / "robocop-agent.toml")
OUT = R3 / "out"


def timed(cmd: list[str], cwd: Path, n: int = 5) -> dict:
    ts = []
    out = ""
    for _ in range(n):
        t0 = time.perf_counter()
        p = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=300)
        ts.append(time.perf_counter() - t0)
        out = p.stdout
    return {"median_s": round(statistics.median(ts), 3), "min_s": round(min(ts), 3), "max_s": round(max(ts), 3),
            "n": n, "stdout_chars": len(out), "tail": out[-160:]}


def rc(bin_dir: Path, root: Path, *extra: str) -> list[str]:
    return [str(bin_dir / "robocop"), "check", "--skip-gitignore", "--root", str(root), "--exit-zero", *extra]


def build_big(times: int) -> Path:
    big = LAT / f"big{times}"
    if big.exists():
        shutil.rmtree(big)
    big.mkdir(parents=True)
    src = R3 / "noise_corpus"
    for k in range(times):
        for d in src.iterdir():
            if d.is_dir():
                shutil.copytree(d, big / f"c{k}_{d.name}")
    shutil.copy(LAT / "small" / "e3.robot", big / "e3.robot")
    return big


def main() -> None:
    small = LAT / "small"
    res: dict = {}
    nc = ["--no-cache"]
    # --- cold CLI, small project (1 file) ---
    res["cold_default_rules"] = timed(rc(VENV, small, *nc, "e3.robot"), small)
    res["cold_agent_profile"] = timed(rc(VENV, small, *nc, "--config", PROFILE, "e3.robot"), small)
    res["cold_agent_no_analyze_libraries"] = timed(
        rc(VENV, small, *nc, "--config", PROFILE, "--no-analyze-libraries", "e3.robot"), small)
    res["cold_agent_library_workers"] = timed(
        rc(VENV, small, *nc, "--config", PROFILE, "--library-workers", "e3.robot"), small, n=3)
    cache_dir = LAT / "cache_small"
    shutil.rmtree(cache_dir, ignore_errors=True)
    first = timed(rc(VENV, small, "--cache-dir", str(cache_dir), "--config", PROFILE, "e3.robot"), small, n=1)
    res["cached_agent_first_run"] = first
    res["cached_agent_unchanged"] = timed(rc(VENV, small, "--cache-dir", str(cache_dir), "--config", PROFILE,
                                             "e3.robot"), small)
    # modify the file each run -> file cache miss, library cache hit
    e3 = small / "e3.robot"
    original = e3.read_text()
    ts = []
    for k in range(5):
        e3.write_text(original + f"\n# edit {k} {time.time()}\n")
        t0 = time.perf_counter()
        subprocess.run(rc(VENV, small, "--cache-dir", str(cache_dir), "--config", PROFILE, "e3.robot"), cwd=small,
                       capture_output=True, text=True)
        ts.append(time.perf_counter() - t0)
    e3.write_text(original)
    res["cached_agent_file_edited"] = {"median_s": round(statistics.median(ts), 3), "n": 5}
    res["robotcode_analyze_cold"] = timed([str(VENV / "robotcode"), "-r", str(small), "analyze", "code",
                                           "--output-format", "concise", "e3.robot"], small, n=3)
    # --- project size effect ---
    for times in (1, 5):
        big = build_big(times)
        nfiles = len(list(big.rglob("*.robot")))
        key = f"project_{nfiles}_files"
        res[key] = {
            "default_rules_one_file": timed(rc(WT, big, *nc, "e3.robot"), big, n=3),
            "agent_profile_one_file": timed(rc(WT, big, *nc, "--config", PROFILE, "e3.robot"), big, n=3),
        }
        cdir = LAT / f"cache_big{times}"
        shutil.rmtree(cdir, ignore_errors=True)
        subprocess.run(rc(WT, big, "--cache-dir", str(cdir), "--config", PROFILE, "e3.robot"), cwd=big,
                       capture_output=True, text=True)
        res[key]["agent_profile_one_file_cached"] = timed(
            rc(WT, big, "--cache-dir", str(cdir), "--config", PROFILE, "e3.robot"), big, n=3)
        res[key]["agent_profile_one_file_cached_project_off"] = timed(
            rc(WT, big, "--cache-dir", str(cdir), "--config", PROFILE, "--no-project", "e3.robot"), big, n=3)
        print(key, json.dumps(res[key], indent=None)[:600], flush=True)
    # --- warm in-process API ---
    p = subprocess.run([str(VENV / "python"), str(HERE / "warm_api.py"), str(small / "e3.robot"), PROFILE],
                       capture_output=True, text=True, timeout=600)
    res["warm_api"] = json.loads(p.stdout.strip().splitlines()[-1]) if p.stdout.strip() else {"err": p.stderr[-800:]}
    (OUT / "latency.json").write_text(json.dumps(res, indent=1))
    for k, v in res.items():
        if not k.startswith("project_"):
            print(k, {kk: vv for kk, vv in v.items() if kk != "tail"} if isinstance(v, dict) else v)


if __name__ == "__main__":
    main()
