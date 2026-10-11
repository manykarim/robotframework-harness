"""Run one .robot file with robot (dry-run or real) and print a JSON summary.

usage: python run_case.py <file> [--real] [--pythonpath P]...
Prints {rc, elapsed_s, tests:[{name,status,message}], errors:[level: msg]}  (errors incl. deprecation WARNs)
"""

import io
import json
import sys
import tempfile
import time
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

import robot
from robot.api import ExecutionResult


def main() -> None:
    src = sys.argv[1]
    args = sys.argv[2:]
    real = "--real" in args
    pythonpath = [args[i + 1] for i, a in enumerate(args) if a == "--pythonpath"]
    with tempfile.TemporaryDirectory() as tmp:
        out = str(Path(tmp) / "output.xml")
        opts = dict(dryrun=not real, output=out, log="NONE", report="NONE", console="none")
        if pythonpath:
            opts["pythonpath"] = pythonpath
        buf = io.StringIO()
        t0 = time.perf_counter()
        with redirect_stdout(buf), redirect_stderr(buf):
            rc = robot.run(src, **opts)
        elapsed = time.perf_counter() - t0
        tests, errors = [], []
        try:
            res = ExecutionResult(out)
            for t in res.suite.all_tests:
                tests.append({"name": t.name, "status": t.status, "message": t.message[:300]})
            for m in res.errors.messages:
                errors.append(f"{m.level}: {m.message.splitlines()[0][:300]}")
        except Exception as e:  # noqa: BLE001
            errors.append(f"RESULT-PARSE: {e}")
        print(json.dumps({"rc": rc, "elapsed_s": round(elapsed, 3), "tests": tests, "errors": errors}))


if __name__ == "__main__":
    main()
