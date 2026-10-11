"""Round-5 prototype: per-library keyword cache for hooks (in-process libdoc, no robotcode start-up per lookup).

  python kwcache.py build  <lib-spec>...        # Browser | SeleniumLibrary | path/x.resource | Lib.py::arg
  python kwcache.py lookup <lib-spec> "<kw>"    # exact (normalized) or fuzzy suggestions + one-line signature
  python kwcache.py bench                       # timings -> kwcache_bench.json

Cache: $RFH_CACHE (default ~/.cache/rfharness-r5)/<slug>-<key>.json
  key = library: dist version (importlib.metadata) + init args;  resource/py file: path + mtime_ns + size
Each JSON: {lib, version, source, keywords: {normname: {name, sig, short, args, tags, returns, lineno}}}
Per-keyword markdown file written on demand to .rf/docs/kw/<Lib>/<Keyword>.md (what the agent Reads).
"""
from __future__ import annotations

import difflib
import hashlib
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

CACHE = Path(os.environ.get("RFH_CACHE", Path.home() / ".cache" / "rfharness-r5"))
DIST = {"Browser": "robotframework-browser", "SeleniumLibrary": "robotframework-seleniumlibrary",
        "RequestsLibrary": "robotframework-requests"}


def norm(s: str) -> str:
    return re.sub(r"[\s_]", "", s).lower()


def cache_key(spec: str) -> str:
    name, *args = spec.split("::")
    p = Path(name)
    if p.suffix in (".resource", ".robot", ".py", ".txt") and p.exists():
        st = p.stat()
        raw = f"{p.resolve()}|{st.st_mtime_ns}|{st.st_size}|{args}"
    else:
        from importlib.metadata import version, PackageNotFoundError
        try:
            v = version(DIST.get(name, name))
        except (PackageNotFoundError, ValueError):
            v = "rf-" + version("robotframework")  # stdlib libraries follow RF's version (no `import robot`)
        raw = f"{name}|{v}|{args}"
    return hashlib.sha1(raw.encode()).hexdigest()[:12]


def _slug(spec: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "_", Path(spec.split("::")[0]).name)[:40]


def signature(kw: Any) -> str:
    args = ", ".join(str(a) for a in kw.args)
    ret = f" -> {kw.args.return_type}" if getattr(kw.args, "return_type", None) else ""
    return f"{kw.name}({args}){ret}"


def sig_short(kw: Any) -> str:
    """names + defaults only (types live in the per-keyword file)."""
    parts = []
    for a in kw.args:
        t = str(a)
        if t in ("*", "/"):
            parts.append(t)
            continue
        name = re.split(r"[:=]", t, maxsplit=1)[0].strip()
        if " = " in t:
            name += "=" + t.rsplit(" = ", 1)[1]
        elif "=" in t and ":" not in t.split("=", 1)[0]:
            name += "=" + t.split("=", 1)[1]
        parts.append(name)
    return f"{kw.name}({', '.join(parts)})"


_MEM: Dict[str, Dict[str, Any]] = {}


def build(spec: str) -> Dict[str, Any]:
    if spec in _MEM:
        return _MEM[spec]
    _MEM[spec] = data = _build(spec)
    return data


def _build(spec: str) -> Dict[str, Any]:
    path = CACHE / f"{_slug(spec)}-{cache_key(spec)}.json"
    if path.exists():
        return json.loads(path.read_text())
    from robot.libdocpkg import LibraryDocumentation
    d = LibraryDocumentation(spec)
    data = {"lib": d.name, "version": d.version, "source": str(d.source or ""), "spec": spec,
            "keywords": {}}
    for kw in d.keywords:
        data["keywords"][norm(kw.name)] = {
            "name": kw.name, "sig": signature(kw), "sig_short": sig_short(kw), "short": kw.short_doc[:240], "doc": kw.doc,
            "args": [str(a) for a in kw.args], "tags": list(kw.tags), "lineno": kw.lineno,
        }
    CACHE.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data))
    return data


def lookup(data: Dict[str, Any], name: str, n: int = 3) -> Dict[str, Any]:
    kws = data["keywords"]
    k = norm(name.split(".")[-1])
    if k in kws:
        return {"exact": kws[k]}
    # fuzzy: difflib on normalized names + token containment
    close = difflib.get_close_matches(k, list(kws), n=n, cutoff=0.6)
    toks = [t for t in re.split(r"\s+", name.lower()) if len(t) > 2]
    contain = [kk for kk, v in kws.items() if toks and all(t in v["name"].lower() for t in toks)]
    sugg = list(dict.fromkeys(close + contain))[:n]
    return {"suggestions": [kws[s] for s in sugg]}


def write_kw_md(data: Dict[str, Any], kw: Dict[str, Any], root: Path = Path(".rf/docs/kw")) -> Path:
    p = root / re.sub(r"[^A-Za-z0-9]+", "_", data["lib"]) / (re.sub(r"[^A-Za-z0-9]+", "_", kw["name"]) + ".md")
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(f"# {data['lib']}.{kw['name']}  ({data['lib']} {data['version']})\n\n`{kw['sig']}`\n\n"
                 f"tags: {', '.join(kw['tags'])}\n\n{kw['doc']}\n")
    return p


def inline_line(data: Dict[str, Any], kw: Dict[str, Any], path: Optional[Path] = None) -> str:
    first = re.split(r"(?<=[.!?])\s", kw["short"].replace("``", "`"), maxsplit=1)[0]
    return f"{data['lib']}.{kw['sig']}\n  {first}" + (f"\n  full doc: {path}" if path else "")


def write_lib_md(data: Dict[str, Any], root: Path = Path(".rf/docs")) -> Path:
    """one grep-able line per keyword: `Sig(short) -- first sentence`."""
    p = root / (re.sub(r"[^A-Za-z0-9]+", "_", data["lib"]) + ".md")
    p.parent.mkdir(parents=True, exist_ok=True)
    lines = [f"# {data['lib']} {data['version']} ({len(data['keywords'])} keywords) -- per-keyword docs: "
             f".rf/docs/kw/{data['lib']}/<Keyword>.md or `robotcode libdoc {data['spec']} show \"<Keyword>\"`"]
    for kw in sorted(data["keywords"].values(), key=lambda k: k["name"]):
        first = re.split(r"(?<=[.!?])\s", kw["short"].replace("``", "`"), maxsplit=1)[0]
        lines.append(f"{kw['sig_short']} -- {first}")
    p.write_text("\n".join(lines) + "\n")
    return p


def bench() -> None:
    import statistics
    out: List[Dict[str, Any]] = []
    specs = ["Browser", "RequestsLibrary", "BuiltIn", "Collections", "resources/shop.resource",
             "libs/ArgLib.py::advanced"]
    try:
        import SeleniumLibrary  # noqa: F401
        specs.insert(1, "SeleniumLibrary")
    except ImportError:
        pass
    for spec in specs:
        # cold build (no cache), then warm load
        p = CACHE / f"{_slug(spec)}-{cache_key(spec)}.json"
        if p.exists():
            p.unlink()
        t0 = time.perf_counter(); data = build(spec); cold = (time.perf_counter() - t0) * 1000
        warm = []
        for _ in range(5):
            t0 = time.perf_counter(); data = build(spec); warm.append((time.perf_counter() - t0) * 1000)
        names = list(data["keywords"].values())[:20]
        lk = []
        for kw in names:
            t0 = time.perf_counter(); lookup(data, kw["name"]); lk.append((time.perf_counter() - t0) * 1000)
        fz = []
        for kw in names:
            typo = kw["name"][:-1] if len(kw["name"]) > 4 else kw["name"] + "x"
            t0 = time.perf_counter(); r = lookup(data, typo); fz.append((time.perf_counter() - t0) * 1000)
        t0 = time.perf_counter(); ck = cache_key(spec); key_ms = (time.perf_counter() - t0) * 1000
        out.append({"spec": spec, "keywords": len(data["keywords"]), "cache_bytes": p.stat().st_size,
                    "cold_build_ms": round(cold), "warm_load_ms": round(statistics.median(warm), 1),
                    "exact_lookup_ms": round(statistics.median(lk), 3), "fuzzy_lookup_ms": round(statistics.median(fz), 2),
                    "cache_key_ms": round(key_ms, 2)})
        print(out[-1], flush=True)
    Path("kwcache_bench.json").write_text(json.dumps(out, indent=1))


def main(argv: List[str]) -> int:
    if not argv or argv[0] == "bench":
        bench()
        return 0
    if argv[0] == "build":
        for s in argv[1:]:
            d = build(s)
            print(f"{s}: {len(d['keywords'])} keywords, {d['lib']} {d['version']}")
        return 0
    if argv[0] == "libmd":
        for spec in argv[1:]:
            t0 = time.perf_counter(); d = build(spec); p = write_lib_md(d)
            print(f"{spec}: {p} {p.stat().st_size} B {round((time.perf_counter() - t0) * 1000, 1)} ms")
        return 0
    if argv[0] == "lookup":
        d = build(argv[1])
        r = lookup(d, argv[2])
        if "exact" in r:
            p = write_kw_md(d, r["exact"])
            print(inline_line(d, r["exact"], p))
        else:
            print(f"No keyword '{argv[2]}' in {d['lib']}. Did you mean:")
            for kw in r["suggestions"]:
                print("  " + inline_line(d, kw).replace("\n", "\n  "))
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
