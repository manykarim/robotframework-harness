"""Single-shot in-process batch (no daemon): run RF steps through robotcode's REPL engine, return compact results.

    from rfmcp_local.batch import run_cells
    res = run_cells(["Import Library  RequestsLibrary", "GET  https://example.org"], hooks=("redact",))

CLI: python -m rfmcp_local batch FILE|- [--hooks redact,hints] [-v name:value] [-P path] [-p profile]
     (FILE = RF steps, i.e. a test-case body; every top-level body item becomes one step record)
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from robot.output import LOGGER

from robotcode.plugin import Application
from robotcode.repl.run import run_repl

from .daemon import HelperInterpreter, Request
from .hooks import build_hooks


class _BatchInterpreter(HelperInterpreter):
    def __init__(self, req: Request, **kw: Any) -> None:
        super().__init__(**kw)
        self._pending: Optional[Request] = req

    def _next(self) -> Optional[Request]:
        r, self._pending = self._pending, None
        return r


def run_cells(cells: Sequence[str], *, hooks: Sequence[str] = ("redact",), variables: Sequence[str] = (),
              pythonpath: Sequence[str] = (), outputdir: Optional[str] = None, profiles: Sequence[str] = (),
              stop_on_fail: bool = True, graceful: bool = True, app: Optional[Application] = None) -> Dict[str, Any]:
    t0 = time.perf_counter()
    app = app or Application()
    app.config.profiles = list(profiles) or None
    outdir = os.path.abspath(outputdir or tempfile.mkdtemp(prefix="rfmcp-batch-"))
    Path(outdir).mkdir(parents=True, exist_ok=True)
    req = Request("step", {"cells": list(cells), "stop_on_fail": stop_on_fail})
    interp = _BatchInterpreter(req, hooks=build_hooks(list(hooks)), journal=Path(outdir) / "journal.jsonl")
    interp.graceful = graceful  # close Browser in-process instead of waiting for atexit
    try:
        run_repl(interp, app, variable=tuple(variables), pythonpath=tuple(pythonpath), outputdir=outdir,
                 source=Path.cwd() / "__rfmcp_batch__.robot")
    finally:
        LOGGER.unregister_logger(interp._logger)  # allow repeated in-process batches
    resp = dict(req.resp or {"ok": None, "error": "no result"})
    resp["total_ms"] = round((time.perf_counter() - t0) * 1000, 1)
    if interp.stop_info:
        resp["stop"] = interp.stop_info
    return resp


def main(argv: List[str]) -> int:
    ap = argparse.ArgumentParser(prog="rfmcp_local batch")
    ap.add_argument("file")
    ap.add_argument("--hooks", default="redact")
    ap.add_argument("-v", "--variable", action="append", default=[])
    ap.add_argument("-P", "--pythonpath", action="append", default=[])
    ap.add_argument("-p", "--profile", action="append", default=[])
    ap.add_argument("-d", "--outputdir")
    ap.add_argument("--continue-on-failure", action="store_true")
    a = ap.parse_args(argv)
    text = sys.stdin.read() if a.file == "-" else Path(a.file).read_text()
    res = run_cells([text], hooks=[h for h in a.hooks.split(",") if h], variables=a.variable,
                    pythonpath=a.pythonpath, outputdir=a.outputdir, profiles=a.profile,
                    stop_on_fail=not a.continue_on_failure)
    sys.stdout.write(json.dumps(res, separators=(",", ":"), default=str) + "\n")
    sys.stdout.flush()
    return 0 if res.get("ok") else 1
