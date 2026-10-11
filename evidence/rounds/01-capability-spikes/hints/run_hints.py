"""Feed robotcode-derived (keyword, args, error, libraries) into rf-mcp's REAL hint code
and compare with what native rf-mcp returned for the same mistake.

Pipeline emulation (mirrors keyword_executor.py ~L4755-4795, minus live-state steps):
  lower   = generate_hints(HintContext(... no search order))      # rf_native_context_manager
  plugin  = plugin_manager.generate_failure_hints(library_name, ...)
  hints   = plugin + lower;  if empty -> generate_hints(... session_search_order=libraries)
  hints   = KeywordExecutor._add_link_image_locator_guidance(...)
  minimal = KeywordExecutor._rank_and_deduplicate_hints(hints, "minimal")

  cd ~/workspace/rf-mcp-robotcode && uv run python experiments/robotcode-remote/hints/run_hints.py
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from corpus import CORPUS  # noqa: E402
from parse_robotcode import (  # noqa: E402
    executable_lines, parse_k, parse_plain_v2, parse_replserver, top_failures_k,
)

from robotmcp.components.execution.keyword_executor import KeywordExecutor  # noqa: E402
from robotmcp.plugins.manager import get_library_plugin_manager  # noqa: E402
from robotmcp.utils.hints import HintContext, generate_hints  # noqa: E402

RUNS = HERE / "runs"
OUT = HERE / "results"
from robotmcp.config.library_registry import _ensure_plugins_registered  # noqa: E402

_ensure_plugins_registered()  # register builtin plugins (RequestsLibrary etc.) like the server does
PM = get_library_plugin_manager()


def hint_key(h):
    if isinstance(h, dict):
        return h.get("title") or h.get("type") or json.dumps(h)[:60]
    return str(h)[:60]


def pipeline(keyword, args, error, libraries, library_name):
    args = list(args or [])
    lower = generate_hints(HintContext(session_id="remote", keyword=keyword or "", arguments=args,
                                       error_text=error or ""))
    plugin = PM.generate_failure_hints(library_name, None, keyword or "", args, error or "") if library_name else []
    hints = list(plugin or []) + list(lower or [])
    if not hints:
        hints = generate_hints(HintContext(session_id="remote", keyword=keyword or "", arguments=args,
                                           error_text=error or "", session_search_order=libraries))
    hints = KeywordExecutor._add_link_image_locator_guidance(KeywordExecutor, keyword or "", args, hints)
    minimal = KeywordExecutor._rank_and_deduplicate_hints(list(hints), "minimal")
    return [hint_key(h) for h in hints], [hint_key(h) for h in minimal]


def native_hints(m):
    p = RUNS / m["id"] / "native" / "result.json"
    d = json.loads(p.read_text())
    step = next((s for s in d.get("steps", []) if s.get("is_mistake")), None)
    if not step:
        return None
    r = step.get("response") or {}
    hints = r.get("hints") or []
    if isinstance(hints, str) and hints.startswith("Content saved to "):
        path = re.match(r"Content saved to (\S+?)(?: \(|$)", hints).group(1)
        moved = RUNS / "native_artifacts" / Path(path).name  # worktree .robotmcp_artifacts/ moved here
        try:
            txt = (moved if moved.exists() else Path(path)).read_text()
            hints = json.loads(txt)
        except Exception:  # noqa: BLE001
            hints = [f"<externalized:{path}>"]
    return {"success": r.get("success"), "error": r.get("error"),
            "hints": [hint_key(h) for h in hints] if isinstance(hints, list) else [str(hints)[:60]],
            "minimal": [hint_key(h) for h in KeywordExecutor._rank_and_deduplicate_hints(
                hints if isinstance(hints, list) else [], "minimal")],
            "pre_validation": bool(r.get("pre_validation_failed"))}


def libs_from_k(k_txt):
    owners = []
    for s in parse_k(k_txt):
        o = s.get("owner")
        if o and o not in owners and o != "None":
            owners.append(o)
    # rf-mcp puts the UI library first in the search order
    order = [o for o in owners if o in ("Browser", "SeleniumLibrary", "AppiumLibrary")] + \
            [o for o in owners if o not in ("Browser", "SeleniumLibrary", "AppiumLibrary")]
    return order + ([] if "BuiltIn" in order else ["BuiltIn"])


def libs_from_input(stdin_lines):
    libs = []
    for ln in executable_lines(stdin_lines):
        if ln["keyword"].lower() == "import library" and ln["args"]:
            name = Path(ln["args"][0]).stem if ln["args"][0].endswith(".py") else ln["args"][0]
            libs.append(name)
    order = [x for x in libs if x in ("Browser", "SeleniumLibrary")] + [x for x in libs if x not in ("Browser", "SeleniumLibrary")]
    return order + ["BuiltIn"]


def first_fail(steps):
    return steps[0] if steps else None


def main():
    OUT.mkdir(exist_ok=True)
    rows = []
    for m in CORPUS:
        d = RUNS / m["id"]
        k_txt = (d / "k" / "stdout.txt").read_text()
        plain_txt = (d / "plain" / "stdout.txt").read_text()
        stdin = (d / "plain" / "stdin.txt").read_text().splitlines()
        cells = json.loads((d / "replserver" / "cells.json").read_text())
        nat = native_hints(m)
        ac = m["agent_call"]
        row = {"id": m["id"], "title": m["title"], "native": nat, "remote": {}}

        # sanity: emulated pipeline on the NATIVE error with the agent's own call
        if nat and nat.get("error") and not nat["success"]:
            err = re.sub(r"^Keyword execution failed: ", "", nat["error"])
            lib = PM.get_library_for_keyword(ac["keyword"].lower()) if hasattr(PM, "get_library_for_keyword") else None
            full, mini = pipeline(ac["keyword"], ac["arguments"], err, m["libraries"], lib)
            row["emulated_on_native_error"] = {"hints": full, "minimal": mini}

        kf = first_fail(top_failures_k(k_txt))
        rsf = first_fail(parse_replserver(cells))
        pf = first_fail(parse_plain_v2(plain_txt, stdin))
        pf0 = first_fail(parse_plain_v2(plain_txt, None))
        k_libs = libs_from_k(k_txt)
        in_libs = libs_from_input(stdin)
        variants = {}
        if kf:
            variants["k"] = (kf["keyword"], kf["args"], kf["error"], k_libs, kf.get("owner"))
        if rsf:
            variants["replserver"] = (rsf["keyword"], rsf["args"], rsf["error"], k_libs, rsf.get("owner"))
        if pf:
            owner = PM.get_library_for_keyword((pf["keyword"] or "").lower()) if pf.get("keyword") else None
            variants["plain+input"] = (pf["keyword"], pf["args"], pf["error"], in_libs, owner)
        if pf0:
            variants["error+libs"] = ("", [], pf0["error"], in_libs, None)
            variants["error only"] = ("", [], pf0["error"], None, None)
        for name, (kw, args, err, libs, owner) in variants.items():
            full, mini = pipeline(kw, args, err, libs, owner)
            row["remote"][name] = {"keyword": kw, "args": args, "libraries": libs, "library_name": owner,
                                   "error_head": (err or "").splitlines()[0][:160] if err else "",
                                   "hints": full, "minimal": mini}
        rows.append(row)
    (OUT / "hints_comparison.json").write_text(json.dumps(rows, indent=2))
    print(json.dumps([{"id": r["id"], "native": (r["native"] or {}).get("hints"),
                       "emul": (r.get("emulated_on_native_error") or {}).get("hints"),
                       "k": (r["remote"].get("k") or {}).get("hints"),
                       "plain": (r["remote"].get("plain+input") or {}).get("hints"),
                       "err_only": (r["remote"].get("error only") or {}).get("hints")} for r in rows], indent=1))


if __name__ == "__main__":
    main()
