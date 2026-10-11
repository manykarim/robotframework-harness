"""Documentation worker started detached by the hooks (runs in the project venv; uses `robotcode libdoc`).

  python -m rf_harness.runtime.docsgen kw  --target <Lib|path|path::args> --kw "<Keyword>" --dest FILE [--owner O] [--cache F]
      `robotcode libdoc <target> show "<Keyword>"` -> FILE (header: owner, signature line, source) [+ global cache copy]
  python -m rf_harness.runtime.docsgen lib --item "<name>\t<target>\t<lib|path>" ...
      `robotcode libdoc --specdocformat raw <target> <tmp>.json` -> .rf/docs/<name>.full.md (every keyword: signature +
      full doc) and, when missing, .rf/docs/<name>.md (one line per keyword); cached per library version in
      ~/.cache/rf-harness/docs/.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from . import robotcode_adapter
from .kwdoc import CACHE, lib_version, safe


def _sig_from_show(text: str) -> Optional[str]:
    """RF 7.3 text (`Arguments:  [a, b=1]`) or RF 7.4+ markdown (`#### Arguments` + `* `a` (type ...)`)."""
    lines = text.splitlines()
    name = lines[0].lstrip("# ").strip() if lines else ""
    m = re.search(r"^Arguments:\s+\[(.*?)\]\s*$", text, re.M | re.S)
    if m:
        args = re.sub(r"\s+", " ", m.group(1))
        args = re.sub(r":\s*[^,=\]]+(?=\s*(?:=|,|$))", "", args)       # drop type annotations
        args = re.sub(r"\s*=\s*", "=", args)
        return f"{name}({args.strip()})"
    m = re.search(r"#### Arguments\s*\n(.*?)(?:\n#### |\Z)", text, re.S)
    if m:
        args = []
        for a in re.findall(r"^\* `([^`]+)`(?:.*?default: `([^`]*)`)?", m.group(1), re.M):
            args.append(a[0] + (f"={a[1]}" if a[1] else ""))
        return f"{name}({', '.join(args)})"
    return f"{name}()" if name else None


def cmd_kw(opts: argparse.Namespace) -> int:
    dest = Path(opts.dest)
    t0 = time.time()
    r = robotcode_adapter.libdoc([opts.target, "show", opts.kw])
    body = (r.stdout or "").strip()
    if r.returncode != 0 or not body:
        err = (r.stderr or r.stdout or "").strip().splitlines()[-1:] or ["no output"]
        text = (f"# {opts.owner}.{opts.kw}\n\nno documentation: `robotcode libdoc {opts.target} show \"{opts.kw}\"` "
                f"failed: {err[0][:300]}\nSearch instead: grep -i '<words>' .rf/docs/*.md\n")
    else:
        sig = _sig_from_show(body) or opts.kw
        text = (f"# {opts.owner}.{opts.kw}\nsignature: {sig}\nsource: robotcode libdoc {opts.target} show "
                f"\"{opts.kw}\"  ({time.time() - t0:.1f}s)\n\n{body}\n")
    tmp = dest.with_suffix(".tmp%d" % os.getpid())
    tmp.write_text(text)
    os.replace(tmp, dest)
    if opts.cache and r.returncode == 0 and body:
        c = Path(opts.cache)
        c.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(dest, c)
    return 0


def _strip(s: str) -> str:
    s = re.sub(r"``(.+?)``", r"\1", s or "")
    s = re.sub(r"`(.+?)`", r"\1", s)
    return re.sub(r"\s+", " ", s).strip()


def _arg_repr(a: Dict[str, Any]) -> str:
    r = a.get("repr") or a.get("name") or ""
    r = re.sub(r":\s*[^=]+(?==)|:\s*[^=]+$", "", r).strip()
    return re.sub(r"\s*=\s*", "=", r)


def _write_lib(name: str, target: str, kind: str, docs: Path, root: Path) -> Optional[str]:
    full, comp = docs / f"{safe(name)}.full.md", docs / f"{safe(name)}.md"
    gkey = None
    if kind == "lib":
        gkey = CACHE / "docs" / f"{safe(name)}-{lib_version(name)}"     # (no with_suffix: versions contain dots)
        g_full, g_comp, g_spec = (Path(f"{gkey}.full.md"), Path(f"{gkey}.compact.md"), Path(f"{gkey}.spec.json"))
        if g_full.is_file() and g_spec.is_file():
            shutil.copyfile(g_full, full)
            if not comp.is_file() and g_comp.is_file():
                shutil.copyfile(g_comp, comp)
            return "cached"
    with tempfile.TemporaryDirectory(prefix="rfhdoc") as td:
        spec = Path(td) / "spec.json"
        r = robotcode_adapter.libdoc(["--specdocformat", "raw", target, str(spec)], timeout=120)
        if r.returncode != 0 or not spec.is_file():
            full.write_text(f"# {name}: documentation unavailable: {(r.stderr or r.stdout or '').strip()[-300:]}\n")
            return "error"
        d = json.loads(spec.read_text())
    kws = sorted(d.get("keywords") or [], key=lambda k: k["name"].lower())
    head = f"# {d.get('name') or name} {d.get('version') or ''} -- {len(kws)} keywords"
    if kind == "path":
        head += f" (import by path: {os.path.relpath(target, root)})"
    lines = [head + "  (full docs; one line per keyword: " + os.path.relpath(comp, root) + ")", ""]
    one = [f"# {d.get('name') or name} {d.get('version') or ''} -- {len(kws)} keywords, one per line: "
           "Keyword Name(arguments) -- short doc (full: " + os.path.relpath(full, root) + ")"]
    for k in kws:
        args = ", ".join(_arg_repr(a) for a in k.get("args") or [])
        lines += [f"## {k['name']}({args})", "", (k.get("doc") or "").strip(), ""]
        sd = _strip(k.get("shortdoc") or (k.get("doc") or "").split("\n\n")[0])[:170]
        one.append(f"{k['name']}({args})" + (f" -- {sd}" if sd else ""))
    full.write_text("\n".join(lines) + "\n")
    if not comp.is_file():
        comp.write_text("\n".join(one) + "\n")
    slim = {"name": d.get("name") or name, "version": d.get("version") or "", "keywords": {
        k["name"]: {"args": ", ".join(_arg_repr(a) for a in k.get("args") or []), "doc": (k.get("doc") or "").strip(),
                    "short": _strip(k.get("shortdoc") or (k.get("doc") or "").split("\n\n")[0])[:240]} for k in kws}}
    if gkey is not None:
        gkey.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(full, f"{gkey}.full.md")
        shutil.copyfile(comp, f"{gkey}.compact.md")
        Path(f"{gkey}.spec.json").write_text(json.dumps(slim))
    else:
        sd = docs / ".spec"
        sd.mkdir(parents=True, exist_ok=True)
        try:
            mt = int(os.stat(target).st_mtime)
        except OSError:
            mt = 0
        (sd / f"{safe(name)}-{mt}.json").write_text(json.dumps(slim))
    return "written"


def cmd_lib(opts: argparse.Namespace) -> int:
    root = Path.cwd()
    docs = root / ".rf" / "docs"
    docs.mkdir(parents=True, exist_ok=True)
    for item in opts.item or []:
        try:
            name, target, kind = item.split("\t")
        except ValueError:
            continue
        lock = docs / f".{safe(name)}.gen"
        try:
            if lock.exists() and time.time() - lock.stat().st_mtime < 120:
                continue
            lock.write_text(str(os.getpid()))
            _write_lib(name, target, kind, docs, root)
        except Exception as e:  # never crash silently without a trace
            print(f"{name}: {type(e).__name__}: {e}", file=sys.stderr)
        finally:
            try:
                lock.unlink()
            except OSError:
                pass
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(prog="rf_harness.runtime.docsgen")
    sub = ap.add_subparsers(dest="cmd", required=True)
    k = sub.add_parser("kw")
    k.add_argument("--target", required=True)
    k.add_argument("--kw", required=True)
    k.add_argument("--dest", required=True)
    k.add_argument("--owner", default="")
    k.add_argument("--cache")
    lb = sub.add_parser("lib")
    lb.add_argument("--item", action="append")
    opts = ap.parse_args(argv)
    return cmd_kw(opts) if opts.cmd == "kw" else cmd_lib(opts)


if __name__ == "__main__":
    sys.exit(main())
