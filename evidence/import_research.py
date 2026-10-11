#!/usr/bin/env python3
"""Rebuild the evidence archive from the rf-mcp research sources (provenance tool, stdlib only).

    python3 evidence/import_research.py --source-repo ~/workspace/rf-mcp-robotcode [--commit 7994ae3] \
        [--worktree DIR] [--transcripts DIR] [--out evidence]

What it does, in order:
  1. Exports the committed research tree (``git archive <commit> experiments/robotcode-remote
     docs/research/static-analysis-quality-gates.md``) and maps every file to its place in the archive
     (``rounds/<NN>-<topic>/``, ``harness-versions/``, ``eval-snapshots/``). An unmapped file is an error.
  2. Adds the on-disk files of the research worktree that were never committed but belong to the evidence:
     result-file backups (the sources of the excluded rows), runner logs, the OpenRouter price cache and the
     results_complex fixture (``data/output.xml``). A committed file that differs on disk is taken from disk.
  3. Scrubs every file with ``scrub.py`` while copying, so only scrubbed bytes reach the archive.
  4. Writes the excluded rows per round (``excluded_*.jsonl``), the scenario and grader definitions per A/B round
     (``scenarios.json``), the run configuration per round (``config.json``), ``provenance.json`` (source path,
     source sha256, archive sha256, scrub substitutions per file) and ``scrub_report.json``.

Hand-written files (``README.md`` per round, ``incidents.md``, ...) are never touched. Run ``checksums.py --write``
afterwards. Transcripts are not imported here; ``pack_transcripts.py`` turns them into release assets.
"""
from __future__ import annotations

import argparse
import dataclasses
import gzip
import hashlib
import importlib.util
import io
import json
import re
import subprocess
import sys
import tarfile
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import scrub  # noqa: E402

COMMIT = "7994ae3"
RESEARCH = "experiments/robotcode-remote/"
STATIC_DOC = "docs/research/static-analysis-quality-gates.md"
SNAP = "eval-snapshots/ab-7994ae3/"

R01, R02, R03 = "rounds/01-capability-spikes/", "rounds/02-local-runtime/", "rounds/03-lsp-robocop/"
R03A, R03B = "rounds/03a-ab-file-authoring/", "rounds/03b-ab-live-journeys/"
R04, R05 = "rounds/04-hooks-matrix-and-hooks-ab/", "rounds/05-v2/"
R06, R07 = "rounds/06-v3-main/", "rounds/07-v31-v32/"
RSA = "rounds/static-analysis/"

# research-tree prefix -> archive prefix (longest prefix wins)
PREFIX_MAP: list[tuple[str, str]] = [
    ("research/", R01 + "research/"),
    ("map/", R01 + "map/"),
    ("hints/", R01 + "hints/"),
    ("stepwise/", R01 + "stepwise/"),
    ("static/", R01 + "static/"),
    ("locators/", R01 + "locators/"),
    ("round2/", R02),
    ("round3/", R03),
    ("round4/", R04),
    ("round5/", R05),
    ("round6/", R06),
    ("build_suite_bugs/", RSA + "build_suite_bugs/"),
    ("ab/fixtures/", SNAP + "fixtures/"),
    ("ab/fixtures_live/", SNAP + "fixtures_live/"),
    ("ab/skillpkg/verify/", R03A + "build-verification/skillpkg/"),
    ("ab/hookpkg/verify/", R04 + "build-verification/hookpkg/"),
    ("ab/hookpkg2/verify/", R05 + "build-verification/hookpkg2/"),
    ("ab/hookpkg3/verify/", R06 + "build-verification/hookpkg3/"),
    ("ab/hookpkg31/verify/", R07 + "build-verification/hookpkg31/"),
    ("ab/hookpkg32/verify/", R07 + "build-verification/hookpkg32/"),
    ("ab/skillpkg/", "harness-versions/skillpkg/"),
    ("ab/hookpkg/", "harness-versions/hookpkg/"),
    ("ab/hookpkg2/", "harness-versions/hookpkg2/"),
    ("ab/hookpkg3/", "harness-versions/hookpkg3/"),
    ("ab/hookpkg31/", "harness-versions/hookpkg31/"),
    ("ab/hookpkg32/", "harness-versions/hookpkg32/"),
]
PREFIX_MAP.sort(key=lambda kv: -len(kv[0]))

FILE_MAP = {
    "ab/findings.md": R03A + "findings.md",
    "ab/findings_live.md": R03B + "findings_live.md",
    "ab/findings_hooks.md": R04 + "findings_hooks.md",
    "ab/hookpkg_build_findings.md": R04 + "hookpkg_build_findings.md",
    "ab/findings_v2.md": R05 + "findings_v2.md",
    "ab/hookpkg2_build_findings.md": R05 + "hookpkg2_build_findings.md",
    "ab/findings_v3main.md": R06 + "findings_v3main.md",
    "ab/hookpkg3_build_findings.md": R06 + "hookpkg3_build_findings.md",
    "ab/findings_v31.md": R07 + "findings_v31.md",
    "ab/hookpkg31_build_findings.md": R07 + "hookpkg31_build_findings.md",
    "ab/hookpkg32_build_findings.md": R07 + "hookpkg32_build_findings.md",
}

HARNESS_CODE = {"harness.py", "analyze.py", "analyze_hooks.py", "journey_evidence.py", "openrouter.py",
                "run_ab_resilient.sh", "run_hooks_ab.sh", "run_v2_ab.sh", "rerun_auth_failures.sh"}

# which round a harness data file (results_/report_/summary_/run_/pilot_/verify_ ... ) belongs to
_ROUND_OF_TAG = [
    (re.compile(r"v3[12]"), R07),
    (re.compile(r"v3main|v3pilot"), R06),
    (re.compile(r"_v2\b|_v2[._]|v2_ab"), R05),
    (re.compile(r"hooks"), R04),
    (re.compile(r"(?:^|_)rc(?:[._]|$)"), R03A),
    (re.compile(r"live|rerun_auth"), R03B),
]

# on-disk files that are not in the commit and stay out of the archive (pattern on the research-relative path)
DISK_EXCLUDE = [
    (re.compile(r"^ab/harness/transcripts_"), "transcripts: published as release assets (pack_transcripts.py)"),
    (re.compile(r"(^|/)__pycache__/"), "Python bytecode cache"),
    (re.compile(r"\.egg-info/"), "editable-install metadata"),
    (re.compile(r"^ab/harness/\.run_ab_[^/]+\.lock$"), "empty runner lock files"),
    (re.compile(r"^ab/hookpkg[0-9]*/verify/runs/"), "build-verification agent runs (not committed upstream)"),
]


@dataclasses.dataclass
class Item:
    archive: str  # path relative to the archive root
    source: str  # research-relative path, or "docs/..." for the static-analysis report
    origin: str  # commit | disk | disk-differs-from-commit
    data: bytes


def harness_dest(name: str) -> str | None:
    if name in HARNESS_CODE:
        return SNAP + "harness/" + name
    if name == "or_prices.json":
        return R07 + "results/or_prices.json"
    rnd = next((r for pat, r in _ROUND_OF_TAG if pat.search(name)), None)
    if rnd is None:
        return None
    if ".bak." in name or ".before_" in name:
        return rnd + "backups/" + name
    if name.endswith(".log"):
        return rnd + "logs/" + name
    if name.startswith("results_"):
        return rnd + "results/" + name
    if name.startswith(("report_", "summary_", "verify_")):
        return rnd + "reports/" + name
    return None


def map_path(rel: str) -> str | None:
    """research-relative path -> archive path."""
    if rel in FILE_MAP:
        return FILE_MAP[rel]
    if rel.startswith("ab/harness/") and rel.count("/") == 2:
        return harness_dest(rel.split("/")[-1])
    for prefix, dest in PREFIX_MAP:
        if rel.startswith(prefix):
            return dest + rel[len(prefix):]
    return None


def git_archive(repo: Path, commit: str) -> dict[str, bytes]:
    out = subprocess.run(["git", "-C", str(repo), "archive", "--format=tar", commit, RESEARCH.rstrip("/"), STATIC_DOC],
                         check=True, capture_output=True).stdout
    files: dict[str, bytes] = {}
    with tarfile.open(fileobj=io.BytesIO(out)) as tar:
        for m in tar.getmembers():
            if m.isfile():
                f = tar.extractfile(m)
                assert f is not None
                files[m.name] = f.read()
    return files


def collect(repo: Path, worktree: Path, commit: str) -> tuple[list[Item], list[dict]]:
    committed = git_archive(repo, commit)
    items: list[Item] = []
    excluded: list[dict] = []
    seen: set[str] = set()
    unmapped: list[str] = []
    for path, data in sorted(committed.items()):
        if path == STATIC_DOC:
            rel, dest = path, RSA + "static-analysis-quality-gates.md"
        else:
            rel = path[len(RESEARCH):]
            dest = map_path(rel)
        if dest is None:
            unmapped.append(path)
            continue
        origin = "commit"
        disk = worktree / path
        if disk.is_file():
            on_disk = disk.read_bytes()
            if on_disk != data:
                data, origin = on_disk, "disk-differs-from-commit"
        items.append(Item(dest, path, origin, data))
        seen.add(path)
    # on-disk additions under ab/ (never committed)
    ab = worktree / RESEARCH / "ab"
    for f in sorted(p for p in ab.rglob("*") if p.is_file()):
        path = f.relative_to(worktree).as_posix()
        if path in seen:
            continue
        rel = path[len(RESEARCH):]
        reason = next((why for pat, why in DISK_EXCLUDE if pat.search(rel)), None)
        if reason:
            excluded.append({"source": path, "reason": reason})
            continue
        dest = map_path(rel)
        if dest is None:
            unmapped.append(path + " (disk)")
            continue
        items.append(Item(dest, path, "disk", f.read_bytes()))
    if unmapped:
        raise SystemExit("unmapped source files:\n  " + "\n  ".join(unmapped))
    dests = Counter(i.archive for i in items)
    dup = [d for d, n in dests.items() if n > 1]
    if dup:
        raise SystemExit(f"two sources map to the same archive path: {dup}")
    return items, excluded


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def write_items(items: list[Item], out: Path, rules: list[scrub.Rule]) -> tuple[list[dict], scrub.Report]:
    report = scrub.Report("apply", "research sources")
    prov: list[dict] = []
    for it in items:
        payload, was_gz = (gzip.decompress(it.data), True) if it.source.endswith(".gz") else (it.data, False)
        before = Counter(report.rule_counts)
        report.files_scanned += 1
        clean = scrub.scrub_bytes(payload, it.archive, rules, report)
        if clean is None:
            prov.append({"archive": it.archive, "source": it.source, "origin": it.origin, "skipped": True})
            continue
        changed = clean is not payload
        data = (scrub.gzip_bytes(clean) if was_gz else clean) if changed else it.data
        if changed:
            report.files_changed += 1
        dest = out / it.archive
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
        subs = {k: v - before.get(k, 0) for k, v in report.rule_counts.items() if v - before.get(k, 0)}
        prov.append({"archive": it.archive, "source": it.source, "origin": it.origin,
                     "source_sha256": sha256(it.data), "archive_sha256": sha256(data),
                     "substitutions": dict(sorted(subs.items()))})
    return prov, report


# --------------------------------------------------------------------------- #
# excluded rows
# --------------------------------------------------------------------------- #
def _rows(path: Path) -> list[str]:
    return [ln for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]


def _reason_for_removed(round_dir: str, backup: str, row: dict) -> tuple[str, str]:
    st, agent = row.get("status"), str(row.get("agent") or "")
    blob = (row.get("stderr_tail") or "") + json.dumps(row.get("agent_info") or {})
    if st == "aborted":
        return "aborted", ("cell interrupted when the runner was stopped (external SIGTERM or restart); the runner "
                           "drops aborted rows on resume and re-runs the cell")
    if "credits402" in backup and (agent.startswith("cc-or:") or agent.startswith("oc-or:")):
        return "credits_402", ("OpenRouter account balance exhausted (HTTP 402 from ~12:00 local on 2026-10-10); "
                               "detected by the transcript scan for 'API Error: 402' / 'requires more credits'")
    if "chatgpt.com/backend-api" in blob or "codexinfra" in backup:
        return "codex_backend_outage", ("Codex backend request failed (transport channel closed, 3 tool calls); "
                                        "infrastructure failure, cell re-run")
    if round_dir == R03B and agent == "claude" and "before_auth_rerun" in backup:
        return "auth_expiry", ("Claude Code OAuth login expired during the run (2026-10-02); 25 Claude cells "
                               "dropped by rerun_auth_failures.sh and re-run")
    return "removed", "row present in a backup but not in the final results file"


def excluded_rows(out: Path) -> dict[str, dict[str, int]]:
    """Writes rounds/<NN>/excluded/excluded_<reason>.jsonl; returns {round: {reason: n}}."""
    summary: dict[str, dict[str, int]] = {}
    for rnd in (R03A, R03B, R04, R05, R06, R07):
        rdir = out / rnd
        by_reason: dict[str, list[dict]] = defaultdict(list)
        seen: dict[str, dict] = {}
        finals = {p.name: p for p in sorted((rdir / "results").glob("results_*.jsonl"))}
        for bak in sorted((rdir / "backups").glob("*.jsonl")) if (rdir / "backups").is_dir() else []:
            final_name = re.sub(r"\.(bak|before_|pass1).*$", "", bak.name)
            final_name = final_name if final_name.endswith(".jsonl") else final_name + ".jsonl"
            final = finals.get(final_name)
            if final is None:
                raise SystemExit(f"no final results file for backup {bak}")
            final_lines = set(_rows(final))
            for line in _rows(bak):
                if line in final_lines:
                    continue
                if line in seen:
                    seen[line]["backups"].append(f"backups/{bak.name}")
                    continue
                row = json.loads(line)
                reason, detail = _reason_for_removed(rnd, bak.name, row)
                rec = {"reason": reason, "detail": detail, "key": row.get("key"), "results_file": f"results/{final_name}",
                       "in_results_file": False, "backups": [f"backups/{bak.name}"], "row": row}
                seen[line] = rec
                by_reason[reason].append(rec)
        # rows still inside a results file that the analyzers do not score as valid
        for name, final in finals.items():
            for line in _rows(final):
                row = json.loads(line)
                if row.get("contaminated"):
                    by_reason["contaminated"].append({
                        "reason": "contaminated",
                        "detail": ("cross-arm marker in the transcript (helper CLI / MCP call outside its arm); the "
                                   "row stays in the results file with contaminated=true. The published reports "
                                   "score it (analyze.py drops it only with --drop-contaminated); see claims.yaml "
                                   "for the sensitivity check"),
                        "key": row.get("key"), "results_file": f"results/{name}", "in_results_file": True,
                        "backups": [], "row": row})
                elif row.get("status") != "ok":
                    by_reason["not_ok_in_file"].append({
                        "reason": "not_ok_in_file",
                        "detail": f"status={row.get('status')}; analyzers score only status=ok rows",
                        "key": row.get("key"), "results_file": f"results/{name}", "in_results_file": True,
                        "backups": [], "row": row})
        if not by_reason:
            continue
        exdir = rdir / "excluded"
        exdir.mkdir(parents=True, exist_ok=True)
        for reason, recs in sorted(by_reason.items()):
            text = "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in recs)
            (exdir / f"excluded_{reason}.jsonl").write_text(text, encoding="utf-8")
        summary[rnd] = {k: len(v) for k, v in sorted(by_reason.items())}
    return summary


# --------------------------------------------------------------------------- #
# scenario + grader definitions, run configuration
# --------------------------------------------------------------------------- #
def _load_harness(out: Path):
    path = out / SNAP / "harness" / "harness.py"
    sys.path.insert(0, str(path.parent))
    try:
        spec = importlib.util.spec_from_file_location("ab_harness_snapshot", path)
        assert spec and spec.loader
        mod = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = mod  # dataclasses resolve string annotations through sys.modules
        spec.loader.exec_module(mod)
        return mod
    finally:
        sys.path.remove(str(path.parent))
        for p in path.parent.rglob("__pycache__"):
            for f in p.iterdir():
                f.unlink()
            p.rmdir()


def tree_sha256(root: Path) -> str:
    h = hashlib.sha256()
    for f in sorted(p for p in root.rglob("*") if p.is_file()):
        h.update(f.relative_to(root).as_posix().encode() + b"\0" + sha256(f.read_bytes()).encode() + b"\n")
    return h.hexdigest()


def round_rows(rdir: Path) -> dict[str, list[dict]]:
    return {p.name: [json.loads(ln) for ln in _rows(p)] for p in sorted((rdir / "results").glob("results_*.jsonl"))}


def write_scenarios(out: Path) -> None:
    h = _load_harness(out)
    all_scen = {s.id: s for s in h.SCENARIOS + h.LIVE_SCENARIOS}
    code = {name: sha256((out / SNAP / "harness" / name).read_bytes())
            for name in ("harness.py", "journey_evidence.py", "analyze.py", "analyze_hooks.py")}
    for rnd in (R03A, R03B, R04, R05, R06, R07):
        rdir = out / rnd
        rows = [r for rs in round_rows(rdir).values() for r in rs]
        ids = sorted({r["scenario"] for r in rows}, key=list(all_scen).index)
        scen = [dataclasses.asdict(all_scen[i]) for i in ids]
        fixtures = {}
        for s in scen:
            base = "fixtures_live" if s.get("live") else "fixtures"
            fx = out / SNAP / base / s["fixture"]
            ref = out / SNAP / base / "_reference" / s["id"]
            fixtures[s["id"]] = {
                "fixture": f"../../{SNAP}{base}/{s['fixture']}", "fixture_tree_sha256": tree_sha256(fx),
                "reference": f"../../{SNAP}{base}/_reference/{s['id']}" if ref.is_dir() else None,
                "reference_tree_sha256": tree_sha256(ref) if ref.is_dir() else None,
            }
        doc = {
            "about": ("Scenario prompts and grader definitions of this round, extracted from the archived harness "
                      "(eval-snapshots/ab-7994ae3/harness/harness.py, the version committed at the end of the "
                      "research). Per the findings, prompts and graders did not change between the rounds that "
                      "share a harness_version; graders are implemented in harness.py (_grade_one) and "
                      "journey_evidence.py."),
            "harness_versions_in_results": sorted({r.get("harness_version") for r in rows}),
            "grader_code_sha256": code,
            "scenarios": scen,
            "fixtures": fixtures,
        }
        (rdir / "scenarios.json").write_text(json.dumps(doc, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")


CLAUDE_VERSION_RE = re.compile(rb'"claude_code_version"\s*:\s*"([0-9][^"]{0,30})"')

ROUND_META: dict[str, dict] = {
    R01: {"round": "1", "title": "Capability spikes: robotcode as the execution and analysis backend",
          "dates": ["2026-10-01"], "kind": "spike",
          "tools": {"robotcode": "2.7.0", "robotframework": "7.5 (cross-checked 7.3.2)", "rf-mcp": "0.36.0"},
          "agents": "none (scripted experiments; research subagents of the coordinating session)",
          "studies": ["research", "map", "hints", "stepwise", "static", "locators"]},
    R02: {"round": "2", "title": "Local runtime: embedded robotcode helper, stock REPL, keyword docs, agent channel",
          "dates": ["2026-10-01"], "kind": "spike",
          "agents": {"claude": "Claude Code 2.1.286 + claude-haiku-4-5", "codex": "Codex 0.153.4 + gpt-5.6-luna@low",
                     "opencode": "OpenCode 1.15.12 + MiniMax-M2.7", "copilot": "Copilot CLI 1.0.54 + gpt-4.1"},
          "sessions": "34 headless agent sessions (agents study)",
          "studies": ["agents", "keyword_docs", "python_api", "repl_only"]},
    R03: {"round": "3", "title": "robotcode LSP diagnostics in agents, LSP as validator, Robocop 9.1",
          "dates": ["2026-10-01"], "kind": "spike",
          "agents": {"claude": "Claude Code 2.1.286", "opencode": "OpenCode 1.15.12", "copilot": "Copilot CLI 1.0.54",
                     "codex": "Codex 0.153.4"},
          "tools": {"robotcode": "2.7.0", "robocop": "9.1.0"},
          "sessions": "32 headless agent sessions (agent_lsp study)",
          "studies": ["agent_lsp", "lsp_quality", "robocop"]},
    R03A: {"round": "A/B 1", "title": "A/B file authoring: rf-mcp vs Agent Skill + local package (hard scenarios)",
           "kind": "ab", "findings": ["findings.md"], "transcripts": ["transcripts_rc", "transcripts_rc_pilot",
                                                                      "transcripts_rc_smoke"],
           "main_results": "results/results_rc.jsonl"},
    R03B: {"round": "A/B 2", "title": "A/B live journeys: rf-mcp vs Agent Skill + local package vs plain agent",
           "kind": "ab", "findings": ["findings_live.md"],
           "transcripts": ["transcripts_live", "transcripts_live_pilot", "transcripts_live_smoke"],
           "main_results": "results/results_live.jsonl"},
    R04: {"round": "4", "title": "Hook capability matrix + A/B hooks (hookpkg) vs CLI (skillpkg)",
          "kind": "ab", "findings": ["hooks_matrix/findings.md", "findings_hooks.md", "hookpkg_build_findings.md"],
          "transcripts": ["transcripts_live_hooks"], "main_results": "results/results_live_hooks.jsonl",
          "matrix_agents": {"claude": "Claude Code 2.1.289", "codex": "Codex 0.161.0", "copilot": "Copilot CLI 1.0.91",
                            "opencode": "OpenCode 1.15.12"}},
    R05: {"round": "5", "title": "REPL/debugger hook research + A/B hookpkg v1 vs hookpkg2 (v2)",
          "kind": "ab", "findings": ["research/findings.md", "findings_v2.md", "hookpkg2_build_findings.md"],
          "transcripts": ["transcripts_live_v2"], "main_results": "results/results_live_v2.jsonl"},
    R06: {"round": "6", "title": "Diagnosis + same-day A/B rf-mcp vs v2 vs v3",
          "kind": "ab", "findings": ["diag/findings.md", "findings_v3main.md", "hookpkg3_build_findings.md"],
          "transcripts": ["transcripts_live_v3main", "transcripts_live_v3pilot"],
          "main_results": "results/results_live_v3main.jsonl"},
    R07: {"round": "7", "title": "v3.1 per-model output profiles, cheap OpenRouter models, Haiku 5.5, and v3.2",
          "kind": "ab", "findings": ["findings_v31.md", "hookpkg31_build_findings.md", "hookpkg32_build_findings.md"],
          "transcripts": ["transcripts_live_v31sub", "transcripts_live_v31or", "transcripts_live_v31gem",
                          "transcripts_live_v32", "transcripts_live_v32smoke"],
          "main_results": "results/results_live_v31sub.jsonl"},
    RSA: {"round": "static analysis", "title": "Static-analysis quality gates: Robocop + robotcode analyze",
          "dates": ["2026-10-02"], "kind": "study",
          "tools": {"robotframework": "7.5 (cross-checked 7.3.2)", "robotcode": "2.7.0", "robocop": "9.1.0",
                    "browser": "20.5.0 (cross-checked 19.12.7)", "requests": "0.9.7"}},
}


def claude_versions(transcripts: Path | None, dirs: list[str]) -> list[str]:
    if transcripts is None:
        return []
    found: set[str] = set()
    for d in dirs:
        for f in sorted((transcripts / d).glob("*/*.gz")):
            if not f.parent.name.startswith(("claude", "cc-or")):
                continue
            with gzip.open(f, "rb") as fh:
                head = fh.read(200_000)
            m = CLAUDE_VERSION_RE.search(head)
            if m:
                found.add(m.group(1).decode())
    return sorted(found)


def write_configs(out: Path, transcripts: Path | None) -> None:
    for rnd, meta in ROUND_META.items():
        rdir = out / rnd
        cfg: dict = {"round": meta["round"], "folder": rnd.rstrip("/").split("/")[-1], "title": meta["title"],
                     "kind": meta["kind"]}
        if meta["kind"] != "ab":
            cfg.update({k: v for k, v in meta.items() if k not in ("round", "title", "kind")})
            (rdir / "config.json").write_text(json.dumps(cfg, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
            continue
        runs = []
        for name, rows in round_rows(rdir).items():
            ok = [r for r in rows if r.get("status") == "ok"]
            started = sorted(r.get("started_at", "") for r in rows if r.get("started_at"))
            finished = sorted(r.get("finished_at", "") for r in rows if r.get("finished_at"))
            models: dict[str, list[str]] = defaultdict(list)
            for r in rows:
                m = r.get("model") or "?"
                if r.get("effort"):
                    m += f"@{r['effort']}"
                if m not in models[r["agent"]]:
                    models[r["agent"]].append(m)
            runs.append({
                "results_file": f"results/{name}",
                "rows": len(rows), "rows_ok": len(ok),
                "agents": sorted({r["agent"] for r in rows}),
                "models": {k: v for k, v in sorted(models.items())},
                "arms": sorted({r["arm"] for r in rows}),
                "scenarios": sorted({r["scenario"] for r in rows}),
                "reps": sorted({r["rep"] for r in rows}),
                "harness_version": sorted({str(r.get("harness_version")) for r in rows}),
                "max_turns": sorted({r.get("max_turns") for r in rows if r.get("max_turns") is not None}),
                "timeout_s": sorted({r.get("timeout_s") for r in rows if r.get("timeout_s") is not None}),
                "started_utc": started[0] if started else None,
                "finished_utc": finished[-1] if finished else None,
            })
        cfg["findings"] = meta["findings"]
        cfg["main_results"] = meta["main_results"]
        cfg["runs"] = runs
        days = {(r["started_utc"] or "")[:10] for r in runs} | {(r["finished_utc"] or "")[:10] for r in runs}
        cfg["dates_utc"] = sorted(days - {""})
        cfg["harness_snapshot"] = "../../" + SNAP + "harness/"
        cfg["scenario_definitions"] = "scenarios.json"
        cfg["transcript_dirs"] = meta["transcripts"]
        cfg["agent_versions_recorded"] = {
            "claude_code": claude_versions(transcripts, meta["transcripts"]) or "not recorded",
            "codex": "not recorded in results or transcripts",
            "opencode": "not recorded in results or transcripts",
        }
        if "matrix_agents" in meta:
            cfg["hook_matrix_agents"] = meta["matrix_agents"]
        excluded: dict[str, int] = {}
        for f in sorted((rdir / "excluded").glob("excluded_*.jsonl")):
            excluded[f.stem[len("excluded_"):]] = len(_rows(f))
        cfg["excluded_rows"] = {"counts": excluded, "files": "excluded/excluded_<reason>.jsonl",
                                "note": ("rows with in_results_file=true are still in the results file "
                                         "(contaminated / not ok); the others were removed from it and are kept "
                                         "here with their reason and the backup they came from")}
        (rdir / "config.json").write_text(json.dumps(cfg, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")


def remove_previous_import(out: Path) -> None:
    """Delete what an earlier run generated (hand-written README.md files stay)."""
    prov = out / "provenance.json"
    if not prov.is_file():
        return
    for entry in json.loads(prov.read_text(encoding="utf-8"))["files"]:
        (out / entry["archive"]).unlink(missing_ok=True)
    for rnd in ROUND_META:
        for name in ("scenarios.json", "config.json"):
            (out / rnd / name).unlink(missing_ok=True)
        for f in (out / rnd / "excluded").glob("excluded_*.jsonl"):
            f.unlink()
    for top in ("rounds", "harness-versions", "eval-snapshots"):
        for d in sorted((out / top).rglob("*"), key=lambda p: -len(p.parts)):
            if d.is_dir() and not any(d.iterdir()):
                d.rmdir()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--source-repo", required=True, type=Path, help="rf-mcp checkout that contains the commit")
    ap.add_argument("--commit", default=COMMIT)
    ap.add_argument("--worktree", type=Path, default=None, help="research worktree on disk (default: --source-repo)")
    ap.add_argument("--transcripts", type=Path, default=None,
                    help="transcripts root (default: <worktree>/experiments/robotcode-remote/ab/harness)")
    ap.add_argument("--out", type=Path, default=HERE)
    args = ap.parse_args(argv)
    worktree = (args.worktree or args.source_repo).expanduser()
    transcripts = (args.transcripts or worktree / RESEARCH / "ab" / "harness").expanduser()
    out: Path = args.out
    remove_previous_import(out)
    rules = scrub.build_rules()
    items, disk_excluded = collect(args.source_repo.expanduser(), worktree, args.commit)
    prov, report = write_items(items, out, rules)
    excluded = excluded_rows(out)
    write_scenarios(out)
    write_configs(out, transcripts if transcripts.is_dir() else None)
    origin = Counter(p["origin"] for p in prov)
    (out / "provenance.json").write_text(json.dumps({
        "source": {"repository": "manykarim/rf-mcp (branch research/robotcode-remote-mcp)", "commit": args.commit,
                   "paths": [RESEARCH.rstrip("/"), STATIC_DOC]},
        "scrub_py_sha256": sha256((HERE / "scrub.py").read_bytes()),
        "files_by_origin": dict(sorted(origin.items())),
        "not_imported": disk_excluded,
        "excluded_rows": {k.rstrip("/").split("/")[-1]: v for k, v in excluded.items()},
        "files": sorted(prov, key=lambda p: p["archive"]),
    }, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    rep = report.to_json()
    by_top: dict[str, Counter] = defaultdict(Counter)
    for f, rules_ in rep["files"].items():
        top = "/".join(f.split("/")[:2])
        by_top[top].update(rules_)
    (out / "scrub_report.json").write_text(json.dumps({
        "about": "Substitutions made by scrub.py while importing (counts only, never values).",
        "files_scanned": rep["files_scanned"], "files_changed": rep["files_changed"],
        "files_skipped": rep["files_skipped"], "rule_counts": rep["rule_counts"],
        "by_folder": {k: dict(sorted(v.items())) for k, v in sorted(by_top.items())},
    }, indent=1) + "\n", encoding="utf-8")
    print(f"imported {len(prov)} files ({dict(origin)}), {rep['files_changed']} changed by the scrub")
    print("scrub substitutions:", rep["rule_counts"])
    print("excluded rows:", {k.rstrip('/').split('/')[-1]: v for k, v in excluded.items()})
    print("not imported (on disk only):", len(disk_excluded))
    return 0


if __name__ == "__main__":
    sys.exit(main())
