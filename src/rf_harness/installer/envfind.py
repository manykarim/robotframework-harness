"""Find the project's Python environment and provision the harness runtime into it (design D2/D3, task 4.3).

Order: ``--python``, the active environment (``VIRTUAL_ENV``, ``CONDA_PREFIX``), ``<project>/.venv``, a uv- or
poetry-managed environment (``UV_PROJECT_ENVIRONMENT``; ``poetry env info --path``), then ``python3`` on PATH.
Every candidate is probed before use (change fix-windows-python-detection): the Microsoft Store placeholder, too-old
and broken interpreters, and the installer's own (uvx) environment are skipped with a recorded reason. When nothing is
usable, the CLI offers to create ``<project>/.venv`` with uv.
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
from collections.abc import Iterator
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


MIN_PYTHON = (3, 10)
APPEXECLINK = 0x8000001B            # IO_REPARSE_TAG_APPEXECLINK: an App Execution Alias in ...\WindowsApps
STORE_EXIT_CODES = (9009, 49)       # 49 = 9009 mod 256 (MSYS shells, POSIX exit status)
STORE_MARKERS = ("microsoft store", "app execution alias")
STORE_PLACEHOLDER = "the Microsoft Store placeholder (App Execution Alias), not a Python installation"
ALIAS_TIP = "turn off the alias under Settings > Apps > Advanced app settings > App execution aliases"
UV_INSTALL_URL = "https://docs.astral.sh/uv/getting-started/installation/"
DEFAULT_VENV_PYTHON = "3.12"
# No "%" or quotes that cmd.exe would touch: .cmd/.bat shims (pyenv-win) pass arguments through cmd.exe.
_PROBE = "import sys; print('.'.join(map(str, sys.version_info[:3]))); print(sys.executable)"


@dataclass
class Probe:
    """Result of running a candidate interpreter once (design D1)."""

    status: str                     # usable | store-placeholder | too-old | broken
    version: str = ""
    executable: str = ""
    detail: str = ""

    @property
    def usable(self) -> bool:
        return self.status == "usable"

    def reason(self) -> str:
        if self.status == "store-placeholder":
            return STORE_PLACEHOLDER
        if self.status == "too-old":
            return f"Python {self.version} is too old (the harness needs {'.'.join(map(str, MIN_PYTHON))} or newer)"
        if self.status == "broken":
            return f"does not run ({self.detail})"
        return f"Python {self.version}"


@dataclass
class Skipped:
    label: str                      # where it came from, e.g. "python3 on PATH", ".venv"
    python: Path
    reason: str
    status: str                     # a Probe status, or "excluded"


@dataclass
class EnvChoice:
    python: Path | None
    source: str
    detail: str = ""
    skipped: list[Skipped] = field(default_factory=list)

    @property
    def found(self) -> bool:
        return self.python is not None

    @property
    def placeholder_skipped(self) -> bool:
        return any(s.status == "store-placeholder" for s in self.skipped)


def is_app_alias(path: str | Path) -> bool:
    """A Windows App Execution Alias in a ``WindowsApps`` folder, from file metadata only."""
    if os.name != "nt":
        return False
    try:
        tag = getattr(os.lstat(path), "st_reparse_tag", 0)
    except OSError:
        return False
    return tag == APPEXECLINK and os.path.basename(os.path.dirname(str(path))).lower() == "windowsapps"


def probe(python: str | Path, timeout: float = 15.0) -> Probe:
    """Run ``python`` once with arguments (so the Store placeholder only prints its message) and classify it."""
    try:
        proc = subprocess.run([str(python), "-c", _PROBE], capture_output=True, text=True, errors="replace",
                              timeout=timeout, stdin=subprocess.DEVNULL)
    except subprocess.TimeoutExpired:
        return Probe("broken", detail=f"no answer within {timeout:g} s")
    except OSError as exc:
        return Probe("store-placeholder" if is_app_alias(python) else "broken", detail=str(exc))
    output = (proc.stdout or "") + (proc.stderr or "")
    first = next((line.strip() for line in output.splitlines() if line.strip()), "")
    if proc.returncode in STORE_EXIT_CODES or any(m in output.lower() for m in STORE_MARKERS):
        return Probe("store-placeholder", detail=f"exit {proc.returncode}: {first}" if first else "")
    if proc.returncode != 0:
        status = "store-placeholder" if is_app_alias(python) else "broken"
        return Probe(status, detail=f"exit {proc.returncode}" + (f": {first}" if first else ""))
    lines = (proc.stdout or "").strip().splitlines()
    match = re.fullmatch(r"(\d+)\.(\d+)\.(\d+)", lines[0].strip()) if lines else None
    if not match:
        return Probe("broken", detail=f"unexpected output: {first[:80]}" if first else "no output")
    version = lines[0].strip()
    executable = lines[1].strip() if len(lines) > 1 else ""
    if (int(match.group(1)), int(match.group(2))) < MIN_PYTHON:
        return Probe("too-old", version, executable)
    return Probe("usable", version, executable)


def explain_failure(python: Path) -> str:
    """Why ``python`` cannot be used, for an interpreter that failed the package report."""
    result = probe(python)
    if not result.usable:
        return result.reason()
    return f"Python {result.version} runs, but its package report failed; check it with: {python} -m site"


def uv_binary() -> str | None:
    """uv from ``UV`` (set by uvx and ``uv run``), then PATH."""
    value = os.environ.get("UV")
    if value and os.path.isfile(value):
        return value
    return shutil.which("uv")


def _uv_dirs() -> list[tuple[Path, str]]:
    """uv's cache and tool directories (explicit settings and the platform defaults)."""
    home = Path.home()
    if os.name == "nt":
        local = Path(os.environ.get("LOCALAPPDATA", str(home / "AppData" / "Local")))
        roaming = Path(os.environ.get("APPDATA", str(home / "AppData" / "Roaming")))
        cache, tools = local / "uv" / "cache", roaming / "uv" / "data" / "tools"
    else:
        cache = Path(os.environ.get("XDG_CACHE_HOME") or str(home / ".cache")) / "uv"
        tools = Path(os.environ.get("XDG_DATA_HOME") or str(home / ".local" / "share")) / "uv" / "tools"
    dirs = [(cache, "inside uv's cache (a throwaway environment)"), (tools, "a uv tool environment")]
    if os.environ.get("UV_CACHE_DIR"):
        dirs.insert(0, (Path(os.environ["UV_CACHE_DIR"]), "inside uv's cache (a throwaway environment)"))
    if os.environ.get("UV_TOOL_DIR"):
        dirs.insert(0, (Path(os.environ["UV_TOOL_DIR"]), "a uv tool environment"))
    return dirs


def _under(path: Path, root: Path) -> bool:
    forms = {os.path.normcase(os.path.abspath(path)), os.path.normcase(os.path.join(os.path.realpath(path.parent),
                                                                                    path.name))}
    roots = {os.path.normcase(os.path.abspath(root)), os.path.normcase(os.path.realpath(root))}
    return any(f == r or f.startswith(r.rstrip(os.sep) + os.sep) for f in forms for r in roots)


def excluded(python: Path, own_prefix: bool = True) -> str:
    """Why ``python`` must not become the project environment (design D2), or ``""``.

    ``own_prefix``: also exclude the running installer's environment (``sys.prefix``). The PATH fallback uses it, where
    uvx puts its own environment first; a project ``.venv`` or an activated environment that happens to run the
    installer is the project's environment and stays allowed.
    """
    parts = {p.lower() for p in python.parts}
    if "archive-v0" in parts:
        return "the installer's own (uvx) environment" if own_prefix and _under(python, Path(sys.prefix)) \
            else "inside uv's cache (a throwaway environment)"
    if own_prefix and _under(python, Path(sys.prefix)):
        return "the installer's own environment"
    for root, reason in _uv_dirs():
        if _under(python, root):
            return reason
    return ""


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


def _candidates(project: Path) -> Iterator[tuple[str, str, Path, str]]:
    """``(source, label, python, detail)`` in discovery order, computed lazily (poetry runs only when needed)."""
    for var in ("VIRTUAL_ENV", "CONDA_PREFIX"):
        value = os.environ.get(var)
        if value:
            python = venv_python(Path(value))
            if python:
                yield var, var, python, f"active environment {value}"
    python = venv_python(project / ".venv")
    if python:
        yield ".venv", ".venv", python, "project virtual environment"
    uv_env = os.environ.get("UV_PROJECT_ENVIRONMENT")
    if uv_env:
        path = Path(uv_env) if os.path.isabs(uv_env) else project / uv_env
        python = venv_python(path)
        if python:
            yield "UV_PROJECT_ENVIRONMENT", "UV_PROJECT_ENVIRONMENT", python, f"uv project environment {path}"
    python = _poetry_env(project)
    if python:
        yield "poetry", "poetry", python, "poetry-managed environment"
    seen: set[str] = set()
    for name in ("python3", "python") if os.name == "nt" else ("python3",):
        which = shutil.which(name)
        if which and os.path.normcase(which) not in seen:
            seen.add(os.path.normcase(which))
            yield "PATH", f"{name} on PATH", Path(which), f"{name} on PATH (no project environment found)"


def find_env(project: Path, explicit: str | None = None) -> EnvChoice:
    """The first usable candidate; unusable and excluded ones are listed in ``EnvChoice.skipped``."""
    if explicit:
        path = Path(explicit).expanduser()
        python: Path | None
        if path.is_dir():
            python, detail = venv_python(path), f"environment {path}"
            if python is None:
                return EnvChoice(None, "--python", f"--python {explicit}: no Python interpreter in this directory")
        elif path.is_file():
            python, detail = path, explicit
        else:
            which = shutil.which(explicit)
            if not which:
                return EnvChoice(None, "--python", f"--python {explicit} does not exist")
            python, detail = Path(which), explicit
        result = probe(python)
        if not result.usable:
            skip = Skipped("--python", python, result.reason(), result.status)
            return EnvChoice(None, "--python", f"--python {python} is {result.reason()}"
                             if result.status == "store-placeholder" else f"--python {python}: {result.reason()}",
                             [skip])
        return EnvChoice(python, "--python", detail)
    skipped: list[Skipped] = []
    for source, label, python, detail in _candidates(project):
        reason = excluded(python, own_prefix=source == "PATH")
        if reason:
            skipped.append(Skipped(label, python, reason, "excluded"))
            continue
        result = probe(python)
        if result.usable:
            return EnvChoice(python, source, detail, skipped)
        skipped.append(Skipped(label, python, result.reason(), result.status))
    detail = "no usable Python environment" if skipped else "no Python interpreter found"
    return EnvChoice(None, "none", detail, skipped)


def skipped_lines(choice: EnvChoice) -> list[str]:
    """The skip report of design D4: one entry per candidate with its classification."""
    lines: list[str] = []
    for skip in choice.skipped:
        lines.append(f"  skipped  {skip.label:<16} {skip.python}")
        lines.append(f"           -> {skip.reason}")
    return lines


def venv_command(project: Path, version: str = DEFAULT_VENV_PYTHON, uv: str | None = None) -> list[str]:
    return [uv or uv_binary() or "uv", "venv", "--python", version, str(project / ".venv")]


def display_command(cmd: list[str]) -> str:
    """``cmd`` for printing: ``uv`` instead of a full path when that is the uv on PATH."""
    shown = list(cmd)
    if shown and os.path.isabs(shown[0]):
        on_path = shutil.which(Path(shown[0]).name)
        if on_path and os.path.normcase(os.path.realpath(on_path)) == os.path.normcase(os.path.realpath(shown[0])):
            shown[0] = Path(shown[0]).stem
    return " ".join(f'"{part}"' if " " in part else part for part in shown)


def fix_lines(choice: EnvChoice, project: Path, version: str = DEFAULT_VENV_PYTHON) -> list[str]:
    """How to get a usable environment (design D4): uv, ``--python``, and the alias tip for the Store placeholder."""
    uv = uv_binary()
    if uv:
        lines = [f"  - let uv create the project environment: {display_command(venv_command(project, version, uv))}"
                 ", then rerun"]
    else:
        lines = [f"  - install uv ({UV_INSTALL_URL}) and rerun; the installer then creates the project environment "
                 f"with `uv venv --python {version}`"]
    lines.append("  - or pass --python <path> (an interpreter or virtual environment with Python "
                 f"{'.'.join(map(str, MIN_PYTHON))}+)")
    if choice.placeholder_skipped:
        lines.append(f"  - the Microsoft Store placeholder is not Python: install Python, or {ALIAS_TIP}")
    return lines


def create_venv(project: Path, version: str = DEFAULT_VENV_PYTHON, uv: str | None = None,
                timeout: float = 600.0) -> tuple[Path | None, str]:
    """``uv venv --python <version> <project>/.venv``; the new interpreter if it probes usable, else the error text."""
    cmd = venv_command(project, version, uv)
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, errors="replace", timeout=timeout,
                              stdin=subprocess.DEVNULL)
    except (OSError, subprocess.SubprocessError) as exc:
        return None, f"{display_command(cmd)}: {exc}"
    tail = "\n".join((proc.stderr or proc.stdout or "").strip().splitlines()[-12:])
    if proc.returncode != 0:
        return None, tail or f"{display_command(cmd)} exited with {proc.returncode}"
    python = venv_python(project / ".venv")
    if python is None:
        return None, f"{display_command(cmd)} reported success but created no interpreter in {project / '.venv'}"
    result = probe(python)
    if not result.usable:
        return None, f"{python}: {result.reason()}" + (f"\n{tail}" if tail else "")
    return python, tail


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
    uv = uv_binary()
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
    if uv_binary():
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
