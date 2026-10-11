"""Helpers for the hook launcher tests (plugins/rf-harness/bin/rfh-launch): fake environments with a fake runtime."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import sysconfig
import venv
from pathlib import Path

from rf_harness import __version__

REPO = Path(__file__).resolve().parents[2]
BIN = REPO / "plugins" / "rf-harness" / "bin"
LAUNCHER = BIN / "rfh-launch"
IS_WINDOWS = os.name == "nt"

# The fake runtime echoes what it received: argv, stdin, selected env vars; exit code from the payload ("exit").
FAKE_HOOK = r'''
import json, os, sys
data = sys.stdin.buffer.read()
try:
    payload = json.loads(data.decode() or "{}")
except ValueError:
    payload = {}
print(json.dumps({"fake_runtime": True, "argv": sys.argv[1:], "stdin_len": len(data),
                  "stdin_sha": __import__("hashlib").sha256(data).hexdigest(), "python": sys.executable,
                  "env": {k: v for k, v in os.environ.items() if k.startswith("RFH_")}}))
sys.exit(int(payload.get("exit", 0)) if isinstance(payload, dict) else 0)
'''


def base_python() -> str:
    """The real interpreter behind the test venv (a venv's python is a symlink / launcher to it)."""
    return getattr(sys, "_base_executable", None) or sys.executable


def site_packages(prefix: Path) -> Path:
    if IS_WINDOWS:
        return prefix / "Lib" / "site-packages"
    return prefix / "lib" / f"python{sys.version_info.major}.{sys.version_info.minor}" / "site-packages"


def add_runtime(site: Path, version: str | None = __version__, with_package: bool = True) -> None:
    site.mkdir(parents=True, exist_ok=True)
    if with_package:
        pkg = site / "rf_harness" / "runtime"
        pkg.mkdir(parents=True, exist_ok=True)
        (site / "rf_harness" / "__init__.py").write_text("", encoding="utf-8")
        (pkg / "__init__.py").write_text("", encoding="utf-8")
        (pkg / "hook.py").write_text(FAKE_HOOK, encoding="utf-8")
    if version:
        dist = site / f"robotframework_harness-{version}.dist-info"
        dist.mkdir(exist_ok=True)
        (dist / "METADATA").write_text(f"Metadata-Version: 2.1\nName: robotframework-harness\nVersion: {version}\n\n",
                                       encoding="utf-8")


def make_venv(prefix: Path, runtime: str | None = __version__, with_package: bool = True) -> Path:
    """A minimal virtual environment (symlinked interpreter + pyvenv.cfg) with an optional fake runtime."""
    if IS_WINDOWS:
        venv.EnvBuilder(with_pip=False, symlinks=False).create(prefix)
        python = prefix / "Scripts" / "python.exe"
    else:
        (prefix / "bin").mkdir(parents=True, exist_ok=True)
        python = prefix / "bin" / "python"
        real = os.path.realpath(base_python())
        if not python.exists():
            python.symlink_to(real)
        version = sysconfig.get_python_version()
        (prefix / "pyvenv.cfg").write_text(
            f"home = {os.path.dirname(real)}\ninclude-system-site-packages = false\nversion = {version}\n",
            encoding="utf-8")
    site = site_packages(prefix)
    site.mkdir(parents=True, exist_ok=True)
    if runtime or with_package:
        add_runtime(site, runtime, with_package)
    return python


def run_launcher(args: list[str], payload: dict | bytes | None, env: dict[str, str], cwd: Path,
                 timeout: float = 60) -> subprocess.CompletedProcess[bytes]:
    data = payload if isinstance(payload, bytes) else (json.dumps(payload).encode() if payload is not None else b"")
    return subprocess.run([sys.executable, "-S", str(LAUNCHER), *args], input=data, capture_output=True, env=env,
                          cwd=str(cwd), timeout=timeout)


def output_json(proc: subprocess.CompletedProcess[bytes]) -> dict:
    lines = [line for line in proc.stdout.decode().splitlines() if line.strip()]
    assert len(lines) == 1, proc.stdout.decode() + proc.stderr.decode()
    return json.loads(lines[0])
