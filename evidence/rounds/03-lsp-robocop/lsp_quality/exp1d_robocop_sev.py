"""Exp 1d: severity of default robocop noise in the LS, and whether a robocop config file can mute it."""
import json, sys
from pathlib import Path
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from lsp_client import LSP, short
RC = "~/workspace/robotcode-experiments/.venv/bin/robotcode"
P = HERE / "proj"
def run(label):
    f = P / ".rf" / "noise.robot"
    text = "*** Settings ***\nLibrary    Browser\n\n*** Test Cases ***\nLive\n    New Page    ${BASE_URL}\n    ${t}=    Get Title\n    Set Test Variable    ${x}    1\n"
    f.write_text(text)
    lsp = LSP(RC, P, log=HERE / "logs" / "exp1d.stderr")
    lsp.initialize({})
    u, v, t0 = lsp.open(f, text)
    r = lsp.wait_diags(u, v, t0, timeout=60, settle=1.5, source=None)
    lsp.shutdown()
    rows = [(d.get("source"), d.get("severity"), short(d)) for d in r["all_diags"]]
    print(label); [print("  ", x) for x in rows]
    return rows
def main():
    out = {"default": run("default (no robocop config)")}
    cfg = P / "robocop.toml"
    cfg.write_text('[tool.robocop.lint]\nselect = ["ERR*"]\n')
    try:
        out["robocop.toml select ERR*"] = run("with proj/robocop.toml select=ERR*")
    finally:
        cfg.unlink()
    (HERE / "results" / "exp1d_robocop_sev.json").write_text(json.dumps(out, indent=1))
if __name__ == "__main__":
    main()
