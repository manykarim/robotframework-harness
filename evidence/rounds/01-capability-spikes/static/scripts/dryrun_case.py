"""Run `robot --dryrun` on one file (rf-mcp's current suite-validation approach).

Executed with the target venv's python. Prints one JSON object:
{rc, elapsed_s, tests: [{name, status, message}], errors: [str]}
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
    extra = sys.argv[2:]  # e.g. --pythonpath libs --variable X:1
    with tempfile.TemporaryDirectory() as tmp:
        out = str(Path(tmp) / "output.xml")
        opts = dict(dryrun=True, output=out, log="NONE", report="NONE", console="none")
        # translate a tiny subset of CLI args
        pythonpath, variables = [], []
        it = iter(extra)
        for a in it:
            if a == "--pythonpath":
                pythonpath.append(next(it))
            elif a == "--variable":
                variables.append(next(it))
        if pythonpath:
            opts["pythonpath"] = pythonpath
        if variables:
            opts["variable"] = variables
        buf = io.StringIO()
        t0 = time.perf_counter()
        with redirect_stdout(buf), redirect_stderr(buf):
            rc = robot.run(src, **opts)
        elapsed = time.perf_counter() - t0
        tests, errors = [], []
        try:
            res = ExecutionResult(out)
            for t in res.suite.all_tests:
                tests.append({"name": t.name, "status": t.status, "message": t.message})
            for m in res.errors.messages:
                errors.append(f"{m.level}: {m.message.splitlines()[0]}")
        except Exception as e:  # noqa: BLE001
            errors.append(f"RESULT-PARSE: {e}")
        print(json.dumps({"rc": rc, "elapsed_s": round(elapsed, 3), "tests": tests, "errors": errors}))


if __name__ == "__main__":
    main()
