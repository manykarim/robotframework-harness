"""run_ab_resilient.sh: distinct exit codes, cleanup of invalid rows, resume to completion (stub harness, offline)."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest
from eval_helpers import EVAL, claude_402_events, posix_only, result_row, write_gz_transcript, write_jsonl

pytestmark = [posix_only, pytest.mark.skipif(shutil.which("flock") is None, reason="needs flock(1)")]

STUB_HARNESS = textwrap.dedent('''\
    import json, os, sys
    args = sys.argv[1:]
    out = args[args.index("--out-dir") + 1]
    tag = args[args.index("--tag") + 1]
    res = os.path.join(out, f"results_live_{tag}.jsonl")
    with open(os.environ["STUB_CALLS"], "a") as f:
        f.write(" ".join(args) + "\\n")
    for key in [k for k in os.environ.get("STUB_WRITE", "").split(",") if k]:
        a, arm, s, rep = key.split("|")
        with open(res, "a") as f:
            f.write(json.dumps({"key": key, "agent": a, "arm": arm, "scenario": s, "rep": int(rep),
                                "status": "ok", "primary_pass": True}) + "\\n")
    sys.exit(int(os.environ.get("STUB_RC", "0")))
''')


def _run(tmp_path: Path, rc: int, write: str, expected: int, tag: str = "t"):
    stub = tmp_path / "stub_harness.py"
    stub.write_text(STUB_HARNESS)
    env = {k: v for k, v in os.environ.items() if not k.startswith(("AB_", "OPENROUTER"))}
    env.update({"AB_OUT_DIR": str(tmp_path / "out"), "AB_HARNESS_CMD": f"{sys.executable} {stub}",
                "AB_EXPECTED": str(expected), "AB_AUTH_CMD": "true", "AB_MAX_PASSES": "2", "AB_MIN_FREE_GB": "0.01",
                "STUB_RC": str(rc), "STUB_WRITE": write, "STUB_CALLS": str(tmp_path / "calls.txt")})
    p = subprocess.run(["bash", str(EVAL / "run_ab_resilient.sh"), tag, "prototype-v32,rf-harness", "1", "codex",
                        "live"], env=env, capture_output=True, text=True, timeout=120)
    log = (tmp_path / "out" / f"run_ab_{tag}.log").read_text()
    return p.returncode, log


def test_complete_run_exits_0(tmp_path):
    rc, log = _run(tmp_path, 0, "codex|rf-harness|tricentis_quote|1,codex|prototype-v32|tricentis_quote|1", 2)
    assert rc == 0, log
    assert "done: complete (2/2)" in log
    calls = (tmp_path / "calls.txt").read_text()
    assert "--out-dir" in calls and "--max-turns 80" in calls and "--tag t" in calls


@pytest.mark.parametrize("hrc,code,text", [(5, 5, "exit 5"), (4, 4, "exit 4"), (6, 6, "exit 6"), (2, 2, "exit 2")])
def test_harness_exit_codes_are_propagated_without_restart(tmp_path, hrc, code, text):
    rc, log = _run(tmp_path, hrc, "", 2)
    assert rc == code, log
    assert text in log
    assert (tmp_path / "calls.txt").read_text().count("run ") == 1          # no second pass


def test_incomplete_after_passes_exits_1(tmp_path):
    rc, log = _run(tmp_path, 0, "", 3)
    assert rc == 1 and "still incomplete after 2 passes" in log


def test_start_cleanup_relabels_402_rows_and_reruns_them(tmp_path):
    out = tmp_path / "out"
    write_gz_transcript(out / "transcripts_live_t" / "cc-or" / "c.jsonl.gz", claude_402_events())
    write_jsonl(out / "results_live_t.jsonl", [
        result_row("codex|rf-harness|tricentis_quote|1", transcript="transcripts_live_t/cc-or/c.jsonl.gz",
                   agent="cc-or:qwen3.8-flash"),
        result_row("codex|prototype-v32|tricentis_quote|1", status="aborted"),
    ])
    rc, log = _run(tmp_path, 0, "codex|rf-harness|tricentis_quote|1,codex|prototype-v32|tricentis_quote|1", 2)
    assert rc == 0, log
    assert "start cleanup: dropped 1 aborted/torn rows, 1 rows re-labelled invalid" in log
    rows = [json.loads(ln) for ln in (out / "results_live_t.jsonl").read_text().splitlines()]
    assert [r["status"] for r in rows] == ["invalid", "ok", "ok"]
    assert list(out.glob("results_live_t.bak.*.jsonl"))


def test_second_runner_for_the_same_tag_exits_3(tmp_path):
    import fcntl

    (tmp_path / "out").mkdir()
    with open(tmp_path / "out" / ".run_ab_t.lock", "w") as fh:
        fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
        rc, log = _run(tmp_path, 0, "", 1)
    assert rc == 3 and "holds" in log
