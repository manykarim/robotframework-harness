"""One live step through the real live session, for `rf-harness doctor`:

    python -m rf_harness.runtime.smoke --page <path-or-url> [--timeout 10]

Starts the live-session daemon (`rf_harness.runtime.execd`, exactly as the hooks do) in a throwaway project directory,
opens the page in headless chromium (Browser library), reads its title and prints one JSON line
{"ok": bool, "title": str|null, "ms": int[, "error": str]}. Exit code 0 when the title was read, else 1. Every process
it started (daemon, Playwright node, chromium) is stopped and the directory removed before it exits; the daemon also
watches this process and exits by itself if the smoke is killed.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

from . import hookcore as hc
from . import procs, proto


def page_url(page: str) -> str:
    """URL for New Page: URLs pass through, file paths become file:// URIs."""
    if "://" in page or page.startswith(("about:", "data:")):
        return page
    return Path(page).expanduser().resolve().as_uri()


def _cells(url: str) -> list[str]:
    return ["Import Library    Browser\n"
            "New Browser    chromium    headless=True\n"
            f"New Page    {url}\n"
            "${title}=    Get Title"]


def _cleanup(d: hc.Dirs) -> None:
    tokens = [st.get("token_env") for st in (proto.read_state(d.exec) or {},) if st.get("token_env")]
    with contextlib.suppress(Exception):
        hc.stop_daemons(d, wait=5.0)
    t_end = time.monotonic() + 5.0
    left: list[int] = []
    while time.monotonic() < t_end:
        left = [p for t in tokens for p in procs.token_procs(t) if p != os.getpid()]
        if not left:
            break
        time.sleep(0.1)
    if left:
        procs.terminate(left, grace=1.0)


def run(page: str, timeout: float = 10.0) -> dict[str, Any]:
    t0 = time.monotonic()
    url = page_url(page)
    if url.startswith("file:") and not Path(page).expanduser().exists():
        return {"ok": False, "title": None, "ms": 0, "error": f"no such file: {page}"}
    ws = Path(tempfile.mkdtemp(prefix="rfh-smoke-"))
    d = hc.Dirs(ws).make()
    os.environ["RFH_WATCH_PID"] = str(os.getpid())       # the daemon exits when this process is gone
    res: dict[str, Any] = {"ok": False, "title": None}

    def left() -> float:
        return max(0.5, timeout - (time.monotonic() - t0))

    try:
        st = hc.start_daemon(d, "exec", wait=left())
        if st is None:
            log = _tail(d.exec / "daemon.log")
            res["error"] = "live session did not start within the timeout" + (f": {log}" if log else "")
            return res
        r = hc.request(st, {"op": "step", "cells": _cells(url), "guard": False, "timeout": left()}, timeout=left() + 2)
        steps = r.get("steps") or []
        if r.get("ok") and steps and steps[-1].get("status") == "PASS":
            res.update(ok=True, title=steps[-1].get("ret", ""))
        elif r.get("status") == "running":
            res["error"] = f"no title within {timeout:g} s"
        else:
            bad = next((s for s in steps if s.get("status") != "PASS"), None)
            res["error"] = (f"{bad.get('kw')}: {bad.get('msg')}" if bad else
                            "; ".join(r.get("errors") or []) or str(r.get("error") or "step failed"))[:500]
        return res
    finally:
        _cleanup(d)
        shutil.rmtree(ws, ignore_errors=True)
        res["ms"] = round((time.monotonic() - t0) * 1000)


def _tail(path: Path, n: int = 300) -> str:
    try:
        return " ".join(path.read_text(errors="replace").split())[-n:]
    except OSError:
        return ""


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="rf_harness.runtime.smoke", description=__doc__.split("\n\n")[0])
    ap.add_argument("--page", required=True, help="HTML file path or URL to open")
    ap.add_argument("--timeout", type=float, default=10.0, help="seconds for the whole smoke step (default 10)")
    o = ap.parse_args(argv)
    res = run(o.page, o.timeout)
    sys.stdout.write(json.dumps(res) + "\n")
    sys.stdout.flush()
    return 0 if res.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
