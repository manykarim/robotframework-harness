"""Tiny timing helper library: Measure <kw> <args> -> records elapsed, status, message to JSONL."""
import json, os, time
from robot.libraries.BuiltIn import BuiltIn

OUT = os.environ.get("TIMING_OUT", "logs/timing.jsonl")

class timing:
    ROBOT_LIBRARY_SCOPE = "GLOBAL"
    def measure(self, label, name, *args):
        bi = BuiltIn()
        t0 = time.time()
        status, msg = "PASS", ""
        try:
            ret = bi.run_keyword(name, *args)
        except Exception as e:  # noqa
            status, msg = "FAIL", str(e)
        dt = round(time.time() - t0, 3)
        rec = {"label": label, "kw": name, "args": [str(a) for a in args], "status": status, "elapsed": dt, "msg": msg[:600]}
        with open(OUT, "a") as f:
            f.write(json.dumps(rec) + "\n")
        bi.log_to_console(f"{label}: {status} {dt}s {msg[:160]}")
        return dt
