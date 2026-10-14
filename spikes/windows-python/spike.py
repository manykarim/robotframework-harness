"""Windows spike for change fix-windows-python-detection (run on GitHub-hosted Windows runners).

Answers, with evidence:
  Q1  Is the Microsoft Store placeholder (App Execution Alias) present, and how does it behave when run WITH arguments
      (exit code, stderr, does it hang)?
  Q2  What do os.path.isfile / os.access / os.lstat report for the alias (decides whether path scans pick it up)?
  Q3  With a "no Python installed" PATH, what do shutil.which("python3"/"python"/"py") return, and does
      `uvx robotframework-harness@1.0.0 install ... --dry-run` reproduce "did not start"?
  Q4  Does uv skip the placeholder: `uv python find` (default / only-system), `uv venv --python 3.12`; is the new
      venv usable? Is UV set for processes started by uvx on Windows?
  Q5  What happens to the plugin-mode hook command (`python3 -S .../rfh-launch`) and rfh-launch.cmd under cmd and
      Git Bash with that PATH?
Writes spike_results.json and a Markdown summary (also to $GITHUB_STEP_SUMMARY).
"""

from __future__ import annotations

import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import time
from pathlib import Path

OUT = Path(os.environ.get("SPIKE_OUT", "spike_out"))
OUT.mkdir(parents=True, exist_ok=True)
LOCAL = Path(os.environ.get("LOCALAPPDATA", ""))
WINDOWSAPPS = LOCAL / "Microsoft" / "WindowsApps"
UV = shutil.which("uv")
UVX = shutil.which("uvx")
RESULTS: dict = {"python_running_spike": sys.version, "uv": UV, "uvx": UVX}


def run(cmd, env=None, cwd=None, timeout=120, shell=False):
    t0 = time.monotonic()
    try:
        p = subprocess.run(cmd, env=env, cwd=cwd, capture_output=True, text=True, timeout=timeout,
                           stdin=subprocess.DEVNULL, shell=shell, errors="replace")
        return {"cmd": cmd if isinstance(cmd, str) else " ".join(map(str, cmd)), "rc": p.returncode,
                "stdout": p.stdout[-1500:], "stderr": p.stderr[-1500:], "s": round(time.monotonic() - t0, 2)}
    except subprocess.TimeoutExpired:
        return {"cmd": str(cmd), "rc": "TIMEOUT", "s": timeout}
    except OSError as e:
        return {"cmd": str(cmd), "rc": f"OSError: {e}"}


def file_facts(p: Path) -> dict:
    d = {"path": str(p)}
    try:
        st = os.lstat(p)
        d["lstat_size"] = st.st_size
        d["reparse_point"] = bool(getattr(st, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT)
        d["reparse_tag"] = hex(getattr(st, "st_reparse_tag", 0))
    except OSError as e:
        d["lstat_error"] = str(e)
    try:
        os.stat(p)
        d["stat_ok"] = True
    except OSError as e:
        d["stat_error"] = str(e)
    d["isfile"] = os.path.isfile(p)
    d["access_x"] = os.access(p, os.X_OK)
    try:
        d["readlink"] = os.readlink(p)
    except (OSError, ValueError) as e:
        d["readlink_error"] = f"{type(e).__name__}: {e}"
    return d


# ---------------------------------------------------------------- Q1/Q2: the WindowsApps aliases
aliases = []
if WINDOWSAPPS.is_dir():
    for f in sorted(WINDOWSAPPS.iterdir()):
        if f.name.lower().startswith(("python", "py")) and f.suffix.lower() == ".exe":
            facts = file_facts(f)
            facts["probe"] = run([str(f), "-c", "import sys; print(sys.executable)"], timeout=30)
            aliases.append(facts)
RESULTS["windowsapps_dir"] = str(WINDOWSAPPS)
RESULTS["windowsapps_exists"] = WINDOWSAPPS.is_dir()
RESULTS["windowsapps_python_aliases"] = aliases
RESULTS["appx_desktopappinstaller"] = run(
    ["powershell", "-NoProfile", "-Command",
     "Get-AppxPackage -Name Microsoft.DesktopAppInstaller | Select-Object -ExpandProperty Version"], timeout=60)
RESULTS["appx_python"] = run(
    ["powershell", "-NoProfile", "-Command", "Get-AppxPackage -Name *Python* | Select-Object -ExpandProperty Name"],
    timeout=60)

# ---------------------------------------------------------------- Q3: a "no Python installed" PATH
sysroot = os.environ.get("SystemRoot", r"C:\Windows")
clean_path = os.pathsep.join(p for p in [
    rf"{sysroot}\System32", sysroot, rf"{sysroot}\System32\Wbem", rf"{sysroot}\System32\WindowsPowerShell\v1.0",
    str(WINDOWSAPPS), str(Path(UV).parent) if UV else "", r"C:\Program Files\Git\cmd",
] if p)
clean_env = {k: v for k, v in os.environ.items() if k.upper() not in ("PATH", "VIRTUAL_ENV", "CONDA_PREFIX",
                                                                     "PYTHONHOME", "PYTHONPATH", "UV_PYTHON")}
clean_env["PATH"] = clean_path
RESULTS["clean_path"] = clean_path
RESULTS["which_clean"] = {n: shutil.which(n, path=clean_path) for n in ("python3", "python", "py", "uv", "uvx")}
RESULTS["which_full"] = {n: shutil.which(n) for n in ("python3", "python", "py")}

proj = Path(tempfile.mkdtemp(prefix="rfh-spike-proj-"))
(proj / "tests").mkdir()
(proj / "tests" / "t.robot").write_text("*** Test Cases ***\nT\n    Log    hi\n", encoding="utf-8")
if UVX:
    RESULTS["installer_repro"] = run([UVX, "robotframework-harness@1.0.0", "install", "--agent", "claude-code",
                                      "--mode", "files", "--dry-run", "--no-input"],
                                     env=clean_env, cwd=str(proj), timeout=300)
    RESULTS["uv_env_under_uvx"] = run([UVX, "--from", "robotframework-harness@1.0.0", "python", "-c",
                                       "import os,sys; print('UV=', os.environ.get('UV')); print(sys.executable)"],
                                      env=clean_env, cwd=str(proj), timeout=300)

    RESULTS["which_inside_uvx"] = run([UVX, "--from", "robotframework-harness@1.0.0", "python", "-c",
                                       "import shutil,sys,os; print('python3=', shutil.which('python3')); "
                                       "print('python=', shutil.which('python')); print('prefix=', sys.prefix); "
                                       "print('VIRTUAL_ENV=', os.environ.get('VIRTUAL_ENV'))"],
                                      env=clean_env, cwd=str(proj), timeout=300)

# ---------------------------------------------------------------- Q3c: a synthetic placeholder (exit 9009 + message)
# Hosted images without App Installer have no real alias: a tiny python3.cmd... is not an .exe, so build a real exe
# placeholder by copying the venv launcher is not possible either; use a C# one-liner compiled with csc if present.
stub_dir = Path(tempfile.mkdtemp(prefix="rfh-stub-"))
csc = next(iter(sorted(Path(sysroot, "Microsoft.NET", "Framework64").glob("v4*/csc.exe"))), None)
if csc:
    src = stub_dir / "stub.cs"
    src.write_text('class P{static int Main(string[] a){System.Console.Error.WriteLine("Python was not found; run '
                   'without arguments to install from the Microsoft Store, or disable this shortcut from Settings > '
                   'Apps > Advanced app settings > App execution aliases.");return 9009;}}', encoding="utf-8")
    RESULTS["stub_build"] = run([str(csc), "/nologo", f"/out:{stub_dir / 'python3.exe'}", str(src)], timeout=120)
    stub_env = dict(clean_env)
    stub_env["PATH"] = str(stub_dir) + os.pathsep + clean_path
    RESULTS["synthetic_stub_probe"] = run([str(stub_dir / "python3.exe"), "-c", "print(1)"], env=stub_env)
    if UVX:
        RESULTS["installer_with_synthetic_stub"] = run(
            [UVX, "robotframework-harness@1.0.0", "install", "--agent", "claude-code", "--mode", "files",
             "--dry-run", "--no-input"], env=stub_env, cwd=str(Path(tempfile.mkdtemp(prefix="rfh-spike-p2-"))),
            timeout=300)

# ---------------------------------------------------------------- Q4: uv discovery and uv venv
if UV:
    RESULTS["uv_python_find_default"] = run([UV, "python", "find"], env=clean_env, timeout=120)
    RESULTS["uv_python_find_only_system"] = run([UV, "python", "find", "--python-preference", "only-system"],
                                                env=clean_env, timeout=120)
    RESULTS["uv_python_list"] = run([UV, "python", "list"], env=clean_env, timeout=120)
    venv = proj / ".venv"
    RESULTS["uv_venv_312"] = run([UV, "venv", "--python", "3.12", str(venv)], env=clean_env, cwd=str(proj),
                                 timeout=600)
    vpy = venv / "Scripts" / "python.exe"
    RESULTS["venv_python_exists"] = vpy.is_file()
    if vpy.is_file():
        RESULTS["venv_python_probe"] = run([str(vpy), "-c", "import sys; print(sys.version, sys.executable)"],
                                           env=clean_env, timeout=60)
        RESULTS["installer_with_venv"] = run([UVX, "robotframework-harness@1.0.0", "install", "--agent",
                                              "claude-code", "--mode", "files", "--dry-run", "--no-input"],
                                             env=clean_env, cwd=str(proj), timeout=300)

# ---------------------------------------------------------------- Q5: hook bootstrap under cmd and Git Bash
plugin = Path(__file__).resolve().parents[2] / "plugins" / "rf-harness" / "bin"
launch = plugin / "rfh-launch"
payload = json.dumps({"hook_event_name": "SessionStart", "cwd": str(proj), "source": "startup"})


def with_stdin(cmd, shell=False):
    t0 = time.monotonic()
    try:
        p = subprocess.run(cmd, env=clean_env, cwd=str(proj), input=payload, capture_output=True, text=True,
                           timeout=60, shell=shell, errors="replace")
        return {"cmd": cmd if isinstance(cmd, str) else " ".join(cmd), "rc": p.returncode,
                "stdout": p.stdout[-800:], "stderr": p.stderr[-800:], "s": round(time.monotonic() - t0, 2)}
    except Exception as e:  # noqa: BLE001
        return {"cmd": str(cmd), "rc": f"{type(e).__name__}: {e}"}


RESULTS["hook_cmd_python3"] = with_stdin(f'python3 -S "{launch}" SessionStart --agent claude', shell=True)
RESULTS["hook_cmd_launcher_cmd"] = with_stdin(f'"{plugin / "rfh-launch.cmd"}" SessionStart --agent claude',
                                              shell=True)
bash = Path(r"C:\Program Files\Git\bin\bash.exe")
if bash.is_file():
    posix_launch = str(launch).replace("\\", "/")
    RESULTS["gitbash_which_python3"] = run([str(bash), "-lc", "command -v python3; command -v python; "
                                            "command -v py; echo PATH=$PATH"], env=clean_env, timeout=60)
    RESULTS["hook_gitbash_python3"] = with_stdin([str(bash), "-c", f'python3 -S "{posix_launch}" SessionStart '
                                                  "--agent claude"])

(OUT / "spike_results.json").write_text(json.dumps(RESULTS, indent=1), encoding="utf-8")


# ---------------------------------------------------------------- summary
def rc(key):
    v = RESULTS.get(key) or {}
    return f"rc={v.get('rc')} {(v.get('stderr') or v.get('stdout') or '').strip().splitlines()[-1:] or ''}"


lines = [f"# Windows Python spike ({os.environ.get('ImageOS', '?')} / {os.environ.get('ImageVersion', '?')})", "",
         f"- WindowsApps exists: {RESULTS['windowsapps_exists']}; python aliases: "
         f"{[Path(a['path']).name for a in aliases]}",
         f"- App Installer (DesktopAppInstaller): {RESULTS['appx_desktopappinstaller'].get('stdout', '').strip()!r}"]
for a in aliases:
    pr = a.get("probe", {})
    lines.append(f"  - {Path(a['path']).name}: isfile={a.get('isfile')} x={a.get('access_x')} "
                 f"reparse={a.get('reparse_point')} tag={a.get('reparse_tag')} stat_ok={a.get('stat_ok', False)} "
                 f"-> probe rc={pr.get('rc')} {pr.get('s')}s stderr={pr.get('stderr', '').strip()[:160]!r}")
lines += [f"- which (clean PATH): {RESULTS['which_clean']}",
          f"- installer repro: {rc('installer_repro')}",
          f"- UV under uvx: {(RESULTS.get('uv_env_under_uvx') or {}).get('stdout', '').strip()!r}",
          f"- which inside uvx: {(RESULTS.get('which_inside_uvx') or {}).get('stdout', '').strip()!r}",
          f"- synthetic stub probe: {rc('synthetic_stub_probe')}",
          f"- installer with synthetic stub on PATH: {rc('installer_with_synthetic_stub')}",
          f"- uv python find (default): {rc('uv_python_find_default')}",
          f"- uv python find (only-system): {rc('uv_python_find_only_system')}",
          f"- uv venv --python 3.12: {rc('uv_venv_312')}; venv python ok: "
          f"{(RESULTS.get('venv_python_probe') or {}).get('rc') == 0}",
          f"- installer with .venv present: {rc('installer_with_venv')}",
          f"- hook `python3 -S rfh-launch` (cmd): {rc('hook_cmd_python3')}",
          f"- hook rfh-launch.cmd: {rc('hook_cmd_launcher_cmd')}",
          f"- Git Bash: {(RESULTS.get('gitbash_which_python3') or {}).get('stdout', '').strip()[:300]!r}",
          f"- hook via Git Bash python3: {rc('hook_gitbash_python3')}"]
md = "\n".join(lines) + "\n"
(OUT / "summary.md").write_text(md, encoding="utf-8")
if os.environ.get("GITHUB_STEP_SUMMARY"):
    with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as fh:
        fh.write(md)
print(md)
