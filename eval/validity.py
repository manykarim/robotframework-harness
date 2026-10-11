#!/usr/bin/env python3
"""Invalid-session detection for the evaluation harness (stdlib only).

A session is INVALID when it did no real work for reasons outside the arm under test. Such rows get
`status: "invalid"` plus `invalid_reason` / `invalid_kind`, are excluded from scoring (the analyzers only score
`status == "ok"` rows) and are rerun (the harness only skips cells with an ok row). Kinds:

  credits         provider out of credits: "API Error: 402", "requires more credits", "Insufficient credits",
                  or a Claude Code result event with api_error_status 402
  auth            authentication failure: "API Error: 401", "Failed to authenticate", or api_error_status 401
  backend_outage  agent backend outage (Codex): "request timed out" / "error sending request" seen at least twice
                  AND fewer than 10 tool calls (the round-7 Codex cell that ended after 3 tool calls)

Only agent-authored or agent-reported text is scanned (assistant text, result/error events, stderr), never tool
results, so a page under test that mentions "credits" cannot invalidate a session. Claude Code records a 402 as a
normal `result:success` turn, so the exit code alone is not enough (round-7 incident: 76 cells written as ok).

CLI (used by run_ab_resilient.sh):
    python3 validity.py clean RESULTS.jsonl     drop aborted / torn rows, re-label ok rows whose transcript shows an
                                                invalid session (backup written when anything changed); prints
                                                "<dropped> <relabelled>"
    python3 validity.py scan RESULTS.jsonl      report rows that would be invalid (no changes), JSON
"""
from __future__ import annotations

import argparse
import gzip
import json
import os
import shutil
import sys
import time
from collections.abc import Iterable
from pathlib import Path
from typing import Any

PROVIDER_PATTERNS: list[tuple[str, str]] = [
    ("API Error: 402", "credits"),
    ("requires more credits", "credits"),
    ("Insufficient credits", "credits"),
    ("API Error: 401", "auth"),
    ("Failed to authenticate", "auth"),
]
OUTAGE_PATTERNS = ("request timed out", "error sending request")
OUTAGE_MIN_HITS = 2              # "repeated"
OUTAGE_MAX_TOOL_CALLS = 10       # fewer than this many tool calls = the session did no real work
OUTAGE_AGENTS = ("codex",)


def _base_agent(agent: str) -> str:
    a = str(agent or "")
    if a.startswith("cc-or:"):
        return "claude"
    if a.startswith("oc-or:"):
        return "opencode"
    return a


def _text(x: Any) -> str:
    if x is None:
        return ""
    return x if isinstance(x, str) else json.dumps(x, default=str)


def agent_texts(agent: str, lines: Iterable[str]) -> tuple[list[str], list[int]]:
    """(agent-authored/reported texts, api_error_status values) from a JSONL agent transcript.

    claude: assistant text blocks (incl. <synthetic> error messages), result.result, result api_error_status
    codex: agent_message text, error / turn.failed events
    opencode: text parts, error events
    copilot: assistant.message content, session.error / error events
    any: the harness' __stderr_tail__ record. Tool calls and tool results are never included."""
    agent = _base_agent(agent)
    texts: list[str] = []
    statuses: list[int] = []
    for line in lines:
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            d = json.loads(line)
        except ValueError:
            continue
        if not isinstance(d, dict):
            continue
        if "__stderr_tail__" in d:
            texts.append(_text(d["__stderr_tail__"]))
            continue
        if "__harness_calls__" in d:
            continue
        t = d.get("type")
        if agent == "claude":
            if t == "assistant":
                for c in (d.get("message") or {}).get("content") or []:
                    if isinstance(c, dict) and c.get("type") == "text":
                        texts.append(_text(c.get("text")))
            elif t == "result":
                texts.append(_text(d.get("result")))
                try:
                    if d.get("api_error_status") is not None:
                        statuses.append(int(d["api_error_status"]))
                except (TypeError, ValueError):
                    pass
            elif t == "system" and str(d.get("subtype") or "").startswith("api_error"):
                texts.append(_text(d))
        elif agent == "codex":
            if t in ("turn.failed", "error"):
                texts.append(_text(d.get("error") or d.get("message") or d))
            elif t == "item.completed":
                it = d.get("item") or {}
                if it.get("type") in ("agent_message", "error"):
                    texts.append(_text(it.get("text") or it.get("message")))
        elif agent == "opencode":
            part = d.get("part") if isinstance(d.get("part"), dict) else {}
            if t == "text":
                texts.append(_text(part.get("text")))
            elif t == "error":
                texts.append(_text(d.get("error") or d))
        elif agent == "copilot":
            data = d.get("data") or {}
            if t == "assistant.message":
                texts.append(_text(data.get("content")))
            elif t in ("session.error", "error"):
                texts.append(_text(data or d))
        else:                                   # unknown format: scan the whole event
            texts.append(_text(d))
    return texts, statuses


def classify(agent: str, transcript_lines: Iterable[str], stderr: str = "", tool_calls: int | None = None,
             extra_texts: Iterable[str] = ()) -> dict | None:
    """None for a valid session, else {"kind", "reason"} (see the module docstring)."""
    texts, statuses = agent_texts(agent, transcript_lines)
    texts += [stderr or ""] + [_text(x) for x in extra_texts]
    blob = "\n".join(t for t in texts if t)
    for st in statuses:
        if st in (401, 402):
            return {"kind": "credits" if st == 402 else "auth", "reason": f"provider error: api_error_status {st}"}
    for pat, kind in PROVIDER_PATTERNS:
        if pat in blob:
            return {"kind": kind, "reason": f"provider error: {pat!r}"}
    if _base_agent(agent) in OUTAGE_AGENTS:
        hits = {p: blob.count(p) for p in OUTAGE_PATTERNS}
        n = sum(hits.values())
        tc = tool_calls if isinstance(tool_calls, int) else 0
        if n >= OUTAGE_MIN_HITS and tc < OUTAGE_MAX_TOOL_CALLS:
            seen = ", ".join(f"{p!r} x{c}" for p, c in hits.items() if c)
            return {"kind": "backend_outage",
                    "reason": f"agent backend outage: {seen} with {tc} tool calls (< {OUTAGE_MAX_TOOL_CALLS})"}
    return None


def classify_files(agent: str, stdout_log: Path, stderr_log: Path | None, tool_calls: int | None,
                   extra_texts: Iterable[str] = ()) -> dict | None:
    """classify() on a live cell's agent_stdout.log / agent_stderr.log (harness, before grading)."""
    try:
        lines = Path(stdout_log).read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        lines = []
    err = ""
    if stderr_log is not None:
        try:
            err = Path(stderr_log).read_text(encoding="utf-8", errors="replace")[-20000:]
        except OSError:
            err = ""
    return classify(agent, lines, err, tool_calls, extra_texts)


def _open_transcript(path: Path) -> list[str]:
    try:
        opener = gzip.open if str(path).endswith(".gz") else open
        with opener(path, "rt", encoding="utf-8", errors="replace") as f:
            return f.read().splitlines()
    except OSError:
        return []


def classify_row(row: dict, base_dir: Path) -> dict | None:
    """classify() for an archived results row: its gz transcript (relative to the results file's directory), its
    stderr_tail and agent_info errors, and metrics.tool_calls."""
    lines: list[str] = []
    t = row.get("transcript")
    if t:
        p = Path(t)
        lines = _open_transcript(p if p.is_absolute() else base_dir / p)
    tc = (row.get("metrics") or {}).get("tool_calls")
    errs = (row.get("agent_info") or {}).get("errors") or []
    return classify(row.get("agent") or "", lines, row.get("stderr_tail") or "", tc, [str(e) for e in errs])


def mark_invalid(row: dict, inv: dict) -> dict:
    row["status"] = "invalid"
    row["invalid_kind"] = inv["kind"]
    row["invalid_reason"] = inv["reason"]
    row["primary_pass"] = False
    return row


def clean_results(results: Path, now: str | None = None) -> tuple[int, int, Path | None]:
    """Runner cleanup: drop aborted rows and torn lines, re-label ok rows with an invalid session. Writes a backup
    (<results>.bak.<time>.jsonl) and replaces the file atomically when anything changed.
    Returns (dropped, relabelled, backup path or None)."""
    results = Path(results)
    if not results.exists():
        return 0, 0, None
    base = results.parent
    out: list[str] = []
    dropped = relabelled = 0
    for line in results.read_text(encoding="utf-8").splitlines(True):
        try:
            r = json.loads(line)
        except ValueError:
            dropped += 1                      # a torn last line of a killed run
            continue
        if not isinstance(r, dict) or r.get("status") == "aborted":
            dropped += 1
            continue
        if r.get("status") == "ok":
            inv = classify_row(r, base)
            if inv:
                mark_invalid(r, inv)
                relabelled += 1
                line = json.dumps(r, default=str) + "\n"
        out.append(line if line.endswith("\n") else line + "\n")
    bak = None
    if dropped or relabelled:
        stem = str(results)[:-6] if str(results).endswith(".jsonl") else str(results)
        bak = Path(f"{stem}.bak.{now or time.strftime('%Y%m%d-%H%M%S')}.jsonl")
        shutil.copyfile(results, bak)
        tmp = results.with_name(results.name + ".tmp")
        tmp.write_text("".join(out), encoding="utf-8")
        os.replace(tmp, results)
    return dropped, relabelled, bak


def scan_results(results: Path) -> list[dict]:
    """Rows (any status but aborted) whose transcript shows an invalid session: [{key, status, kind, reason}]."""
    out = []
    base = Path(results).parent
    for line in Path(results).read_text(encoding="utf-8").splitlines():
        try:
            r = json.loads(line)
        except ValueError:
            continue
        if r.get("status") == "aborted":
            continue
        inv = classify_row(r, base)
        if inv:
            out.append({"key": r.get("key"), "status": r.get("status"), **inv})
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="invalid-session detection for eval results")
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("clean", help="drop aborted/torn rows, re-label invalid sessions; prints '<dropped> <relabelled>'")
    c.add_argument("results")
    s = sub.add_parser("scan", help="list rows whose transcript shows an invalid session (read-only)")
    s.add_argument("results")
    args = ap.parse_args(argv)
    if args.cmd == "clean":
        d, r, _ = clean_results(Path(args.results))
        print(d, r)
        return 0
    rows = scan_results(Path(args.results))
    print(json.dumps({"invalid": len(rows), "rows": rows}, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
