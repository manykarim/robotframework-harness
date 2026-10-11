"""Write compact keyword docs for grep: .rf/docs/<Library>.md (one line per keyword: signature -- short doc).

  python -m rfharness32.docs ROOT        (spawned detached by the SessionStart hook; exits when done)
Libraries: Browser, SeleniumLibrary, RequestsLibrary, BuiltIn, Collections, String, DateTime, OperatingSystem
(when installed) + libraries named in the project's files + project resources / path-imported Python libraries
(.rf/docs/project.md). Library files are cached per version in ~/.cache/rfharness32/docs/.
`*args, **kwargs` decorator signatures (RequestsLibrary) are repaired to the real parameters.
"""
from __future__ import annotations

import contextlib
import io
import os
import re
import sys
import time
from pathlib import Path
from typing import Any, List, Optional

LIBS = ["Browser", "SeleniumLibrary", "RequestsLibrary", "BuiltIn", "Collections", "String", "DateTime",
        "OperatingSystem"]
STD = {"BuiltIn", "Collections", "String", "DateTime", "OperatingSystem", "Process", "XML", "Screenshot", "Telnet",
       "Dialogs"}
HEADERS = {
    "Browser": ("Browser (Playwright). iframe: `id=frame >>> id=field` (no select-frame keyword); css/id/text pierce "
                "open shadow DOM, xpath does not; strict mode: >1 match fails (`>> nth=0`); getters with an "
                "operator (`Get Text    sel    ==    x`) retry only ~1 s -> async UI: Wait For Condition / "
                "Wait For Elements State."),
    "RequestsLibrary": ("RequestsLibrary: Create Session    alias    http://host ; ${r}=    GET On Session    alias    /path ; "
                        "json=${body} for JSON bodies; expected_status=404 to capture non-2xx; Status Should Be    200    ${r}; "
                        "${r.json()}[key] outside Evaluate."),
    "SeleniumLibrary": "SeleniumLibrary: locators id:x name:x css:x xpath:x link:Text; frames: Select Frame / Unselect Frame.",
}


def _version(name: str) -> str:
    if name in STD:
        import robot

        return "rf" + robot.__version__
    try:
        import importlib.metadata as md

        dist = {"Browser": "robotframework-browser", "SeleniumLibrary": "robotframework-seleniumlibrary",
                "RequestsLibrary": "robotframework-requests"}.get(name, name)
        return md.version(dist)
    except Exception:
        try:
            mod = __import__(name)
            return str(getattr(mod, "__version__", "0"))
        except Exception:
            return "0"


def _installed(name: str) -> bool:
    if name in STD:
        return True
    import importlib.util

    try:
        return importlib.util.find_spec(name.split(".")[0]) is not None
    except (ImportError, ValueError):
        return False


def lib_lines(name_or_path: str, owner: str) -> List[str]:
    from robot.libdocpkg import LibraryDocumentation
    from robot.utils import getshortdoc

    from .kwdocs import _strip, signature

    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        d = LibraryDocumentation(name_or_path)
    out = []
    for kw in sorted(d.keywords, key=lambda k: k.name.lower()):
        doc = _strip(getshortdoc(kw.doc or ""))[:170]
        sig = signature(kw, owner)
        out.append(f"{sig} -- {doc}" if doc else sig)
    return out


def write_lib(name: str, outdir: Path, cache: Path) -> Optional[Path]:
    if not _installed(name):
        return None
    ver = _version(name)
    cached = cache / f"{name}-{ver}.md"
    dest = outdir / f"{name}.md"
    if cached.is_file():
        dest.write_text(cached.read_text())
        return dest
    try:
        lines = lib_lines(name, name)
    except Exception as e:
        dest.write_text(f"# {name}: documentation unavailable ({type(e).__name__}: {str(e)[:200]})\n")
        return dest
    head = [f"# {name} {ver} -- {len(lines)} keywords, one per line: Keyword Name(arguments) -- short doc",
            f"# import: Library    {name}"]
    if name in HEADERS:
        head.append("# " + HEADERS[name])
    text = "\n".join(head + lines) + "\n"
    cache.mkdir(parents=True, exist_ok=True)
    cached.write_text(text)
    dest.write_text(text)
    return dest


def workspace_libs(root: Path) -> List[str]:
    names: List[str] = []
    for dp, dns, fns in os.walk(root):
        dns[:] = [d for d in dns if not d.startswith(".") and d not in ("node_modules", "results", "venv")]
        for fn in fns:
            if fn.endswith((".robot", ".resource")):
                with contextlib.suppress(OSError):
                    for line in open(os.path.join(dp, fn), errors="replace"):
                        m = re.match(r"^Library\s{2,}([\w.]+)\s*(?:$|\s{2})", line)
                        if m and not m.group(1).endswith(".py") and m.group(1) not in names:
                            names.append(m.group(1))
    return names


def project_doc(root: Path, outdir: Path) -> Optional[Path]:
    """keywords of project .resource files and path-imported python libraries."""
    blocks: List[str] = []
    seen = set()
    for dp, dns, fns in os.walk(root):
        dns[:] = [d for d in dns if not d.startswith(".") and d not in ("node_modules", "results", "venv", "output")]
        for fn in sorted(fns):
            p = Path(dp) / fn
            targets = []
            if fn.endswith(".resource") and not fn.startswith("."):
                targets.append(p)
            elif fn.endswith(".robot") and not fn.startswith("."):
                with contextlib.suppress(OSError):
                    for line in p.read_text(errors="replace").splitlines():
                        m = re.match(r"^Library\s{2,}(\S+\.py)\b", line)
                        if m:
                            lp = m.group(1).replace("${CURDIR}", str(p.parent)).replace("${EXECDIR}", str(root))
                            lp = Path(lp) if os.path.isabs(lp) else p.parent / lp
                            if lp.is_file():
                                targets.append(lp.resolve())
            for t in targets:
                if t in seen:
                    continue
                seen.add(t)
                try:
                    lines = lib_lines(str(t), t.stem)
                except Exception as e:
                    lines = [f"(not documented: {type(e).__name__}: {str(e)[:120]})"]
                blocks.append(f"\n## {os.path.relpath(t, root)}  ({len(lines)} keywords)\n" + "\n".join(lines))
    for d in ("lib", "libs", "resources", "libraries"):
        for py in sorted((root / d).glob("*.py")) if (root / d).is_dir() else []:
            if py.resolve() in seen or py.name.startswith("_"):
                continue
            seen.add(py.resolve())
            with contextlib.suppress(Exception):
                lines = lib_lines(str(py), py.stem)
                blocks.append(f"\n## {os.path.relpath(py, root)}  ({len(lines)} keywords; import BY PATH: "
                              f"Library    ${{CURDIR}}/<relative path to {py.name}>)\n" + "\n".join(lines))
    if not blocks:
        return None
    dest = outdir / "project.md"
    dest.write_text("# project keywords (resources / python libraries in this workspace)\n" + "".join(blocks) + "\n")
    return dest


def main(argv: Optional[List[str]] = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    root = Path(argv[0] if argv else os.getcwd()).resolve()
    outdir = root / ".rf" / "docs"
    outdir.mkdir(parents=True, exist_ok=True)
    cache = Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache") / "rfharness32" / "docs"
    t0 = time.time()
    done = []
    names = list(dict.fromkeys(LIBS + workspace_libs(root)))
    for n in names:
        with contextlib.suppress(Exception):
            if write_lib(n, outdir, cache):
                done.append(n)
    with contextlib.suppress(Exception):
        if project_doc(root, outdir):
            done.append("project")
    (outdir / "README.txt").write_text(
        "One line per keyword: `Keyword Name(arguments) -- short doc`. Search: grep -i 'select option' .rf/docs/*.md\n"
        f"Files: {', '.join(n + '.md' for n in done)}\n")
    (outdir / ".complete").write_text(f"{time.time() - t0:.1f}s\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
