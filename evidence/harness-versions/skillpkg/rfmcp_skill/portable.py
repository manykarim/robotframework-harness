"""Portable-suite check: imports that resolve in the helper / robotcode (both add ./lib and ./resources to the
python path when there is no robot.toml, plus any -P) or via PYTHONPATH, but FAIL in a plain `robot <file>` run
from the project root -- the suite then dies with ModuleNotFoundError / "Resource file does not exist".

Only flags an import when the module/file is NOT reachable the way plain robot looks for it AND it DOES exist
somewhere in the project, so the fix (import it by path, relative to ${CURDIR}) is certain.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

SKIP_DIRS = {".git", ".rf", ".venv", "venv", "env", "node_modules", "__pycache__", ".robotcode_cache",
             ".robocop_cache", "site-packages", ".tox", ".mypy_cache", ".pytest_cache", "results", "output"}
FILE_EXT = (".py", ".resource", ".robot", ".txt", ".yaml", ".yml", ".json", ".tsv", ".rst")
VAR_RE = re.compile(r"[$@&%]\{[^}]*\}")


@lru_cache(maxsize=1)
def plain_sys_path() -> Tuple[str, ...]:
    """sys.path of a plain `robot` run: same interpreter, no PYTHONPATH, no cwd entry; + robot/libraries."""
    pp = {os.path.abspath(x) for x in os.environ.get("PYTHONPATH", "").split(os.pathsep) if x}
    script_dir = os.path.dirname(os.path.abspath(sys.argv[0] or "")) if sys.argv and sys.argv[0] else ""
    if sys.path and sys.path[0] and os.path.abspath(sys.path[0]) == script_dir and \
            script_dir != os.path.abspath(os.getcwd()):
        # console-script process (rfmcp hook / rfmcp check): sys.path is already what `robot` gets, minus PYTHONPATH
        paths = [p for p in sys.path[1:] if p and os.path.abspath(p) not in pp]
        return _with_stdlibs(paths)
    env = {k: v for k, v in os.environ.items() if k not in ("PYTHONPATH", "PYTHONSTARTUP", "PYTHONSAFEPATH")}
    try:
        out = subprocess.run([sys.executable, "-c", "import sys,json;print(json.dumps(sys.path[1:]))"],
                             env=env, cwd=tempfile.gettempdir(), capture_output=True, text=True, timeout=30).stdout
        paths = [p for p in json.loads(out) if p]
    except Exception:
        pp = set(filter(None, os.environ.get("PYTHONPATH", "").split(os.pathsep)))
        paths = [p for p in sys.path[1:] if p and p not in pp and Path(p).resolve() != Path.cwd().resolve()]
    return _with_stdlibs(paths)


def _with_stdlibs(paths: List[str]) -> Tuple[str, ...]:
    try:
        import robot

        paths = [str(Path(robot.__file__).parent / "libraries"), *paths]
    except ImportError:
        pass
    return tuple(paths)


def _module_importable(name: str) -> bool:
    from importlib.machinery import PathFinder

    top = name.split(".")[0]
    if top in sys.builtin_module_names:
        return True
    try:
        return PathFinder.find_spec(top, list(plain_sys_path())) is not None
    except Exception:
        return True  # cannot judge -> do not warn


def _walk(root: Path, limit: int = 30000):
    n = 0
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS and not d.startswith(".")]
        for f in filenames:
            n += 1
            if n > limit:
                return
            yield Path(dirpath) / f
        for d in dirnames:
            yield Path(dirpath) / d


def _find_in_project(root: Path, rel_candidates: List[str], near: Path) -> Optional[Path]:
    """first project path whose tail matches one of rel_candidates (posix), closest to `near`."""
    hits = []
    tails = [c.strip("/") for c in rel_candidates if c.strip("/")]
    for p in _walk(root):
        sp = p.as_posix()
        for t in tails:
            if sp.endswith("/" + t) or sp == t:
                hits.append(p)  # a package stays .../pkg/__init__.py: plain robot AND robocop accept that path
                break
        if len(hits) >= 5:
            break
    if not hits:
        return None

    def dist(p: Path) -> int:
        try:
            return len(Path(os.path.relpath(p, near)).parts)
        except ValueError:
            return 99
    return sorted(hits, key=dist)[0]


def _curdir_path(target: Path, suite_dir: Path, is_dir: bool = False) -> str:
    rel = Path(os.path.relpath(target, suite_dir)).as_posix()
    return "${CURDIR}/" + rel + ("/" if is_dir else "")


def _resolve_vars(name: str, suite_dir: Path, root: Path) -> Optional[str]:
    s = name.replace("${CURDIR}", str(suite_dir)).replace("${EXECDIR}", str(root))
    return None if VAR_RE.search(s) else s


def _path_reachable(p: str, suite_dir: Path) -> bool:
    """RF: absolute path, else relative to the importing file's directory, else searched from the module path."""
    cand = Path(p)
    if cand.is_absolute():
        return cand.exists()
    if (suite_dir / cand).exists():
        return True
    return any((Path(d) / cand).exists() for d in plain_sys_path())


def _imports(path: Path) -> List[Tuple[str, str, int]]:
    from robot.api import get_model, get_resource_model

    model = get_resource_model(str(path)) if path.suffix == ".resource" else get_model(str(path))
    out = []
    for sec in model.sections:
        if type(sec).__name__ != "SettingSection":
            continue
        for st in sec.body:
            kind = type(st).__name__
            if kind in ("LibraryImport", "ResourceImport", "VariablesImport") and getattr(st, "name", None):
                out.append((kind.replace("Import", ""), st.name, st.lineno))
    return out


def issues(path: Path, root: Optional[Path] = None) -> List[Dict[str, Any]]:
    """-> [{line, code, msg, fix}] for imports that only resolve through a python path plain robot lacks."""
    path = Path(path).resolve()
    if path.suffix not in (".robot", ".resource") or not path.is_file():
        return []
    root = Path(root or Path.cwd()).resolve()
    suite_dir = path.parent
    out: List[Dict[str, Any]] = []
    try:
        imports = _imports(path)
    except Exception:
        return []
    for kind, name, line in imports:
        resolved = _resolve_vars(name, suite_dir, root)
        if resolved is None:
            continue
        looks_like_path = "/" in resolved or "\\" in resolved or resolved.lower().endswith(FILE_EXT)
        target: Optional[Path] = None
        is_dir = False
        if looks_like_path:
            if _path_reachable(resolved, suite_dir):
                continue
            tail = resolved.replace("\\", "/").lstrip("./")
            target = _find_in_project(root, [tail, Path(tail).name], suite_dir)
        else:  # module name (Library / Variables): plain robot imports it from sys.path only
            if kind == "Resource" or _module_importable(resolved):
                continue
            parts = resolved.split(".")
            cands = ["/".join(parts) + ".py", "/".join(parts) + "/__init__.py"]
            if len(parts) > 1:  # module.ClassName
                cands += ["/".join(parts[:-1]) + ".py", "/".join(parts[:-1]) + "/__init__.py"]
            target = _find_in_project(root, cands, suite_dir)
        if target is None:
            continue  # not in the project either: a plain import error the analyzer reports anyway
        fix = f"{kind}    {_curdir_path(target, suite_dir, is_dir)}"
        how = ("is found only via ./lib, ./resources, -P or PYTHONPATH (the helper and robotcode add them, a plain "
               "`robot` run does not)") if not looks_like_path else \
              "does not exist relative to this file (plain `robot` resolves it from the importing file's directory)"
        msg = f"{kind} '{name}' {how} -> use `{fix}`"
        if not looks_like_path and len(resolved.split(".")) > 1 and target.stem != resolved.split(".")[-1]:
            msg += " (a path import uses the class named like the module, else the module's functions)"
        out.append({"line": line, "code": "NotPortable", "msg": msg, "fix": fix})
    return out


def lines(path: Path, root: Optional[Path] = None) -> List[str]:
    return [f"L{i['line']} {i['msg']}" for i in issues(path, root)]


if __name__ == "__main__":
    for f in sys.argv[1:]:
        print(json.dumps(issues(Path(f)), indent=1))
