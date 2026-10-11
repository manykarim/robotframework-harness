"""Exp 2e: are robot.toml [tool.robotcode-analyze.modifiers] honored by the language server?"""
import sys
from pathlib import Path
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from lsp_client import LSP, short
def main():
    P = HERE / "proj2"; f = P / ".rf" / "live.robot"
    text = "*** Test Cases ***\nLive\n    Log    ${DYN_B}\n    Lgo    x\n"
    f.write_text(text)
    lsp = LSP("~/workspace/robotcode-experiments/.venv/bin/robotcode", P)
    lsp.initialize({"robocop": {"enabled": False}})
    u, v, t0 = lsp.open(f, text)
    r = lsp.wait_diags(u, v, t0, timeout=60, settle=1.2)
    print([short(d) for d in r["diags"]])
    lsp.shutdown()
if __name__ == "__main__":
    main()
