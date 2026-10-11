"""E3 probe (runs in a FRESH process per call): time keyword-doc retrieval via
  rf   = robot.libdocpkg.LibraryDocumentation(name)
  rc   = robotcode.robot.diagnostics.library_doc.get_library_doc(name)
  rcpk = load pickled robotcode LibraryDoc from a local file cache (written on first use)
  rfjs = LibraryDocumentation(<local libdoc JSON spec>)  (spec generated + kept locally)
  rcdb = read LibraryDoc from robotcode's analyze cache (.robotcode_cache sqlite) via SqliteDataCache
Prints one JSON line."""
import json, sys, time, pickle, os
from pathlib import Path

t_proc = time.perf_counter()
mode, lib = sys.argv[1], sys.argv[2]
cache_dir = Path(sys.argv[3]) if len(sys.argv) > 3 else Path("/tmp")
kw_probe = {"Browser": "Fill Text", "SeleniumLibrary": "Input Text", "RequestsLibrary": "POST On Session",
            "BuiltIn": "Should Be Equal", "Collections": "Append To List", "String": "Split String"}.get(lib, None)
res = {"mode": mode, "lib": lib}
t0 = time.perf_counter()
if mode == "rf":
    from robot.libdocpkg import LibraryDocumentation
    t_imp = time.perf_counter()
    d = LibraryDocumentation(lib)
    t1 = time.perf_counter()
    kws = d.keywords
    kw = next((k for k in kws if k.name == kw_probe), None)
    res.update(n=len(kws), import_s=round(t_imp - t0, 3), build_s=round(t1 - t_imp, 3),
               sample={"name": kw.name, "args": [str(a) for a in kw.args], "tags": list(kw.tags),
                       "doc_len": len(kw.doc), "doc_first": kw.doc.split("\n\n")[0][:160]} if kw else None)
    # second build in same process (warm module import)
    t2 = time.perf_counter(); LibraryDocumentation(lib); res["warm_rebuild_s"] = round(time.perf_counter() - t2, 3)
elif mode == "rc":
    from robotcode.robot.diagnostics.library_doc import get_library_doc
    t_imp = time.perf_counter()
    d = get_library_doc(lib)
    t1 = time.perf_counter()
    kw = next(iter(d.keywords.get_all(kw_probe)), None) if kw_probe else None
    res.update(n=len(d.keywords), errors=[str(e.message)[:120] for e in (d.errors or [])][:2],
               import_s=round(t_imp - t0, 3), build_s=round(t1 - t_imp, 3),
               sample={"name": kw.name, "signature": kw.signature if hasattr(kw, "signature") else None,
                       "args": [(a.name, a.kind.name, a.types, a.default_value) for a in kw.arguments],
                       "tags": list(kw.tags), "return_type": kw.return_type, "doc_format": kw.doc_format,
                       "md_len": len(kw.to_markdown())} if kw else None)
    t2 = time.perf_counter(); p = pickle.dumps(d); res["pickle_bytes"] = len(p); res["pickle_dump_s"] = round(time.perf_counter() - t2, 3)
    (cache_dir / f"{lib}.rc.pkl").write_bytes(p)
elif mode == "rcpk":
    import robotcode.robot.diagnostics.library_doc  # noqa: F401  (class defs for unpickle)
    t_imp = time.perf_counter()
    d = pickle.loads((cache_dir / f"{lib}.rc.pkl").read_bytes())
    t1 = time.perf_counter()
    kw = next(iter(d.keywords.get_all(kw_probe)), None) if kw_probe else None
    md = kw.to_markdown() if kw else ""
    res.update(n=len(d.keywords), import_s=round(t_imp - t0, 3), build_s=round(t1 - t_imp, 3), md_len=len(md),
               md_s=round(time.perf_counter() - t1, 4))
elif mode == "rfjs":
    from robot.libdocpkg import LibraryDocumentation
    spec = cache_dir / f"{lib}.raw.json"
    if not spec.exists():
        LibraryDocumentation(lib).save(str(spec), "JSON")  # RAW doc format by default from save()
    t_imp = time.perf_counter()
    d = LibraryDocumentation(str(spec))
    t1 = time.perf_counter()
    res.update(n=len(d.keywords), import_s=round(t_imp - t0, 3), build_s=round(t1 - t_imp, 3), spec_bytes=spec.stat().st_size)
elif mode == "rcdb":
    from robotcode.robot.diagnostics.data_cache import SqliteDataCache, CacheSection, build_cache_dir
    from robotcode.robot.diagnostics.imports_manager import LibraryMetaData
    from robotcode.robot.diagnostics.library_doc import LibraryDoc
    from robotcode.robot.__version__ import __version__ as rcv
    t_imp = time.perf_counter()
    c = SqliteDataCache(build_cache_dir(cache_dir), app_version=rcv)
    entries = c.list_entries(CacheSection.LIBRARY)
    hit = [e for e in entries if lib.lower() in e.entry_name.lower()]
    res["entries"] = [e.entry_name for e in entries][:12]
    d = None
    if hit:
        ent = c.read_entry(CacheSection.LIBRARY, hit[0].entry_name, LibraryMetaData, LibraryDoc)
        d = ent.data
    t1 = time.perf_counter()
    res.update(n=len(d.keywords) if d else 0, import_s=round(t_imp - t0, 3), build_s=round(t1 - t_imp, 3))
res["total_in_proc_s"] = round(time.perf_counter() - t_proc, 3)
print(json.dumps(res, default=str))
