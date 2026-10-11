"""Find the project's Python environment and provision the harness runtime into it (design D2/D3, task 4.3).

Order: ``--python``, the active environment (``VIRTUAL_ENV``, ``CONDA_PREFIX``), ``<project>/.venv``, a uv- or
poetry-managed environment (``UV_PROJECT_ENVIRONMENT``; ``poetry env info --path``), then ``python3`` on PATH.
The runtime is installed only with consent, pinned to the installer's own version
(``robotframework-harness[runtime]==<version>``) with ``uv pip`` (fallback ``python -m pip``). Test libraries and
browser binaries are never installed; the libraries the project's suites import are reported with the exact command.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .. import __version__
from . import transforms as _x

DIST = "robotframework-harness"
HARNESS_JSON = Path(".rf") / "harness.json"
SKIP_DIRS = {".git", ".venv", "venv", "node_modules", ".rf", ".rf-harness", "results", "output", "__pycache__",
             ".tox", ".nox", "site-packages", "dist", "build"}
STANDARD_LIBRARIES = {"BuiltIn", "Collections", "DateTime", "Dialogs", "OperatingSystem", "Process", "Screenshot",
                      "String", "Telnet", "XML", "Remote", "Easter", "Reserved"}
LIBRARY_PACKAGES = {
    "Browser": "robotframework-browser",
    "SeleniumLibrary": "robotframework-seleniumlibrary",
    "RequestsLibrary": "robotframework-requests",
    "AppiumLibrary": "robotframework-appiumlibrary",
    "DatabaseLibrary": "robotframework-databaselibrary",
    "SSHLibrary": "robotframework-sshlibrary",
    "JSONLibrary": "robotframework-jsonlibrary",
    "DataDriver": "robotframework-datadriver",
    "REST": "RESTinstance",
    "FakerLibrary": "robotframework-faker",
    "PlatynUI": "robotframework-platynui",
    "Mainframe3270": "robotframework-mainframe3270",
    "DebugLibrary": "robotframework-debuglibrary",
    "Pabot": "robotframework-pabot",
}
_LIBRARY_LINE = re.compile(r"^Library(?: {2,}|\t+|\s*\|\s*)(?P<name>[^\s|][^|\t]*?)(?=(?: {2,}|\t|\s+\||$))", re.M)
_SETTINGS = re.compile(r"^\*+\s*settings?\s*\**\s*$", re.I | re.M)
_SECTION = re.compile(r"^\*+\s*[^*\n]+", re.M)


@dataclass
class EnvChoice:
    python: Path | None
    source: str
    detail: str = ""

    @property
    def found(self) -> bool:
        return self.python is not None


def venv_python(prefix: Path) -> Path | None:
    names = (("Scripts", "python.exe"), ("python.exe",)) if os.name == "nt" else (("bin", "python"), ("bin", "python3"))
    for parts in names:
        candidate = prefix.joinpath(*parts)
        if candidate.is_file():
            return candidate
    return None


def _poetry_env(project: Path) -> Path | None:
    pyproject = project / "pyproject.toml"
    try:
        text = pyproject.read_text(encoding="utf-8")
    except OSError:
        return None
    if "[tool.poetry" not in text and not (project / "poetry.lock").is_file():
        return None
    exe = shutil.which("poetry")
    if exe:
        try:
            proc = subprocess.run([exe, "env", "info", "--path"], cwd=str(project), capture_output=True, text=True,
                                  timeout=30, stdin=subprocess.DEVNULL)
            path = proc.stdout.strip().splitlines()[-1] if proc.returncode == 0 and proc.stdout.strip() else ""
            if path and venv_python(Path(path)):
                return venv_python(Path(path))
        except (OSError, subprocess.SubprocessError, IndexError):
            pass
    return _poetry_env_computed(project, text)


def _poetry_env_computed(project: Path, pyproject_text: str) -> Path | None:
    """Poetry's own naming (EnvManager.generate_env_name) without running poetry."""
    import base64
    import hashlib

    name = None
    for section in ("tool.poetry", "project"):
        match = re.search(r"^\[" + re.escape(section) + r"\]\s*$(.*?)(?=^\[|\Z)", pyproject_text, re.M | re.S)
        if match:
            found = re.search(r"""^name\s*=\s*["']([^"']+)["']""", match.group(1), re.M)
            if found:
                name = found.group(1)
                break
    if not name:
        return None
    if os.environ.get("POETRY_VIRTUALENVS_PATH"):
        base = Path(os.environ["POETRY_VIRTUALENVS_PATH"])
    elif os.environ.get("POETRY_CACHE_DIR"):
        base = Path(os.environ["POETRY_CACHE_DIR"]) / "virtualenvs"
    elif os.name == "nt":
        base = Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local"))) / "pypoetry" / "Cache" / \
            "virtualenvs"
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Caches" / "pypoetry" / "virtualenvs"
    else:
        base = Path(os.environ.get("XDG_CACHE_HOME", str(Path.home() / ".cache"))) / "pypoetry" / "virtualenvs"
    sanitized = re.sub(r'[ $`!*@"\\\r\n\t]', "_", name.lower())[:42]
    digest = hashlib.sha256(os.path.normcase(os.path.realpath(project)).encode("utf-8")).digest()
    prefix = f"{sanitized}-{base64.urlsafe_b64encode(digest).decode()[:8]}-py"
    if not base.is_dir():
        return None
    for entry in sorted((p for p in base.iterdir() if p.name.startswith(prefix)), reverse=True):
        python = venv_python(entry)
        if python:
            return python
    return None


def find_env(project: Path, explicit: str | None = None) -> EnvChoice:
    if explicit:
        path = Path(explicit).expanduser()
        if path.is_dir():
            python = venv_python(path)
            return EnvChoice(python, "--python", f"environment {path}")
        if path.is_file():
            return EnvChoice(path, "--python", explicit)
        which = shutil.which(explicit)
        if which:
            return EnvChoice(Path(which), "--python", explicit)
        return EnvChoice(None, "--python", f"--python {explicit} does not exist")
    for var in ("VIRTUAL_ENV", "CONDA_PREFIX"):
        value = os.environ.get(var)
        if value:
            python = venv_python(Path(value))
            if python:
                return EnvChoice(python, var, f"active environment {value}")
    python = venv_python(project / ".venv")
    if python:
        return EnvChoice(python, ".venv", "project virtual environment")
    uv_env = os.environ.get("UV_PROJECT_ENVIRONMENT")
    if uv_env:
        path = Path(uv_env) if os.path.isabs(uv_env) else project / uv_env
        python = venv_python(path)
        if python:
            return EnvChoice(python, "UV_PROJECT_ENVIRONMENT", f"uv project environment {path}")
    python = _poetry_env(project)
    if python:
        return EnvChoice(python, "poetry", "poetry-managed environment")
    which = shutil.which("python3") or (shutil.which("python") if os.name == "nt" else None)
    if which:
        return EnvChoice(Path(which), "PATH", "python3 on PATH (no project environment found)")
    return EnvChoice(None, "none", "no Python interpreter found")


# ------------------------------------------------------------------------------------------------ inspection
_INSPECT = r"""
import importlib.metadata as md, importlib.util as iu, json, sys
def ver(d):
    try:
        return md.version(d)
    except Exception:
        return None
def spec(m):
    try:
        return iu.find_spec(m) is not None
    except Exception:
        return False
mods = json.loads(sys.argv[1])
print(json.dumps({"python": sys.version.split()[0], "executable": sys.executable,
    "sys_path": [p for p in sys.path if p],
    "versions": {d: ver(d) for d in ("robotframework", "robotcode", "robotframework-harness",
                                      "robotframework-browser", "robotframework-robocop")},
    "imports": {m: spec(m) for m in mods}}))
"""


def inspect(python: Path, modules: list[str] | None = None, timeout: float = 60.0) -> dict[str, Any] | None:
    mods = sorted({"robot", "robotcode", "rf_harness.runtime", "rf_harness.runtime.hook", *(modules or [])})
    try:
        proc = subprocess.run([str(python), "-c", _INSPECT, json.dumps(mods)], capture_output=True, text=True,
                              timeout=timeout, stdin=subprocess.DEVNULL)
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0:
        return None
    try:
        data = json.loads(proc.stdout.strip().splitlines()[-1])
    except (ValueError, IndexError):
        return None
    return data if isinstance(data, dict) else None


def runtime_ready(info: dict[str, Any] | None) -> bool:
    if not info:
        return False
    imports = info.get("imports", {})
    return bool(imports.get("robot") and imports.get("robotcode") and imports.get("rf_harness.runtime.hook"))


def runtime_compatible(info: dict[str, Any] | None) -> bool:
    version = (info or {}).get("versions", {}).get(DIST)
    return bool(version) and str(version).split(".")[:2] == __version__.split(".")[:2]


# ------------------------------------------------------------------------------------------------ provisioning
def install_command(python: Path, version: str = __version__, source: str | None = None) -> list[str]:
    requirement = f"{DIST}[runtime]=={version}"
    if source:
        requirement = f"{Path(source).expanduser().resolve()}[runtime]"
    uv = shutil.which("uv")
    if uv:
        return [uv, "pip", "install", "--python", str(python), requirement]
    return [str(python), "-m", "pip", "install", requirement]


def run_install(python: Path, version: str = __version__, source: str | None = None) -> tuple[bool, str]:
    cmd = install_command(python, version, source)
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=900, stdin=subprocess.DEVNULL)
    except (OSError, subprocess.SubprocessError) as exc:
        return False, f"{' '.join(cmd)}: {exc}"
    tail = "\n".join((proc.stderr or proc.stdout or "").strip().splitlines()[-12:])
    return proc.returncode == 0, tail


def write_harness_json(project: Path, updates: dict[str, Any]) -> Path:
    path = project / HARNESS_JSON
    try:
        data, _ = _x.load_json_object(path)
    except (OSError, ValueError):
        data = {}
    data.update(updates)
    _x.write_text_if_changed(path, _x.dump_json(data))
    return path


def harness_json(project: Path) -> dict[str, Any]:
    try:
        data, _ = _x.load_json_object(project / HARNESS_JSON)
    except (OSError, ValueError):
        return {}
    return data


# ------------------------------------------------------------------------------------------------ libraries
def _suite_files(project: Path, limit: int = 2000) -> list[Path]:
    found: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(project):
        dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS and not d.startswith("."))
        for name in sorted(filenames):
            if name.endswith((".robot", ".resource")):
                found.append(Path(dirpath) / name)
                if len(found) >= limit:
                    return found
    return found


def _settings_text(text: str) -> str:
    parts: list[str] = []
    for match in _SETTINGS.finditer(text):
        nxt = _SECTION.search(text, match.end())
        parts.append(text[match.end(): nxt.start() if nxt else len(text)])
    return "\n".join(parts)


def scan_libraries(project: Path) -> dict[str, list[str]]:
    """``{library: [files importing it]}`` for module libraries (standard libraries and file paths excluded)."""
    libs: dict[str, list[str]] = {}
    for path in _suite_files(project):
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for match in _LIBRARY_LINE.finditer(_settings_text(text)):
            name = match.group("name").strip()
            if not name or "${" in name or "/" in name or "\\" in name or name.endswith(".py"):
                continue
            if name in STANDARD_LIBRARIES or name.split(".")[0] in STANDARD_LIBRARIES:
                continue
            rel = str(path.relative_to(project))
            libs.setdefault(name, [])
            if rel not in libs[name]:
                libs[name].append(rel)
    return libs


@dataclass
class LibraryStatus:
    name: str
    files: list[str]
    importable: bool
    package: str | None = None
    fix: str = ""
    extra: list[str] = field(default_factory=list)


def _pip_hint(python: Path, package: str) -> str:
    if shutil.which("uv"):
        return f"uv pip install --python {python} {package}"
    return f"{python} -m pip install {package}"


def browser_binaries_present(info: dict[str, Any]) -> bool:
    """Whether Playwright browsers exist for the Browser library (bundled, PLAYWRIGHT_BROWSERS_PATH or the cache)."""
    roots: list[Path] = []
    for entry in info.get("sys_path", []):
        core = Path(entry) / "Browser" / "wrapper" / "node_modules" / "playwright-core" / ".local-browsers"
        roots.append(core)
    if os.environ.get("PLAYWRIGHT_BROWSERS_PATH"):
        roots.append(Path(os.environ["PLAYWRIGHT_BROWSERS_PATH"]))
    if os.name == "nt":
        roots.append(Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local"))) / "ms-playwright")
    elif sys.platform == "darwin":
        roots.append(Path.home() / "Library" / "Caches" / "ms-playwright")
    else:
        roots.append(Path.home() / ".cache" / "ms-playwright")
    return any(r.is_dir() and any(p.name.startswith("chromium") for p in r.iterdir()) for r in roots)


def library_report(python: Path, libs: dict[str, list[str]], info: dict[str, Any] | None = None) -> list[LibraryStatus]:
    if not libs:
        return []
    info = info or inspect(python, sorted(libs)) or {}
    imports = info.get("imports", {})
    missing_imports = [n for n in libs if n not in imports]
    if missing_imports:
        extra = inspect(python, sorted(libs)) or {}
        imports = {**imports, **extra.get("imports", {})}
        info = {**info, **{k: v for k, v in extra.items() if k == "sys_path"}}
    report: list[LibraryStatus] = []
    for name, files in sorted(libs.items()):
        package = LIBRARY_PACKAGES.get(name)
        ok = bool(imports.get(name))
        status = LibraryStatus(name, files, ok, package)
        if not ok:
            status.fix = _pip_hint(python, package) if package else f"install the package that provides {name}"
        elif name == "Browser" and not browser_binaries_present(info):
            rfbrowser = python.parent / ("rfbrowser.exe" if os.name == "nt" else "rfbrowser")
            status.extra.append("Browser is installed but no Playwright browsers were found")
            status.fix = f"{rfbrowser if rfbrowser.exists() else 'rfbrowser'} init chromium"
        report.append(status)
    return report
