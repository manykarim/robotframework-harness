"""The 224-check simulation suite of the v3.2 prototype (verify_hooks.py) as one pytest test.

Runs verify_hooks.py in a subprocess into tmp_path (it mutates os.environ and drives real daemons, browsers and plain
robot runs) and asserts the parity bar of task 2.2:
  * all 224 checks ran and at least 221 pass;
  * scenario L (v3.2: covered `label:has(#id)` target, read-streak nudge) is fully green;
  * the scenario-D pre-tool lint timing check ("D[...] planted typo in a new file ... 'not blocking' warning") is a
    tolerated flake: when it fails, scenario D is re-run once and its result replaces the first one; if it still
    fails it is allowed to fail (it then just counts against the 221).
Needs the `browser` dependency group (Browser + RequestsLibrary) and chromium: `uv sync --group dev --group browser`,
`uv run rfbrowser init --skip-browsers` (browsers from ~/.cache/ms-playwright) -- skipped otherwise.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

import pytest

pytestmark = [pytest.mark.browser, pytest.mark.slow]

HERE = Path(__file__).resolve().parent
TOTAL = 224
MIN_PASS = 221
FLAKY = re.compile(r"^D\[\w+\] planted typo in a new file .*'not blocking' warning")
SCENARIO_L = re.compile(r"^L(\d|:)")


def _procs_under(path: Path) -> list:
    out = []
    for n in os.listdir("/proc"):
        if not n.isdigit() or int(n) == os.getpid():
            continue
        try:
            with open(f"/proc/{n}/cmdline", "rb") as f:
                cl = f.read().decode(errors="replace")
            cwd = os.readlink(f"/proc/{n}/cwd")
        except OSError:
            continue
        if str(path) in cl or cwd.startswith(str(path)):
            out.append(int(n))
    return out


def _sweep(path: Path) -> list:
    """processes still pointing at the work root (daemons, Playwright node, chromium) -> terminated; returns them."""
    from rf_harness.runtime import procs

    t_end = time.time() + 10
    left = _procs_under(path)
    while left and time.time() < t_end:
        time.sleep(0.5)
        left = _procs_under(path)
    if left:
        procs.terminate(left, grace=2.0)
    return left


def _run(root: Path, only: str | None = None) -> dict:
    root.mkdir(parents=True, exist_ok=True)
    env = {k: v for k, v in os.environ.items() if k not in ("CLAUDE_PROJECT_DIR", "RFH_ROOT", "ONLY")}
    env["PYTHONUNBUFFERED"] = "1"
    if only:
        env["ONLY"] = only
    try:
        with open(root / "verify.log", "w") as log:
            subprocess.run([sys.executable, str(HERE / "verify_hooks.py"), str(root)], cwd=str(root), env=env,
                           stdout=log, stderr=subprocess.STDOUT, timeout=3600, stdin=subprocess.DEVNULL)
    finally:
        leftovers = _sweep(root)
    res = json.loads((root / "results_hooks.json").read_text())
    res["leftover_pids"] = leftovers
    return res


def test_simulation_suite(tmp_path, browser_ready):
    res = _run(tmp_path / "run")
    checks = res["checks"]
    failed = [c for c in checks if not c["ok"]]
    flaky = [c["check"] for c in failed if FLAKY.match(c["check"])]
    retried = {}
    if flaky:
        retry = _run(tmp_path / "retry", only="d")
        retried = {c["check"]: c["ok"] for c in retry["checks"] if c["check"] in flaky}
    ok = {c["check"]: c["ok"] or retried.get(c["check"], False) for c in checks}
    passed = sum(ok.values())
    tolerated = [n for n in flaky if not ok[n]]
    hard = [c for c in failed if not ok[c["check"]] and c["check"] not in tolerated]
    summary = (f"simulation: {passed}/{len(checks)} passed (first run {res['passed']}/{res['total']}, "
               f"{res['wall_s']} s); retried flaky: {len(flaky)}; tolerated: {tolerated}; "
               f"failed: {[c['check'] for c in hard]}")
    print(summary)
    (tmp_path / "summary.txt").write_text(summary + "\n" + json.dumps(hard, indent=1))
    assert len(checks) == TOTAL, summary
    l_checks = [n for n in ok if SCENARIO_L.match(n)]
    assert len(l_checks) == 8 and all(ok[n] for n in l_checks), {n: ok[n] for n in l_checks}
    assert passed >= MIN_PASS, summary + "\n" + json.dumps(hard, indent=1)[:4000]
    assert not res["leftover_pids"], f"processes left behind in the work root: {res['leftover_pids']}"
