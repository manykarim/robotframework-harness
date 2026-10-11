"""E3b: robotcode Python API on project sources: python library by path with init args, resource file (get_model_doc),
plus RF LibraryDocumentation on the same. Prints compact results + timings."""
import time, json
from pathlib import Path
P = Path("~/workspace/rf-mcp-robotcode/experiments/robotcode-remote/round2/keyword_docs/project")
out = {}
t = time.perf_counter()
from robotcode.robot.diagnostics.library_doc import get_library_doc, get_model_doc
from robot.api import get_resource_model
from robot.libdocpkg import LibraryDocumentation
out["import_s"] = round(time.perf_counter() - t, 3)

t = time.perf_counter()
d = get_library_doc(str(P / "libs/ShopApi.py"), args=("http://x",), working_dir=str(P), base_dir=str(P))
out["rc_pylib"] = {"s": round(time.perf_counter() - t, 3), "n": len(d.keywords), "kws": [k.name for k in d.keywords.values()],
                   "inits": [str(i.signature) for i in d.inits.values()] if d.inits else None, "errors": [e.message for e in d.errors or []]}
t = time.perf_counter()
d0 = get_library_doc(str(P / "libs/ShopApi.py"), working_dir=str(P), base_dir=str(P))  # without required init args
out["rc_pylib_noargs"] = {"s": round(time.perf_counter() - t, 3), "n": len(d0.keywords), "errors": [e.message[:100] for e in d0.errors or []]}
t = time.perf_counter()
src = str(P / "resources/shop.resource")
rd = get_model_doc(get_resource_model(src), src)
kw = next(iter(rd.keywords.get_all("Login As User")))
out["rc_resource"] = {"s": round(time.perf_counter() - t, 3), "n": len(rd.keywords), "sig": kw.signature, "md": kw.to_markdown()[:300]}
t = time.perf_counter()
ld = LibraryDocumentation(str(P / "libs/ShopApi.py::http://x"))
out["rf_pylib_args"] = {"s": round(time.perf_counter() - t, 3), "n": len(ld.keywords)}
try:
    LibraryDocumentation(str(P / "libs/ShopApi.py"))
    out["rf_pylib_noargs"] = "ok"
except Exception as e:
    out["rf_pylib_noargs"] = f"ERR {type(e).__name__}: {str(e)[:100]}"
t = time.perf_counter()
ld = LibraryDocumentation(src)
out["rf_resource"] = {"s": round(time.perf_counter() - t, 3), "n": len(ld.keywords), "first": ld.keywords[0].name}
# suite file user keywords via RF
print(json.dumps(out, indent=1, default=str))
