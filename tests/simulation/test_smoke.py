"""`python -m rf_harness.runtime.smoke` (used by `rf-harness doctor`): one live step in headless chromium."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent


def _smoke(*args: str) -> tuple[int, dict]:
    r = subprocess.run([sys.executable, "-m", "rf_harness.runtime.smoke", *args], capture_output=True, text=True,
                       timeout=120)
    return r.returncode, json.loads(r.stdout.strip().splitlines()[-1])


@pytest.mark.browser
def test_smoke_reads_the_page_title(browser_ready):
    rc, res = _smoke("--page", str(HERE / "site" / "login.html"), "--timeout", "30")
    assert rc == 0 and res["ok"] and res["title"] == "Shop - Sign in", res
    assert isinstance(res["ms"], int)


@pytest.mark.skipif(not sys.platform.startswith("linux"), reason="live runtime: Linux")
def test_smoke_reports_a_missing_page():
    rc, res = _smoke("--page", str(HERE / "site" / "no-such-page.html"), "--timeout", "5")
    assert rc == 1 and not res["ok"] and "no such file" in res["error"]
