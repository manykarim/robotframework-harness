"""In-process warm analyzer (copied from round-3 lsp_quality/warm_analyzer.py): the engine of `robotcode analyze code`,

Same objects the CLI builds (CodeAnalyzer -> RobotFrameworkLanguageProvider -> DocumentsCacheHelper
-> ImportsManager/Namespace), but documents stay open: a check re-reads the file, applies a full
change (invalidates that document's namespace) and re-runs analyze + collect. Library docs stay
cached in the ImportsManager, so a warm check costs only parse + namespace analysis.

Resources edited on disk: the analyzer's FileWatcherManager is a dummy, so we detect mtime changes
ourselves, push the new text into the resource TextDocument and fire did_change_watched_files.

robotcode names come from robotcode_adapter (the only module that imports robotcode internals).

Usage (stand-alone): python -m rf_harness.runtime.analyzer ROOT FILE [FILE...]
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence

from .robotcode_adapter import (
    AnalyzeConfig,
    Application,
    CodeAnalyzer,
    ModifiersConfig,
    changed_file_events,
    document_uri,
    get_config_files,
    load_robot_config_from_path,
)

SEV = {1: "error", 2: "warning", 3: "info", 4: "hint"}


class WarmAnalyzer:
    def __init__(self, root: Path, profiles: Sequence[str] = (), variables: Optional[Dict[str, str]] = None,
                 extra_ignore: Sequence[str] = (), search_order: Sequence[str] = ()) -> None:
        t0 = time.perf_counter()
        self.root = Path(root).resolve()
        self.app = Application()
        config_files, root_folder, _ = get_config_files([self.root], root_folder=self.root)
        robot_config = load_robot_config_from_path(*config_files, extra_tools={"robotcode-analyze": AnalyzeConfig})
        cfg = (robot_config.tool or {}).get("robotcode-analyze") or AnalyzeConfig()
        if cfg.modifiers is None:
            cfg.modifiers = ModifiersConfig()
        if extra_ignore:
            cfg.modifiers.ignore = [*(cfg.modifiers.ignore or []), *extra_ignore]
        if search_order:
            cfg.global_library_search_order = [*(cfg.global_library_search_order or []), *search_order]
        profile = robot_config.combine_profiles(*profiles).evaluated_with_env()
        if variables:
            profile.variables = {**(profile.variables or {}), **variables}
        self.profile = profile
        self.ca = CodeAnalyzer(app=self.app, analysis_config=cfg.to_workspace_analysis_config(),
                               robot_profile=profile, root_folder=root_folder)
        self.provider = next(iter(self.ca.language_handlers))
        self.cache = self.provider._document_cache
        self.folder = self.ca.workspace.workspace_folders[0]
        self.res_mtime: Dict[str, int] = {}
        self.init_ms = round((time.perf_counter() - t0) * 1000, 1)

    # ------------------------------------------------------------------ resources
    def _refresh_resources(self) -> List[str]:
        """Detect edited resource/variable files imported so far and invalidate them."""
        changed: List[str] = []
        docs = self.ca.workspace.documents
        for u in list(docs):
            d = docs.get(u)
            if d is None:
                continue
            p = d.uri.to_path()
            if p.suffix.lower() not in (".resource", ".robot", ".py") or not p.is_file():
                continue
            m = p.stat().st_mtime_ns
            old = self.res_mtime.setdefault(str(p), m)
            if m != old:
                self.res_mtime[str(p)] = m
                changed.append(str(p))
        if changed:
            im = self.cache.get_imports_manager_for_workspace_folder(self.folder)
            for p in changed:
                d = docs.get(document_uri(Path(p)))
                if d is not None:
                    d.apply_full_change(None, Path(p).read_text())
            im.did_change_watched_files(self, changed_file_events(changed))
        return changed

    # ------------------------------------------------------------------ check
    def check(self, path: Path, text: Optional[str] = None, lines: Optional[Iterable[int]] = None,
              min_severity: int = 2) -> Dict[str, Any]:
        """Analyze `path` (current disk text unless `text`), return diagnostics (1-based lines).
        lines: only report diagnostics starting on these 1-based lines (plus file-level ones on line 1..)."""
        t0 = time.perf_counter()
        path = Path(path).resolve()
        reloaded = self._refresh_resources()
        text = path.read_text() if text is None else text
        doc = self.ca.workspace.documents.get_or_open_document(path)
        if doc.text() != text or doc.version is None:
            doc.apply_full_change((doc.version or 0) + 1, text)
        t1 = time.perf_counter()
        ns = self.cache.get_namespace(doc)
        ns.analyze()
        raw = self.cache.get_diagnostic_modifier(doc).modify_diagnostics(ns.diagnostics)
        t2 = time.perf_counter()
        want = set(lines) if lines is not None else None
        out = []
        for d in raw:
            sev = int(d.severity or 1)
            if sev > min_severity:
                continue
            ln = d.range.start.line + 1
            if want is not None and ln not in want:
                continue
            out.append({"line": ln, "col": d.range.start.character + 1, "sev": SEV.get(sev, sev),
                        "code": str(d.code), "msg": d.message.splitlines()[0][:300]})
        return {"ok": not any(x["sev"] == "error" for x in out), "diags": out, "n_all": len(raw),
                "ms": round((t2 - t0) * 1000, 1), "analyze_ms": round((t2 - t1) * 1000, 1),
                **({"reloaded": [os.path.basename(r) for r in reloaded]} if reloaded else {})}


if __name__ == "__main__":
    import json

    root = Path(sys.argv[1])
    wa = WarmAnalyzer(root)
    print("init_ms", wa.init_ms)
    for rep in range(2):
        for f in sys.argv[2:]:
            r = wa.check(Path(f))
            print(rep, Path(f).name, json.dumps(r)[:300])
