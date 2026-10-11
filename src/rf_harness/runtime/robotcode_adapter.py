"""The only module that touches robotcode internals (pinned to robotcode >=2.7,<2.8; contract tests in
tests/runtime/test_robotcode_adapter.py).

robotcode has no stable Python API for what the harness needs, so every internal name the runtime uses is listed here
once and re-exported lazily (PEP 562): `from .robotcode_adapter import BaseInterpreter` imports only
`robotcode.repl.base_interpreter`, so the live-session daemon does not pay for the analyzer and vice versa.

Used for:
  * the live session: `Application`, `BaseInterpreter` (subclassed by engine.Helper) and `run_repl` (one RF suite
    whose body is fed from the helper's request queue);
  * the static gate: `CodeAnalyzer` + `AnalyzeConfig`/`ModifiersConfig` + robot.toml loading
    (`get_config_files`, `load_robot_config_from_path`) + LSP `Uri`/`FileEvent`/`FileChangeType` (analyzer.WarmAnalyzer,
    lintd);
  * keyword documentation: the `robotcode libdoc` command line (docsgen), run in a subprocess.
"""

from __future__ import annotations

import importlib
import os
import subprocess
import sys
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import TYPE_CHECKING, Any

SUPPORTED_RANGE = ((2, 7), (2, 8))  # >=2.7,<2.8, same as the `runtime` extra

_NAMES = {
    # live session (REPL embedding)
    "Application": "robotcode.plugin",
    "BaseInterpreter": "robotcode.repl.base_interpreter",
    "run_repl": "robotcode.repl.run",
    # static analysis
    "CodeAnalyzer": "robotcode.analyze.code.code_analyzer",
    "AnalyzeConfig": "robotcode.analyze.config",
    "ModifiersConfig": "robotcode.analyze.config",
    "FileChangeType": "robotcode.core.lsp.types",
    "FileEvent": "robotcode.core.lsp.types",
    "Uri": "robotcode.core.uri",
    "load_robot_config_from_path": "robotcode.robot.config.loader",
    "get_config_files": "robotcode.robot.config.utils",
}

__all__ = [
    "AnalyzeConfig",
    "Application",
    "BaseInterpreter",
    "CodeAnalyzer",
    "FileChangeType",
    "FileEvent",
    "ModifiersConfig",
    "Uri",
    "get_config_files",
    "load_robot_config_from_path",
    "run_repl",
    "SUPPORTED_RANGE",
    "changed_file_events",
    "document_uri",
    "is_supported",
    "libdoc",
    "new_application",
    "robotcode_command",
    "robotcode_version",
]

if TYPE_CHECKING:  # pragma: no cover - static names for type checkers only
    from robotcode.analyze.code.code_analyzer import CodeAnalyzer
    from robotcode.analyze.config import AnalyzeConfig, ModifiersConfig
    from robotcode.core.lsp.types import FileChangeType, FileEvent
    from robotcode.core.uri import Uri
    from robotcode.plugin import Application
    from robotcode.repl.base_interpreter import BaseInterpreter
    from robotcode.repl.run import run_repl
    from robotcode.robot.config.loader import load_robot_config_from_path
    from robotcode.robot.config.utils import get_config_files


def __getattr__(name: str) -> Any:
    module = _NAMES.get(name)
    if module is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    value = getattr(importlib.import_module(module), name)
    globals()[name] = value  # cache: next access skips __getattr__
    return value


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(__all__))


# ------------------------------------------------------------------------------------------------ version
def robotcode_version() -> str:
    """Installed robotcode version ("" when robotcode is missing)."""
    try:
        from importlib.metadata import PackageNotFoundError, version
    except ImportError:  # pragma: no cover
        return ""
    try:
        return version("robotcode")
    except PackageNotFoundError:
        return ""


def is_supported(ver: str | None = None) -> bool:
    """True when `ver` (default: the installed robotcode) lies in SUPPORTED_RANGE."""
    ver = robotcode_version() if ver is None else ver
    try:
        major_minor = tuple(int(x) for x in ver.split(".")[:2])
    except ValueError:
        return False
    lo, hi = SUPPORTED_RANGE
    return len(major_minor) == 2 and lo <= major_minor < hi


# ------------------------------------------------------------------------------------------------ live session
def new_application(root: Path | None = None) -> Any:
    """A robotcode `Application` rooted at `root` (default: cwd), as `robotcode repl` builds it."""
    app = __getattr__("Application")()
    app.config.root = Path(root or os.getcwd())
    return app


# ------------------------------------------------------------------------------------------------ static analysis
def document_uri(path: Path) -> Any:
    """Normalized LSP document URI of a file (key of the analyzer's document store)."""
    return __getattr__("Uri").from_path(path).normalized()


def changed_file_events(paths: Iterable[str]) -> list[Any]:
    """`did_change_watched_files` events for files edited on disk."""
    uri, event, kind = __getattr__("Uri"), __getattr__("FileEvent"), __getattr__("FileChangeType")
    return [event(str(uri.from_path(p)), kind.CHANGED) for p in paths]


# ------------------------------------------------------------------------------------------------ libdoc
def robotcode_command(python: str | None = None) -> list[str]:
    """argv prefix of the `robotcode` CLI next to `python` (default: this interpreter)."""
    py = Path(python or sys.executable)
    exe = py.parent / ("robotcode.exe" if os.name == "nt" else "robotcode")
    return [str(exe)] if exe.is_file() else [str(py), "-m", "robotcode"]


def libdoc(args: Sequence[str], timeout: float = 60, python: str | None = None,
           root: str | os.PathLike | None = None) -> subprocess.CompletedProcess:
    """`robotcode libdoc <args>` in a subprocess without PYTHONPATH (docs come from the project environment as a plain
    run sees it), e.g. `libdoc(["--specdocformat", "raw", "Browser", "spec.json"])` or
    `libdoc(["BuiltIn", "show", "Log"])`.

    The project root is always passed explicitly (`--root`, default: the current directory): robotcode otherwise
    derives it from the common base of its path arguments, which fails when they sit on different Windows drives and
    can pick the wrong directory elsewhere (research trap G3)."""
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)
    base = str(Path(root) if root is not None else Path.cwd())
    return subprocess.run([*robotcode_command(python), "--root", base, "libdoc", *args], capture_output=True,
                          text=True, timeout=timeout, env=env)
