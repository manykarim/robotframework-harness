"""Exp 2d: can a helper-maintained variable file remove dynamic-variable FPs in the LANGUAGE SERVER?"""
import json, sys, time
from pathlib import Path
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from lsp_client import LSP, short
RC = "~/workspace/robotcode-experiments/.venv/bin/robotcode"
P = HERE / "proj2"
def main():
    out = {}
    vf = P / ".rf" / "session_vars.py"
    vf.write_text("# written by the helper\n")
    f = P / ".rf" / "live.robot"
    text = "*** Test Cases ***\nLive\n    Log    ${DYN_A}\n"
    f.write_text(text)
    lsp = LSP(RC, P, log=HERE / "logs" / "exp2d.stderr")
    lsp.initialize({"robocop": {"enabled": False}}, watch="--watch" in sys.argv)
    u, v, t0 = lsp.open(f, text)
    r = lsp.wait_diags(u, v, t0, timeout=60, settle=1.2)
    out["1 before"] = [short(d) for d in r["diags"]]
    vf.write_text("DYN_A = 'x'\n")
    u, v, t0 = lsp.append(f, "    Log    again\n")  # doc change, no watched-files event
    r = lsp.wait_diags(u, v, t0, timeout=20, settle=1.2)
    out["2 varfile written + doc change, no didChangeWatchedFiles"] = [short(d) for d in r["diags"]]
    lsp.notify("workspace/didChangeWatchedFiles", {"changes": [{"uri": vf.as_uri(), "type": 2}]})
    time.sleep(2.5)
    u, v, t0 = lsp.append(f, "    Log    again2\n")
    r = lsp.wait_diags(u, v, t0, timeout=20, settle=1.2)
    out["3 after didChangeWatchedFiles + doc change"] = [short(d) for d in r["diags"]]
    out["server_requests"] = sorted(set(lsp.server_requests))
    if "--watch" in sys.argv:
        lsp.shutdown(); print(out); return
    lsp.shutdown()
    lsp = LSP(RC, P, log=HERE / "logs" / "exp2d.stderr")
    lsp.initialize({"robocop": {"enabled": False}})
    u, v, t0 = lsp.open(f, lsp_text := f.read_text())
    r = lsp.wait_diags(u, v, t0, timeout=60, settle=1.2)
    out["4 fresh LS"] = [short(d) for d in r["diags"]]
    lsp.shutdown()
    # settings route: robotcode.robot.variables in initializationOptions
    vf.write_text("# written by the helper\n")
    lsp = LSP(RC, P, log=HERE / "logs" / "exp2d.stderr")
    lsp.initialize({"robocop": {"enabled": False}, "robot": {"variables": {"DYN_A": "x"}}})
    u, v, t0 = lsp.open(f, f.read_text())
    r = lsp.wait_diags(u, v, t0, timeout=60, settle=1.2)
    out["5 settings robotcode.robot.variables"] = [short(d) for d in r["diags"]]
    lsp.shutdown()
    for k, v in out.items():
        print(k, v)
    (HERE / "results" / "exp2d_varfile.json").write_text(json.dumps(out, indent=1))
if __name__ == "__main__":
    main()
