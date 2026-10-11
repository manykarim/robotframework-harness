"""Keyword / library documentation files for the hooks (STDLIB ONLY: imported by hook.py).

  failed keyword  -> .rf/docs/kw/<Owner>.<Keyword>.md  via `robotcode libdoc <Lib|resource path|path::args> show "<Kw>"`
                     (detached worker `python -m rfharness32.docsgen kw ...`; cached per library version in
                     ~/.cache/rfharness32/kw/<Lib>-<version>/, per resource mtime in .rf/docs/kw/.meta.json)
  imported lib/res -> .rf/docs/<Name>.md (one line per keyword) + .rf/docs/<Name>.full.md (all keywords, full doc)
                     via `robotcode libdoc --specdocformat raw <target> <spec>.json` (worker `docsgen lib ...`)
The hook never blocks long: it starts the worker, waits up to RFH32_DOC_WAIT seconds (default 1.2) and reports the
path either way; the one-line signature comes from the compact docs (.rf/docs/<Owner>.md) when the file is late.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

PKG_ROOT = Path(__file__).resolve().parent.parent
CACHE = Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache") / "rfharness32"
STD = {"BuiltIn", "Collections", "String", "DateTime", "OperatingSystem", "Process", "XML", "Screenshot", "Telnet",
       "Dialogs"}
DIST = {"Browser": "robotframework_browser", "SeleniumLibrary": "robotframework_seleniumlibrary",
        "RequestsLibrary": "robotframework_requests"}


def _env_f(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, default))
    except ValueError:
        return default


DOC_WAIT = _env_f("RFH32_DOC_WAIT", 1.2)


def safe(name: str) -> str:
    return re.sub(r"[^\w.-]+", "_", name.strip()).strip("_") or "x"


def _python() -> str:
    return os.environ.get("RFH32_PYTHON") or sys.executable


def lib_version(name: str) -> str:
    """version of an installed library without importing it (dist-info dir names of the hook's venv)."""
    venv = Path(_python()).parent.parent
    if name in STD:
        key = "robotframework"
    else:
        key = DIST.get(name, name).lower().replace("-", "_")
    for sp in venv.glob("lib/python3*/site-packages"):
        for d in sp.glob("*.dist-info"):
            n, _, v = d.name[:-len(".dist-info")].rpartition("-")
            if n.lower().replace("-", "_") == key:
                return v
    return "0"


def target_of(owner: str, source: Optional[str], root: Path) -> Tuple[str, str]:
    """-> (libdoc target, cache key). Library by name (std/installed), resource/py file by path."""
    if source and (source.endswith((".resource", ".robot", ".py")) and os.path.isfile(source)):
        try:
            mt = int(os.stat(source).st_mtime)
        except OSError:
            mt = 0
        return source, f"path:{source}:{mt}"
    return owner, f"lib:{owner}-{lib_version(owner)}"


def _spawn(args: List[str], root: Path, log: Path) -> Optional[subprocess.Popen]:
    env = dict(os.environ)
    env["PYTHONPATH"] = str(PKG_ROOT) + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    env.pop("PYTHONSTARTUP", None)
    log.parent.mkdir(parents=True, exist_ok=True)
    try:
        with open(log, "ab") as lf:
            return subprocess.Popen([_python(), "-m", "rfharness32.docsgen", *args], cwd=str(root), env=env,
                                    stdin=subprocess.DEVNULL, stdout=lf, stderr=subprocess.STDOUT,
                                    start_new_session=True)
    except OSError:
        return None


def compact_signature(docs_dir: Path, owner: str, kw: str) -> Optional[str]:
    """`Keyword Name(args)` line from .rf/docs/<owner>.md (repaired signatures) or project.md."""
    norm = re.sub(r"[\s_]", "", kw).lower()
    for f in [docs_dir / f"{owner}.md", docs_dir / f"{safe(owner)}.md", docs_dir / "project.md"]:
        try:
            for line in f.read_text(errors="replace").splitlines():
                m = re.match(r"^([^#(][^(]*)\((.*?)\)(?: -- |$)", line)
                if m and re.sub(r"[\s_]", "", m.group(1)).lower() == norm:
                    return f"{m.group(1)}({m.group(2)})"
        except OSError:
            continue
    return None


def file_signature(path: Path) -> Optional[str]:
    try:
        text = path.read_text(errors="replace")
    except OSError:
        return None
    m = re.search(r"^signature: (.+)$", text, re.M)
    return m.group(1).strip() if m else None


def _spec(root: Path, owner: str, source: Optional[str]) -> Optional[Dict[str, Any]]:
    """slim libdoc JSON spec written by docsgen (global cache per library version / per resource mtime)."""
    try:
        if source and os.path.isfile(source):
            mt = int(os.stat(source).st_mtime)
            p = root / ".rf" / "docs" / ".spec" / f"{safe(Path(source).stem)}-{mt}.json"
        else:
            p = CACHE / "docs" / f"{safe(owner)}-{lib_version(owner)}.spec.json"
        return json.loads(p.read_text())
    except (OSError, ValueError):
        return None


def _match(spec: Dict[str, Any], kw: str) -> Optional[Tuple[str, Dict[str, Any]]]:
    norm = re.sub(r"[\s_]", "", kw).lower()
    for name, e in (spec.get("keywords") or {}).items():
        if re.sub(r"[\s_]", "", name).lower() == norm:
            return name, e
    return None


def near_names(root: Path, name: str, n: int = 3) -> List[str]:
    """closest keyword names (compact docs of the session) for an unknown keyword."""
    import difflib

    names: Dict[str, str] = {}
    for f in (root / ".rf" / "docs").glob("*.md"):
        if f.name.endswith(".full.md"):
            continue
        try:
            for line in f.read_text(errors="replace").splitlines():
                m = re.match(r"^([A-Z][^(#]*)\((.*?)\)", line)
                if m:
                    names.setdefault(m.group(1).strip().lower(), f"{m.group(1).strip()}({m.group(2)[:60]}) [{f.stem}]")
        except OSError:
            pass
    hits = difflib.get_close_matches(name.strip().lower(), list(names), n=n, cutoff=0.6)
    return [names[h] for h in hits]


def kw_doc(root: Path, owner: str, kw: str, source: Optional[str] = None, wait: float = DOC_WAIT
           ) -> Dict[str, Any]:
    """ensure .rf/docs/kw/<Owner>.<Keyword>.md exists (or is being written) -> {path, signature, ready, cached}"""
    docs = root / ".rf" / "docs"
    kwdir = docs / "kw"
    kwdir.mkdir(parents=True, exist_ok=True)
    owner_name = owner or "BuiltIn"
    if source and owner_name.startswith(".") and owner_name.endswith(".live"):   # live resource of a test file
        owner_name = owner_name[1:-5]
    dest = kwdir / f"{safe(owner_name)}.{safe(kw)}.md"
    target, key = target_of(owner_name, source, root)
    res: Dict[str, Any] = {"path": os.path.relpath(dest, root), "owner": owner_name, "kw": kw}
    meta_p = kwdir / ".meta.json"
    try:
        meta = json.loads(meta_p.read_text())
    except (OSError, ValueError):
        meta = {}
    sp = None if (dest.is_file() and meta.get(dest.name) == key) else _spec(root, owner_name, source)
    hit = _match(sp, kw) if sp else None
    if dest.is_file() and meta.get(dest.name) == key:
        res.update(ready=True, cached=True)
    elif hit is not None:                      # fast path: cached robotcode libdoc spec (~ms)
        name, e = hit
        sig = f"{name}({e.get('args', '')})"
        dest.write_text(f"# {owner_name}.{name}\nsignature: {sig}\nsource: robotcode libdoc {target} (cached spec, "
                        f"{sp.get('version', '')})\n\n{e.get('doc', '')}\n")
        res.update(ready=True, cached=True, spec=True)
        meta[dest.name] = key
        try:
            meta_p.write_text(json.dumps(meta))
        except OSError:
            pass
    else:
        gcache = None
        if key.startswith("lib:"):
            gcache = CACHE / "kw" / safe(key[4:]) / f"{safe(kw)}.md"
            if gcache.is_file():
                dest.write_text(gcache.read_text(errors="replace"))
                res.update(ready=True, cached=True)
        if not res.get("ready"):
            p = _spawn(["kw", "--target", target, "--kw", kw, "--dest", str(dest), "--owner", owner_name,
                        *(["--cache", str(gcache)] if gcache else [])], root, kwdir / ".log")
            t_end = time.monotonic() + max(0.0, wait)
            while p is not None and time.monotonic() < t_end and p.poll() is None:
                time.sleep(0.05)
            res["ready"] = dest.is_file() and (p is None or p.poll() is not None)
        meta[dest.name] = key
        try:
            meta_p.write_text(json.dumps(meta))
        except OSError:
            pass
    sig = (file_signature(dest) if res.get("ready") else None) or compact_signature(docs, owner_name, kw)
    if sig:
        res["signature"] = sig
    if hit is not None and hit[1].get("short"):
        res["first"] = hit[1]["short"].split(". ")[0][:160]
    return res


def kw_signature(root: Path, owner: str, kw: str, source: Optional[str] = None) -> Dict[str, Any]:
    """v3 (round-6: kw-doc files were read 0.1x/session): NO file is written here -- one-line signature from the cached
    libdoc spec / compact docs + the path where the full doc is generated ON DEMAND (PreToolUse of a Read/cat of it)."""
    docs = root / ".rf" / "docs"
    owner_name = owner or "BuiltIn"
    if source and owner_name.startswith(".") and owner_name.endswith(".live"):
        owner_name = owner_name[1:-5]
    dest = docs / "kw" / f"{safe(owner_name)}.{safe(kw)}.md"
    res: Dict[str, Any] = {"path": os.path.relpath(dest, root), "owner": owner_name, "kw": kw, "ready": dest.is_file(),
                           "on_demand": True}
    sp = _spec(root, owner_name, source)
    hit = _match(sp, kw) if sp else None
    if hit is not None:
        res["signature"] = f"{hit[0]}({hit[1].get('args', '')})"
        if hit[1].get("short"):
            res["first"] = hit[1]["short"].split(". ")[0][:160]
    else:
        sig = compact_signature(docs, owner_name, kw)
        if sig:
            res["signature"] = sig
    return res


ON_DEMAND = re.compile(r"\.rf/docs/kw/([^/\s'\"]+)\.md")


def on_demand(root: Path, text: str, wait: float = DOC_WAIT) -> List[str]:
    """PreToolUse of a Read / cat / grep / head that names .rf/docs/kw/<Owner>.<Keyword>.md: generate the file(s)
    first (cached spec ~ms, else robotcode libdoc <= wait s). -> paths written."""
    out = []
    for m in ON_DEMAND.finditer(text or ""):
        stem = m.group(1)
        if "." not in stem or (root / ".rf" / "docs" / "kw" / f"{stem}.md").is_file():
            continue
        owner, kw = stem.split(".", 1)
        src = None
        for f in list(root.glob(f"**/{owner}.resource"))[:1] + list(root.glob(f"**/{owner}.py"))[:1]:
            if ".rf" not in f.parts and ".venv" not in f.parts:
                src = str(f)
                break
        try:
            r = kw_doc(root, owner, kw.replace("_", " "), src, wait=wait)
            out.append(r["path"])
        except Exception:
            continue
    return out


def lib_docs(root: Path, items: List[Tuple[str, str]], cwd: Optional[Path] = None) -> List[Dict[str, Any]]:
    """imports [(kind, target)] -> start background doc generation for the ones without .rf/docs/<Name>.md.
    -> [{name, path, full, new}] (new = generation started now)."""
    docs = root / ".rf" / "docs"
    docs.mkdir(parents=True, exist_ok=True)
    out = []
    todo = []
    for kind, target in items:
        t = target.replace("${CURDIR}", str(cwd or root)).replace("${EXECDIR}", str(root))
        if "${" in t:
            continue
        is_path = "/" in t or t.endswith((".py", ".resource", ".robot"))
        if is_path:
            p = Path(t) if os.path.isabs(t) else (cwd or root) / t
            if not p.is_file():
                continue
            t = str(p.resolve())
            name = p.stem
        else:
            name = t
        comp, full = docs / f"{safe(name)}.md", docs / f"{safe(name)}.full.md"
        rec = {"name": name, "path": os.path.relpath(comp, root), "full": os.path.relpath(full, root)}
        if comp.is_file() and full.is_file():
            rec["new"] = False
        else:
            rec["new"] = True
            todo.append((name, t, "path" if is_path else "lib"))
        out.append(rec)
    if todo:
        args = ["lib"]
        for name, t, k in todo:
            args += ["--item", f"{name}\t{t}\t{k}"]
        _spawn(args, root, docs / ".log")
    return out
