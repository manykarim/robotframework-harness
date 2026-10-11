"""start/stop the round-3 filestep helper via the round-2 lifecycle code (cleanup, token, wait_ready).
usage (cwd = project root): <py> fs_ctl.py start|stop|cleanup [daemon opts...]"""
import os, sys
from pathlib import Path
HERE = Path(__file__).resolve().parent
R2 = HERE.parents[1] / "round2" / "python_api"
os.environ["PYTHONPATH"] = os.pathsep.join([str(HERE), str(R2), os.environ.get("PYTHONPATH", "")]).rstrip(os.pathsep)
sys.path[:0] = [str(HERE), str(R2)]
from rfmcp_local import cli, proto
def main():
    cmd, args = sys.argv[1], sys.argv[2:]
    d = proto.state_dir(os.environ.get("RFMCP_DIR", ".rf"))
    if cmd == "start":
        return cli.start(d, ["--pdeathsig", *args], daemon_cmd=[sys.executable, "-m", "filestep_daemon"])
    if cmd == "stop":
        return cli.stop(d, 30.0, graceful=True)
    if cmd == "cleanup":
        cli._out(cli.cleanup(d)); return 0
if __name__ == "__main__":
    sys.exit(main())
