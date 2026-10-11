"""Generate signature-only stub libraries from libdoc JSON specs.

Idea under test: the client uploads `robotcode libdoc --format JSON <Lib>` once;
the REMOTE server (which does not have Browser/Playwright/Selenium installed)
generates import-safe stubs with identical keyword names + argument specs and can
then run `robotcode analyze code` / `robot --dryrun` itself.

Usage: python spec_to_stub.py <out_dir> <spec.json> [<spec.json> ...]
"""

from __future__ import annotations

import json
import keyword as pykw
import re
import sys
from pathlib import Path


def ident(name: str, used: set[str]) -> str:
    base = re.sub(r"\W+", "_", name.strip()).strip("_").lower() or "kw"
    if base[0].isdigit() or pykw.iskeyword(base):
        base = "kw_" + base
    out, i = base, 1
    while out in used:
        i += 1
        out = f"{base}_{i}"
    used.add(out)
    return out


def argname(n: str) -> str:
    n = re.sub(r"\W+", "_", n) or "arg"
    return n + "_" if pykw.iskeyword(n) else n


STD = {"str": "str", "int": "int", "float": "float", "bool": "bool", "None": "None",
       "timedelta": "timedelta", "Any": "Any", "list": "list", "dict": "dict"}
ENUMS: set[str] = set()


def annotation(t: dict | None) -> str | None:
    """Map a libdoc type dict to a Python annotation, or None when not safely representable."""
    if not t:
        return None
    if t.get("union"):
        parts = [annotation(n) for n in t.get("nested") or []]
        return None if not parts or any(p is None for p in parts) else " | ".join(parts)
    name = t.get("name")
    if name in STD:
        return STD[name]
    if name in ENUMS:
        return name
    return None


def signature(args: list[dict], with_self: bool = True) -> str:
    parts: list[str] = ["self"] if with_self else []
    pos_only, seen_star = [], False
    for a in args:
        kind, name = a["kind"], argname(a["name"])
        ann = annotation(a.get("type")) if TYPED else None
        if ann and kind in ("VAR_POSITIONAL", "VAR_NAMED"):
            ann = None
        if ann:
            name = f"{name}: {ann}"
        default = "" if a.get("required", True) else ("=None" if not ann else " = None")
        if kind == "POSITIONAL_ONLY":
            pos_only.append(f"{name}{default}")
            continue
        if pos_only:
            parts += pos_only + ["/"]
            pos_only = []
        if kind == "POSITIONAL_OR_NAMED":
            parts.append(f"{name}{default}")
        elif kind == "VAR_POSITIONAL":
            parts.append(f"*{name}")
            seen_star = True
        elif kind == "NAMED_ONLY":
            if not seen_star:
                parts.append("*")
                seen_star = True
            parts.append(f"{name}{default}")
        elif kind == "VAR_NAMED":
            parts.append(f"**{name}")
    if pos_only:
        parts += pos_only + ["/"]
    return ", ".join(parts)


def make_stub(spec: dict) -> str:
    lib = spec["name"]
    lines = [
        f'"""Signature-only stub for {lib} {spec.get("version")} (generated from libdoc JSON)."""',
        "from datetime import timedelta",
        "from enum import Enum",
        "from typing import Any",
        "from robot.api.deco import keyword, library",
        "",
    ]
    ENUMS.clear()
    if TYPED:
        for td in spec.get("typedocs") or []:
            if td.get("type") == "Enum" and re.fullmatch(r"[A-Za-z_]\w*", td["name"]):
                members = [(m["name"], m["value"]) for m in td.get("members") or []]
                lines.append(f"{td['name']} = Enum({td['name']!r}, {members!r})")
                ENUMS.add(td["name"])
    lines += [
        "",
        f"@library(scope={spec.get('scope', 'GLOBAL')!r}, version={spec.get('version')!r}, auto_keywords=False)",
        f"class {re.sub(r'\\W+', '_', lib.split('.')[-1])}:",
    ]
    inits = spec.get("inits") or []
    if inits:
        lines.append(f"    def __init__({signature(inits[0]['args'])}):")
        lines.append("        pass")
    used: set[str] = set()
    for kw in spec["keywords"]:
        fn = ident(kw["name"], used)
        doc = (kw.get("shortdoc") or "").replace('"""', "'''").replace("\\", "\\\\")
        lines.append("")
        lines.append(f"    @keyword({kw['name']!r}, tags={list(kw.get('tags') or [])!r})")
        lines.append(f"    def {fn}({signature(kw['args'])}):")
        lines.append(f'        """{doc}"""')
        lines.append("        raise NotImplementedError('stub: executes only on the client')")
    return "\n".join(lines) + "\n"


TYPED = "--typed" in sys.argv
if TYPED:
    sys.argv.remove("--typed")


def main() -> None:
    out = Path(sys.argv[1])
    out.mkdir(parents=True, exist_ok=True)
    for p in sys.argv[2:]:
        spec = json.loads(Path(p).read_text())
        mod = spec["name"].split(".")[0]
        src = make_stub(spec)
        (out / f"{mod}.py").write_text(src)
        print(f"{spec['name']:<18} {len(spec['keywords']):4d} kws -> {out / (mod + '.py')} ({len(src)} bytes)")


if __name__ == "__main__":
    main()
