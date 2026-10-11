"""THE hook entry point (v2) for every agent and event (stdlib only, fast start):

    python -S <pkg>/rfharness2/hook.py <event> --agent claude|codex|copilot|opencode   (event JSON on stdin)
    python -m rfharness2.hook <event> --agent ...                                      (same, slower start)

events: SessionStart | UserPromptSubmit | PreToolUse | PostToolUse | Stop | SessionEnd
  SessionStart   start the live-session + static-gate daemons (detached, idempotent), compact keyword docs ->
                 .rf/docs, snapshot RF files + the original suites (tests, assertions) for the suite guard
  UserPromptSubmit  first prompt: short project context (installed libraries + versions, robot.toml, resources, tests)
  PreToolUse     Write/Edit/apply_patch of *.robot/*.resource: static gate (deny NEW hard errors, modernize outdated
                 syntax), suite guard (removed tests / fewer assertions / failure hiding -> deny);
                 Bash: deny pip/playwright installs and robot -P/PYTHONPATH; robotcode repl|shell|robot-debug|run-debug:
                 format card (first use), safe auto-fixes by input rewriting, deny what cannot be fixed;
                 Read/view of huge output.xml / page sources -> deny with the right tool
  PostToolUse    edit of a test file -> new/changed lines run live (short element timeout, recheck slow vs missing,
                 page capture into .rf/state/latest + step history, docs of the failing keyword in .rf/docs/kw/);
                 imports -> .rf/docs/<Name>.md + .full.md; Bash `robot` -> output.xml summary, failing keyword docs,
                 live reproduction; REPL/debug commands -> FAIL/exception lines, docs, .rf/state/repl-last.txt;
                 the same step failing >= 3x -> loop hint
  Stop           quality gate: test files changed since their last green plain robot run -> block once
  SessionEnd     stop both daemons, remove generated files
Never raises into the agent: any internal error -> no output, exit 0 (logged to .rf/hook2/hooks.jsonl).
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
import traceback
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import guards  # type: ignore
    import hookcore as hc  # type: ignore
    import kwdoc  # type: ignore
    import replfmt  # type: ignore
else:
    from . import guards, kwdoc, replfmt
    from . import hookcore as hc

EVENTS = {"sessionstart": "session-start", "session-start": "session-start", "pretooluse": "pre-tool",
          "pre-tool": "pre-tool", "posttooluse": "post-tool", "post-tool": "post-tool", "stop": "stop",
          "posttoolusefailure": "post-tool",
          "agentstop": "stop", "sessionend": "session-end", "session-end": "session-end",
          "userpromptsubmit": "prompt", "userpromptsubmitted": "prompt", "prompt": "prompt"}
REWRITE_AGENTS = set((os.environ.get("RFH2_REWRITE_AGENTS") or "claude,opencode,codex,copilot").split(","))
REPRODUCE = os.environ.get("RFH2_REPRODUCE", "1") != "0"
MAX_DENIALS = int(hc.env_f("RFH2_MAX_DENIALS", 3))
MAX_DENIALS_OPENCODE = int(hc.env_f("RFH2_MAX_DENIALS_OPENCODE", 2))
MAX_STOP_BLOCKS = int(hc.env_f("RFH2_MAX_STOP_BLOCKS", 2))
LOOP_AT = int(hc.env_f("RFH2_LOOP_AT", 3))
REPL_LISTENER = None if os.environ.get("RFH2_SHORT_TIMEOUTS", "1") == "0" else \
    f"{os.environ.get('RFH2_SHORT_TIMEOUT') or '2.5s'}:{os.environ.get('RFH2_RECHECK_SETTLE') or '10s'}"
READ_TOOLS = {"read", "view", "read_file", "open_file"}

NOTE = """Robot Framework hook harness is active (skill: robotframework). A live Robot Framework session runs in the
background for this workspace:
- Every Write/Edit of a test file (*** Test Cases ***) runs its new or changed test lines in that session; the result
  (per-line PASS/FAIL, message, hints) is attached to your edit. A failing line stays open: fix it (or insert lines
  before it) and only that part re-runs, in the same page.
- Live element timeout is SHORT (2.5 s) so bad locators fail fast; a timeout is re-checked once with the normal
  timeout and reported as SLOW (add an explicit wait) or MISSING (wrong selector/iframe). Never in your files.
- After page-changing steps and locator failures: .rf/state/latest/{page.txt,controls.txt,aria.yaml,source.html,
  screenshot.jpg} (+ history .rf/state/step-NN-<keyword>/). controls.txt has a suggested `=>` selector per control.
- Failing keyword -> its full doc in .rf/docs/kw/<Library>.<Keyword>.md; imported libraries -> .rf/docs/<Name>.md
  (one line per keyword; grep -i 'words' .rf/docs/*.md) + <Name>.full.md.
- Final proof: plain `robot -d results <file>`; its failures are summarized for you automatically."""


NOTE_SHORT = """Robot Framework hooks are active (skill: robotframework): every edit of a .robot test runs its new lines
live and the result (PASS/FAIL, fix hints) comes back with the edit. Page after each step: .rf/state/latest/controls.txt
(selectors), aria.yaml, page.txt; failing keyword docs: .rf/docs/kw/; keyword list: grep -i 'words' .rf/docs/*.md.
Finish with a plain `robot -d results <file>` run."""


# ------------------------------------------------------------------------------------------------ helpers
class Ctx:
    def __init__(self, event: str, agent: str, payload: Dict[str, Any]) -> None:
        self.event, self.agent, self.payload = event, agent, payload
        self.root = hc.find_root(payload)
        self.d = hc.Dirs(self.root)
        self.cwd = Path(payload.get("cwd") or self.root)
        self.t0 = time.monotonic()
        self.log: Dict[str, Any] = {"event": event, "agent": agent}

    def left(self, budget: float = hc.BUDGET) -> float:
        return max(1.0, budget - (time.monotonic() - self.t0))

    @property
    def max_denials(self) -> int:
        return MAX_DENIALS_OPENCODE if self.agent == "opencode" else MAX_DENIALS


def _src_lines(path: Path) -> List[str]:
    t = hc.read(path)
    return t.splitlines() if t else []


def _cut(s: Any, n: int) -> str:
    s = s if isinstance(s, str) else json.dumps(s, default=str)
    s = " ".join(s.split()) if "\n" in s else s
    return s if len(s) <= n else s[: n - 3] + "..."


def _size(n: int) -> str:
    return f"{n}B" if n < 1000 else (f"{n / 1024:.1f}K" if n < 1_000_000 else f"{n / 1048576:.1f}M")


def _bump(c: Ctx, key: str) -> int:
    with hc.Store(c.d) as s:
        den = s.data.setdefault("denials", {})
        den[key] = den.get(key, 0) + 1
        return den[key]


def _flag(c: Ctx, key: str) -> bool:
    """True the first time a flag is set in this session."""
    with hc.Store(c.d) as s:
        if s.data.get(key):
            return False
        s.data[key] = time.time()
        return True


def _code_hint(errs: List[Dict[str, Any]], text: str) -> List[str]:
    hints = []
    msgs = " ".join(e.get("msg", "") for e in errs)
    unknown = [m.group(1) for e in errs for m in [re.search(r"No keyword with name '([^']+)'", e.get("msg", ""))] if m]
    root = guards.missing_keywords_header(text, unknown) if unknown else None
    if root:
        return [root]
    if any(e["code"] == "KeywordNotFound" for e in errs):
        if "frame" in msgs.lower() and "Browser" in text:
            hints.append("Browser has no frame-switching keyword: address iframe content as `id=<frame> >>> <selector>`")
        hints.append("unknown keyword: grep -i '<words>' .rf/docs/*.md for the right name and arguments")
    if "arguments, got" in msgs:
        hints.append("argument count: the signature is in .rf/docs/<Library>.md (separate arguments with 4 spaces)")
    if any(e["code"] == "NotPortable" for e in errs):
        hints.append("the final plain `robot` run must find imports by path (${CURDIR}/...)")
    return hints


def _response_text(payload: Dict[str, Any]) -> str:
    for k in ("tool_response", "toolResult", "tool_output", "output", "error"):
        v = payload.get(k)
        if v is None:
            continue
        if isinstance(v, dict):
            parts = [str(v.get(x) or "") for x in ("stdout", "stderr", "textResultForLlm", "output", "content")]
            v = "\n".join(p for p in parts if p) or json.dumps(v)
        if isinstance(v, list):
            v = "\n".join(str(x.get("text") if isinstance(x, dict) else x) for x in v)
        if isinstance(v, str) and v.strip():
            return v
    return ""


# ------------------------------------------------------------------------------------------------ daemons
def ensure_exec(c: Ctx, wait: float = 45.0) -> Optional[Dict[str, Any]]:
    st = hc.daemon_state(c.d, "exec")
    if st and st.get("ready"):
        return st
    return hc.start_daemon(c.d, "exec", wait=wait)


def ensure_lint(c: Ctx, wait: float = 0.0) -> Optional[Dict[str, Any]]:
    st = hc.daemon_state(c.d, "lint")
    if st and st.get("ready"):
        return st
    return hc.start_daemon(c.d, "lint", wait=wait)


def spawn_docs(c: Ctx) -> None:
    if (c.d.docs / ".complete").exists():
        return
    c.d.docs.mkdir(parents=True, exist_ok=True)
    lock = c.d.docs / ".running"
    try:
        if lock.exists() and time.time() - lock.stat().st_mtime < 120:
            return
        lock.write_text(str(os.getpid()))
    except OSError:
        return
    env = dict(os.environ)
    env["PYTHONPATH"] = str(hc.PKG_ROOT) + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    with open(c.d.docs / ".log", "ab") as log:
        subprocess.Popen([hc._python(), "-m", "rfharness2.docs", str(c.root)], cwd=str(c.root), env=env,
                         stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)


def collect_pending(c: Ctx, timeout: float) -> List[str]:
    """results of live runs that were still running when an earlier hook returned."""
    with hc.Store(c.d) as s:
        pend = list(s.data.get("pending") or [])
    if not pend:
        return []
    st = hc.daemon_state(c.d, "exec")
    out, keep = [], []
    t_end = time.monotonic() + timeout
    for p in pend:
        if st is None:
            continue
        r = hc.request(st, {"op": "wait", "job": p["job"], "timeout": max(0.2, t_end - time.monotonic())},
                       timeout=max(1.0, t_end - time.monotonic()) + 5)
        if r.get("status") == "running":
            keep.append(p)
            continue
        if r.get("error") and not r.get("ran"):
            continue
        _enrich(c, r)
        out.append(f"[result of the live run started {time.strftime('%H:%M:%S', time.localtime(p['ts']))} "
                   f"after your earlier {p.get('what', 'edit')}]\n" + format_run(r, c))
        c.log["pending_delivered"] = c.log.get("pending_delivered", 0) + 1
    with hc.Store(c.d) as s:
        s.data["pending"] = keep
    return out


def _enrich(c: Ctx, r: Dict[str, Any]) -> None:
    """hook-side additions to a live-run result: docs of failing keywords, metrics."""
    ndoc = 0
    for rec in (r.get("ran") or []):
        lf = rec.get("leaf")
        if rec.get("status") == "PASS" or not lf or ndoc >= 2:
            continue
        try:
            rec["doc"] = kwdoc.kw_doc(c.root, lf.get("owner") or "BuiltIn", lf["kw"], lf.get("source"),
                                      wait=min(kwdoc.DOC_WAIT, max(0.0, c.left() - 2)))
            ndoc += 1
        except Exception as e:
            rec["doc_error"] = f"{type(e).__name__}: {e}"[:160]
    if ndoc:
        c.log["docs_kw"] = c.log.get("docs_kw", 0) + ndoc
    caps = [x for x in (r.get("captures") or []) if not x.get("unchanged")]
    if caps:
        c.log["captures"] = c.log.get("captures", 0) + len(caps)
        c.log["capture_ms"] = [x.get("ms") for x in caps if x.get("ms") is not None][:6]
    rc = [x["recheck"] for x in (r.get("ran") or []) if x.get("recheck")]
    if rc:
        c.log["rechecks"] = c.log.get("rechecks", 0) + len(rc)
        c.log["recheck_verdicts"] = [x.get("verdict") for x in rc]


def run_live(c: Ctx, req: Dict[str, Any], what: str) -> Dict[str, Any]:
    st = ensure_exec(c, wait=min(45.0, c.left()))
    if st is None:
        return {"ok": False, "error": "live session did not start (see .rf/exec2/daemon.log)"}
    left = c.left()
    r = hc.request(st, {**req, "timeout": left}, timeout=left + 10)
    if r.get("status") == "running":
        with hc.Store(c.d) as s:
            s.data.setdefault("pending", []).append({"job": r.get("job"), "ts": time.time(), "what": what})
        c.log["still_running"] = True
    lines = [x for x in (r.get("ran") or []) if x.get("status")]
    c.log["ran_lines"] = c.log.get("ran_lines", 0) + len(lines)
    c.log["failed_lines"] = c.log.get("failed_lines", 0) + sum(1 for x in lines if x.get("status") != "PASS")
    _enrich(c, r)
    return r


# ------------------------------------------------------------------------------------------------ formatting
def _doc_line(rec: Dict[str, Any]) -> Optional[str]:
    d = rec.get("doc")
    if not d:
        return None
    s = f"      docs: {d['path']}"
    if d.get("signature"):
        s += f"  {_cut(d['signature'], 150)}"
    if d.get("first"):
        s += f" -- {_cut(d['first'], 110)}"
    if not d.get("ready"):
        s += "  (being written)"
    return s


def _recheck_line(rec: Dict[str, Any], rel: str) -> Optional[str]:
    rc = rec.get("recheck")
    if not rc:
        return None
    sel = rc.get("selector") or "<sel>"
    if rc.get("verdict") == "slow":
        st = "PASSED on the re-check" if rec.get("status") == "PASS" else "still failed after it appeared"
        return (f"      recheck: SLOW -- the element appeared after {rc.get('appeared_after_s')} s (live timeout "
                f"{rc.get('short_s')} s, normal {rc.get('normal_s')} s); {st}. Add before line {rec.get('line')}: "
                f"`Wait For Elements State    {sel}    visible    timeout={max(10, int(rc.get('normal_s') or 10))}s`")
    if rc.get("verdict") == "missing":
        if rc.get("settled_s") is not None:
            s = (f"      recheck: MISSING -- the page had not changed for {rc.get('settled_s')} s (longer than the normal "
                 f"{rc.get('normal_s')} s timeout): wrong selector, iframe or hidden element -- not a timing issue")
        else:
            s = (f"      recheck: MISSING -- not there after the normal {rc.get('normal_s')} s either: wrong selector, "
                 "iframe (`<frame> >>> sel`) or hidden; see .rf/state/latest/controls.txt")
        if rc.get("frame"):
            s += f"\n      found inside an iframe: use `{rc['frame']}`"
        for n in (rc.get("near") or [])[:2]:
            s += f"\n      similar control: {_cut(n, 160)}"
        return s
    return None


def _rec_line(rec: Dict[str, Any], src: List[str], rel: str) -> List[str]:
    ln = rec.get("line") or 0
    code = src[ln - 1].strip() if 0 < ln <= len(src) else rec.get("kw", "")
    st = rec.get("status", "?")
    tag = f"L{ln}"
    out = []
    if st == "PASS":
        s = f"  {tag} PASS  {_cut(code, 100)}"
        if rec.get("assign") and "ret" in rec:
            s += f"  -> {_cut(rec['ret'], 90)}"
        out.append(s)
        r = _recheck_line(rec, rel)
        if r:
            out.append(r)
        return out
    if st == "NOT RUN" and rec.get("static"):
        out.append(f"  {tag} NOT RUN (static error)  {_cut(code, 90)}")
        for x in rec["static"][:2]:
            out.append(f"      {x['code']}: {_cut(x['msg'], 220)}")
        return out
    g = rec.get("guard")
    if st == "NOT RUN" and g:
        out.append(f"  {tag} NOT RUN (refused before execution: {g.get('cls')})  {_cut(code, 90)}")
        r = _recheck_line(rec, rel)
        if r:
            out.append(r)
        elif g.get("fix"):
            out.append(f"      fix: {_cut(g['fix'], 330)}")
        if g.get("error"):
            out.append(f"      selector error: {_cut(g['error'], 200)}")
        d = _doc_line(rec)
        if d:
            out.append(d)
        return out
    out.append(f"  {tag} {st}  {_cut(code, 110)}")
    if rec.get("msg"):
        inside = ""
        if rec.get("failed_in"):
            inside = f"  (failed inside: {rec['failed_in']}" + (f" at {rec['failed_at']}" if rec.get("failed_at") else "") + ")"
        out.append(f"      {_cut(rec['msg'], 380)}" + inside)
    r = _recheck_line(rec, rel)
    if r:
        out.append(r)
    if rec.get("probe"):
        out.append(f"      probe: {_cut(rec['probe'], 160)}")
    for h in (rec.get("hints") or [])[:2]:
        t = f"      hint: {_cut(h.get('title', ''), 120)}"
        if h.get("msg"):
            t += f" -- {_cut(h['msg'], 200)}"
        if h.get("try"):
            t += f"  try: {_cut(' | '.join(map(str, h['try'][:2])), 160)}"
        out.append(t)
    d = _doc_line(rec)
    if d:
        out.append(d)
    if rec.get("logs"):
        out.append(f"      log: {_cut(rec['logs'][0], 200)}")
    return out


def _controls_line(rows: List[str], n: int = 7) -> Optional[str]:
    items = []
    for r in rows:
        m = re.search(r'"([^"]{1,30})"', r)
        s = re.search(r"   => (\S+(?: \S+)*?)(?:   \(|$)", r)
        if s:
            items.append((f'"{m.group(1)}" ' if m else "") + s.group(1))
        if len(items) >= n:
            break
    return ("  controls: " + " | ".join(items)) if items else None


def _page(p: Dict[str, Any], failed: bool, agent: str) -> List[str]:
    if not p or p.get("error"):
        return [f"  page capture failed: {_cut(p.get('error'), 160)}"] if p and p.get("error") else []
    head = f"Page ({p.get('dir')}): \"{_cut(p.get('title') or '', 70)}\"  {_cut(p.get('url') or '', 140)}"
    if p.get("unchanged"):
        return [head + "  (unchanged since the last capture; .rf/state/latest/)"]
    out = [head]
    files = ", ".join(f"{n} {_size(sz)}" for n, sz in (p.get("files") or []))
    fr = p.get("iframes") or []
    out.append(f"  {p.get('n_controls', 0)} controls" + (f"; iframes: {', '.join(fr[:3])} (`<frame> >>> <sel>`)" if fr
                                                           else "") + f"; .rf/state/latest/: {files}")
    cl = _controls_line(p.get("controls_top") or [], 5 if agent == "opencode" else 7)
    if cl:
        out.append(_cut(cl, 330))
    return out


COMPACT = set((os.environ.get("RFH2_COMPACT_AGENTS") or "opencode").split(","))


def _format_compact(r: Dict[str, Any], c: Ctx, head: Optional[str]) -> str:
    """short live-run result for weak models (round-5 OpenCode finding): failures only, one page line, NEXT: line."""
    rel = r.get("file") or "?"
    src = _src_lines(c.root / rel)
    ran = r.get("ran") or []
    out = [head or f"Live run of {rel}:"]
    if r.get("status") == "running":
        return out[0] + " still running; the result comes with your next edit."
    if r.get("error"):
        out.append(f"could not run: {_cut(r['error'], 200)}")
    passed = [x for x in ran if x.get("status") == "PASS" and not x.get("recheck")]
    if passed:
        out.append(f"L{passed[0].get('line')} PASS" if len(passed) == 1 else
                   f"L{passed[0].get('line')}-L{passed[-1].get('line')} PASS ({len(passed)} lines)")
    for rec in ran:
        if rec.get("status") == "PASS" and not rec.get("recheck"):
            continue
        ln = rec.get("line") or 0
        code = src[ln - 1].strip() if 0 < ln <= len(src) else rec.get("kw", "")
        out.append(f"L{ln} {rec.get('status')}  {_cut(code, 90)}")
        g = rec.get("guard") or {}
        if rec.get("msg") and not g:
            out.append(f"  {_cut(rec['msg'], 200)}")
        rl = _recheck_line(rec, rel)
        if rl:
            out += ["  " + x.strip() for x in rl.split("\n")[:2]]
        elif g.get("fix"):
            out.append(f"  fix: {_cut(g['fix'], 200)}")
        elif rec.get("hints"):
            h = rec["hints"][0]
            out.append(f"  hint: {_cut(h.get('title', ''), 90)}" + (f" try: {_cut(h['try'][0], 80)}" if h.get("try") else ""))
        d = rec.get("doc")
        if d:
            out.append(f"  docs: {d['path']}" + (f" {_cut(d.get('signature'), 90)}" if d.get("signature") else ""))
    p = r.get("page") or {}
    if p and not p.get("error"):
        cl = _controls_line(p.get("controls_top") or [], 4)
        out.append(f"Page: \"{_cut(p.get('title') or '', 50)}\" {_cut(p.get('url') or '', 80)}"
                   + ("" if p.get("unchanged") else f"; .rf/state/latest/controls.txt ({p.get('n_controls', 0)} controls)"))
        if cl and not p.get("unchanged"):
            out.append(_cut(cl.strip(), 220))
    last = ran[-1] if ran else None
    if last and last.get("status") != "PASS":
        out.append(f"NEXT: fix line {last.get('line')} (or insert a line before it); only that part re-runs.")
    elif ran and r.get("file_complete"):
        out.append(f"NEXT: all lines passed live -> robot -d results {rel}")
    return hc.clip("\n".join(out), 900)


def format_run(r: Dict[str, Any], c: Ctx, head: Optional[str] = None, collapse_pass: bool = False,
               budget: int = 1900) -> str:
    if c.agent in COMPACT:
        return _format_compact(r, c, head)
    text = _format_run(r, c, head, collapse_pass)
    if len(text) > budget:           # over budget: collapse passing lines first
        text = _format_run(r, c, head, True)
    return hc.clip(text, budget)


def _format_run(r: Dict[str, Any], c: Ctx, head: Optional[str], collapse_pass: bool) -> str:
    rel = r.get("file") or "?"
    path = c.root / rel
    src = _src_lines(path)
    lines = [head or f"Live run of {rel} (hook: live Robot Framework session; the page stays open):"]
    if r.get("status") == "running":
        lines.append(f"  still running after the hook budget ({int(hc.BUDGET)} s); the result is attached to your "
                     "next edit / robot run.")
        return "\n".join(lines)
    if r.get("error"):
        lines.append(f"  could not run: {_cut(r['error'], 300)}")
    for n in (r.get("notes") or [])[:3]:
        lines.append(f"  ({_cut(n, 150)})")
    ran = r.get("ran") or []
    shown = ran
    if collapse_pass and len(ran) > 3:
        head_pass = ran[:-2] if ran[-1].get("status") != "PASS" else ran[:-1]
        if head_pass and all(x.get("status") == "PASS" and not x.get("recheck") for x in head_pass):
            shown = [{"_gap": (head_pass[0].get("line"), head_pass[-1].get("line"), len(head_pass))}] + ran[len(head_pass):]
    elif len(ran) > 14:
        mid = ran[3:-8]
        if all(x.get("status") == "PASS" and not x.get("recheck") for x in mid):
            shown = ran[:3] + [{"_gap": (mid[0].get("line"), mid[-1].get("line"), len(mid))}] + ran[-8:]
    for rec in shown:
        if "_gap" in rec:
            a, b, n = rec["_gap"]
            lines.append(f"  L{a}-L{b} PASS ({n} lines)")
            continue
        lines += _rec_line(rec, src, rel)
    if r.get("console"):
        lines.append(f"  console: {_cut(r['console'], 200)}")
    last = ran[-1] if ran else None
    failed = bool(last and last.get("status") != "PASS")
    lines += _page(r.get("page") or {}, failed, c.agent)
    caps = [x for x in (r.get("captures") or []) if not x.get("unchanged")]
    if len(caps) > 1:
        lines.append("  history: " + ", ".join(f"{x['dir']}" for x in caps[-4:]) + " (.rf/state/<dir>/)")
    if not ran and not r.get("error") and r.get("url"):
        lines.append(f"  page: {r['url']}")
    if failed:
        where = f" (or the keyword line {last['failed_at']})" if last.get("failed_at") else ""
        lines.append(f"-> Fix line {last.get('line')} of {rel}{where} or insert lines before it: the hook re-runs from "
                     "there in this page. Page: .rf/state/latest/controls.txt")
    elif ran and r.get("file_complete"):
        lines.append(f"-> All test lines passed live. Final proof before finishing: robot -d results {rel}")
    return "\n".join(lines)


# ------------------------------------------------------------------------------------------------ loops
def _loop_note(c: Ctx, key: str, failed: bool, where: str, kw: str, owner: Optional[str], sel: Optional[str]
               ) -> Optional[str]:
    with hc.Store(c.d) as s:
        loops = s.data.setdefault("loops", {})
        if not failed:
            pre = key.rsplit("|", 1)[0] + "|"
            for k in [k for k in loops if k.startswith(pre)]:
                loops.pop(k, None)
            return None
        loops[key] = loops.get(key, 0) + 1
        n = loops[key]
    if n >= LOOP_AT and (n - LOOP_AT) % 3 == 0:
        c.log["loop_hint"] = c.log.get("loop_hint", 0) + 1
        return guards.loop_hint(n, where, kw, owner, sel)
    return None


def _deep_link_note(c: Ctx, r: Dict[str, Any], text: str) -> Optional[str]:
    """a `Go To <url>` executed after the test already opened its start page = deep link into a user journey."""
    if not re.search(r"^\s+New Page\s{2,}", text, re.M):
        return None
    src = text.splitlines()
    for rec in r.get("ran") or []:
        ln = rec.get("line") or 0
        code = src[ln - 1] if 0 < ln <= len(src) else ""
        if re.match(r"^\s+Go To\s{2,}\S", code) and _flag(c, "deep_link_note"):
            c.log["deep_link_note"] = True
            return ("note: `Go To <url>` after the start page deep-links into the flow. In a user-journey test reach "
                    "each page like a user (click the link/button); if a click failed, fix that click instead of "
                    "jumping by URL.")
    return None


def _live_loops(c: Ctx, r: Dict[str, Any]) -> Optional[str]:
    ran = r.get("ran") or []
    rel = r.get("file") or "?"
    note = None
    for rec in ran:
        test = rec.get("test") or ""
        kw = (rec.get("leaf") or {}).get("kw") or rec.get("kw") or ""
        key = guards.loop_key(rel, test, rec.get("kw") or kw)
        bad = rec.get("status") != "PASS"
        sel = (rec.get("guard") or {}).get("selector") or ((rec.get("args") or [None])[0])
        n = _loop_note(c, key, bad, f"line {rec.get('line')} of {rel}", kw, (rec.get("leaf") or {}).get("owner")
                       or rec.get("owner"), sel)
        note = n or note
    return note


# ------------------------------------------------------------------------------------------------ events
def on_session_start(c: Ctx) -> hc.Result:
    c.d.make()
    n = 0
    origs: Dict[str, Any] = {}
    for f in hc.rf_files(c.root):
        text = hc.read(f) or ""
        if not hc.snapshot_path(c.d, f).exists():
            hc.save_snapshot(c.d, f, text)
            n += 1
        if hc.is_test_file(f, text):
            origs[str(f.resolve())] = guards.suite_info(text)
    with hc.Store(c.d) as s:
        s.data.setdefault("started", time.time())
        s.data["agent"] = c.agent
        s.data["session_id"] = c.payload.get("session_id")
        if "orig_suites" not in s.data:
            s.data["orig_suites"] = origs
    hc.start_daemon(c.d, "lint")
    hc.start_daemon(c.d, "exec")
    spawn_docs(c)
    try:                      # libdoc specs (global cache per version) -> instant per-keyword docs on failures
        libs = ["BuiltIn", "Browser"]
        res = []
        for f in hc.rf_files(c.root)[:60]:
            for line in (hc.read(f) or "").splitlines():
                m = re.match(r"^Library\s{2,}([A-Za-z][\w.]*)\s*(?:$|\s{2})", line)
                if m and m.group(1) not in libs:
                    libs.append(m.group(1))
            if f.suffix == ".resource" and len(res) < 5:
                res.append(("resource", str(f)))
        kwdoc.lib_docs(c.root, [("library", x) for x in libs[:8]] + res)
    except Exception as e:
        c.log["docs_error"] = str(e)[:120]
    c.log["snapshots"] = n
    c.log["orig_suites"] = len(origs)
    c.log["watch_pid"] = hc.agent_pid()
    return hc.Result("context", NOTE)


def _lazy_init(c: Ctx) -> None:
    """agents without SessionStart: first hook does it (without the note)."""
    if not (c.d.hook / "session.json").exists():
        on_session_start(c)
        c.log["lazy_start"] = True


def on_prompt(c: Ctx) -> hc.Result:
    c.d.make()
    _lazy_init(c)
    if not _flag(c, "prompt_ctx"):
        return hc.Result()
    text = guards.project_context(c.root, hc.rf_files(c.root))
    if c.agent == "opencode":         # the plugin cannot deliver the SessionStart note: put a short one here
        text = (NOTE_SHORT + ("\n" + text if text else ""))
    if not text:
        return hc.Result()
    c.log["prompt_ctx"] = len(text)
    return hc.Result("context", hc.clip(text, 1200))


def on_pre_tool(c: Ctx) -> hc.Result:
    tool = hc.tool_name(c.payload)
    inp = hc.tool_input(c.payload)
    c.log["tool"] = tool
    tl = tool.lower()
    if tl in hc.SHELL_TOOLS or (tl not in hc.EDIT_TOOLS and hc.patch_text(inp) is None
                                and isinstance(inp.get("command") or inp.get("cmd"), (str, list))):
        return _pre_bash(c, tool, inp)
    if tl in READ_TOOLS:
        return _pre_read(c, inp)
    if tl not in hc.EDIT_TOOLS and hc.patch_text(inp) is None:
        return hc.Result()
    return _pre_edit(c, tool, inp)


def _command_key(inp: Dict[str, Any]) -> Optional[str]:
    for k in ("command", "cmd"):
        if isinstance(inp.get(k), (str, list)):
            return k
    return None


def _with_command(inp: Dict[str, Any], new_cmd: str) -> Optional[Dict[str, Any]]:
    k = _command_key(inp)
    if k is None:
        return None
    up = dict(inp)
    v = inp[k]
    if isinstance(v, list):          # ["bash", "-lc", "<script>"]: replace the script element
        idx = next((i for i in range(len(v) - 1, -1, -1) if isinstance(v[i], str)), None)
        if idx is None:
            return None
        nv = list(v)
        nv[idx] = new_cmd
        up[k] = nv
    else:
        up[k] = new_cmd
    return up


def _script_of(tool: str, inp: Dict[str, Any]) -> Optional[str]:
    v = inp.get("command") if "command" in inp else inp.get("cmd")
    if isinstance(v, list):
        return next((x for x in reversed(v) if isinstance(x, str)), None)
    return hc.shell_command(tool, inp)


def _pre_bash(c: Ctx, tool: str, inp: Dict[str, Any]) -> hc.Result:
    cmd = _script_of(tool, inp)
    if not cmd or "*** Begin Patch" in cmd:
        return hc.Result()
    g = guards.bash_guard(cmd, c.cwd)
    if g:
        c.d.make()
        kind, reason = g
        n = _bump(c, f"bash:{kind}")
        c.log["guard"] = kind
        if kind == "install" and n > 2:      # never install into the shared venv; no deny loop: echo instead
            up = _with_command(inp, "echo " + json.dumps("rfharness2: " + reason.split(" Use what")[0]))
            if up is not None:
                c.log["action"] = "rewrite"
                return hc.Result("rewrite", "install refused again (command replaced by an echo).", up)
        if kind == "install" or n <= c.max_denials:
            c.log["action"] = "deny"
            return hc.Result("deny", reason)
        c.log["valve"] = True
        return hc.Result("context", "(allowed after repeated refusals) " + reason.replace(" Nothing was run.", ""))
    inv = replfmt.find(cmd)
    if inv is None:
        return hc.Result()
    c.d.make()
    _lazy_init(c)
    c.log["repl"] = inv.sub
    new, fixes, deny, warns, inv = replfmt.rewrite(cmd, c.agent, c.root, c.d.docs, c.cwd, listener=REPL_LISTENER)
    if deny:
        n = _bump(c, f"repl:{inv.sub if inv else 'x'}:{deny[:40]}")
        _flag(c, "card_shown")
        if n <= c.max_denials:
            c.log["action"] = "deny"
            c.log["format_denial"] = deny.split(":")[0][:80]
            return hc.Result("deny", deny)
        c.log["valve"] = True
        return hc.Result("context", "(allowed after repeated refusals) " + deny.split("\n")[0])
    if any("listener" in f for f in fixes):
        with hc.Store(c.d) as s:
            s.data["repl_injected"] = True
    text: List[str] = []
    # card: Claude reads PreToolUse additionalContext (round-5 verified); OpenCode gets PreToolUse notes appended to the
    # tool output by the plugin; Codex / Copilot get it with the first PostToolUse output.
    if c.agent in ("claude", "opencode") and _flag(c, "card_shown"):
        text.append(replfmt.CARD)
        c.log["card"] = "pre"
    if fixes:
        text.append("REPL command auto-fixed by the hook: " + "; ".join(fixes) + ".")
    text += warns
    if c.agent not in ("claude", "opencode") and (fixes or warns):
        with hc.Store(c.d) as s:          # delivered by PostToolUse (PreToolUse context may not reach the model)
            s.data["repl_note"] = "\n".join(text)
    if new and new != cmd:
        up = _with_command(inp, new)
        if up is not None:
            c.log["action"] = "rewrite"
            c.log["format_fixes"] = fixes
            return hc.Result("rewrite", "\n".join(text), up)
    if text:
        c.log["action"] = "context"
        return hc.Result("context", "\n".join(text))
    return hc.Result()


def _pre_read(c: Ctx, inp: Dict[str, Any]) -> hc.Result:
    fp = inp.get("file_path") or inp.get("filePath") or inp.get("path") or inp.get("file")
    if not isinstance(fp, str):
        return hc.Result()
    p = Path(os.path.expanduser(fp))
    p = p if p.is_absolute() else c.cwd / p
    if c.agent in COMPACT and p.suffix.lower() in (".jpg", ".jpeg", ".png") and ".rf" in p.parts:
        c.d.make()
        if _bump(c, "read:image") <= 1:     # text-only models: a screenshot read returns nothing useful
            c.log["guard"] = "image"
            c.log["action"] = "deny"
            return hc.Result("deny", "the screenshot is an image; read .rf/state/latest/controls.txt (selectors), "
                             "aria.yaml (texts) or page.txt instead.")
        return hc.Result()
    g = guards.read_guard(str(p), inp.get("limit") or inp.get("view_range"), inp.get("offset"))
    if not g:
        return hc.Result()
    c.d.make()
    n = _bump(c, f"read:{p}")
    c.log["guard"] = "bigread"
    if n <= min(2, c.max_denials):
        c.log["action"] = "deny"
        return hc.Result("deny", g[1])
    c.log["valve"] = True
    return hc.Result()


def _pre_edit(c: Ctx, tool: str, inp: Dict[str, Any]) -> hc.Result:
    props = [p for p in hc.proposed_edits(tool, inp, c.cwd)]
    if not props:
        return hc.Result()
    c.d.make()
    _lazy_init(c)
    for p in props:
        if p.current is not None:
            hc.save_snapshot(c.d, p.path, p.current)
    hc.start_daemon(c.d, "exec")          # warm for the PostToolUse run (no wait)
    c.log["files"] = [hc.rel(p.path, c.root) for p in props]
    # ---- suite guard: the suites as they were at session start keep tests, assertions, no failure hiding
    with hc.Store(c.d) as s:
        origs = dict(s.data.get("orig_suites") or {})
    valve_note = None
    for p in props:
        if p.new is None:
            continue
        orig = origs.get(str(p.path.resolve()))
        probs = guards.suite_guard(orig, p.new) if orig else []
        if probs:
            n = _bump(c, f"suite:{p.path}")
            c.log["guard"] = "suite"
            if n <= min(2, c.max_denials):
                c.log["action"] = "deny"
                return hc.Result("deny", f"Edit REFUSED (nothing written): {hc.rel(p.path, c.root)} is an existing "
                                 "suite and this change would weaken it:\n- " + "\n- ".join(probs) +
                                 "\nRepair the test code instead (selector, wait, iframe `>>>`, data); keep all tests "
                                 "and assertions.")
            c.log["valve"] = True
            valve_note = ("(let through after repeated refusals -- this still weakens the existing suite: "
                          + "; ".join(p_.split(" -- ")[0] for p_ in probs) + ")")
    soft: List[str] = []
    for p in props:
        if p.new is None:
            continue
        sdeny, swarn = guards.edit_findings(p.current, p.new, bool(origs.get(str(p.path.resolve()))))
        if sdeny:
            n = _bump(c, f"sleep:{p.path}")
            if n <= 1:
                c.log["guard"] = "sleep"
                c.log["action"] = "deny"
                return hc.Result("deny", f"Edit REFUSED once ({hc.rel(p.path, c.root)}): {sdeny}")
            swarn.insert(0, "Sleep kept (second attempt) -- prefer a condition wait")
        soft += [f"{hc.rel(p.path, c.root)}: {w}" for w in swarn]
    if soft:
        c.log["soft_warn"] = len(soft)
        valve_note = "\n".join(([valve_note] if valve_note else []) + soft)
    st = ensure_lint(c, wait=1.0)
    if st is None:
        c.log["gate"] = "no-daemon"
        return hc.Result("context", valve_note) if valve_note else hc.Result()
    errors: List[str] = []
    fix_notes: List[str] = [valve_note] if valve_note else []
    deny_notes: List[str] = []
    warn: List[str] = []
    updated: Optional[Dict[str, Any]] = None
    can_rewrite = c.agent in REWRITE_AGENTS
    all_errs: List[Dict[str, Any]] = []
    gate_ms = []
    for p in props:
        if p.new is None:
            continue
        if replfmt.SHORT_TIMEOUT_MARK in p.new and can_rewrite and len(props) == 1:
            stripped = "".join(l for l in p.new.splitlines(True) if replfmt.SHORT_TIMEOUT_MARK not in l)
            updated = _rewrite_input(c.agent, inp, p, stripped)
            if updated is not None:
                p.new = stripped
                fix_notes.append("removed the REPL-only short timeout line (live-only; it must not be in a suite)")
        r = hc.request(st, {"op": "gate", "path": str(p.path), "current": p.current, "proposed": p.new,
                            "wait": 1.5}, timeout=hc.GATE_TIMEOUT)
        gate_ms.append((r.get("ms") or {}).get("total"))
        if not r.get("ready"):
            c.log["gate"] = r.get("note") or r.get("error") or "not ready"
            continue
        rl = hc.rel(p.path, c.root)
        nl = p.new.splitlines()
        errs = list(r.get("errors") or [])
        fixes = r.get("fixes") or []
        fixed = r.get("fixed")
        rewritten = False
        if fixes and fixed and can_rewrite and len(props) == 1:
            up2 = _rewrite_input(c.agent, inp, p, fixed)
            if up2 is not None:
                updated, rewritten = up2, True
        if not rewritten:
            errs += r.get("fixable_errors") or []
        for e in sorted(errs, key=lambda e: e["line"]):
            code = nl[e["line"] - 1].strip() if 0 < e["line"] <= len(nl) else ""
            errors.append(f"{rl}:{e['line']} {e['code']}: {_cut(e['msg'], 220)}" + (f"   | {_cut(code, 90)}" if code else ""))
        all_errs += errs
        if fixes:
            desc = "; ".join(sorted({f"L{f['line']} {f['rule']} {f['name']}" for f in fixes}))[:300]
            deny_notes.append(f"{rl}: also outdated syntax ({desc}): use the RF 7 form (IF/ELSE, RETURN, AS, Test Tags)"
                              + (" -- or keep it, it is modernized automatically when the write goes through."
                                 if rewritten else "."))
            if rewritten:
                fix_notes.append(f"{rl}: outdated syntax was modernized automatically before writing ({desc}); "
                                 "the file on disk has the new form -- re-read it before your next edit.")
            else:
                fix_notes.append(f"{rl}: outdated syntax ({desc}) -- works, but use the RF 7 form "
                                 "(IF/ELSE, RETURN, AS, Test Tags, BREAK/CONTINUE).")
    c.log["gate_ms"] = gate_ms
    if errors:
        n = _bump(c, "gate:" + "|".join(sorted(c.log["files"])))
        if n <= c.max_denials:
            hints = _code_hint(all_errs, "\n".join(p.new or "" for p in props))
            text = ("Robot Framework static check REFUSED this edit (nothing was written). Fix these lines and retry:\n"
                    + "\n".join(errors[:8]) + ("\n" + "\n".join("hint: " + h for h in hints) if hints else "")
                    + ("\n" + "\n".join(deny_notes) if deny_notes else ""))
            c.log["action"] = "deny"
            c.log["denied_codes"] = sorted({e["code"] for e in all_errs})
            return hc.Result("deny", text)
        warn.append("static check (let through after repeated refusals) still reports:\n" + "\n".join(errors[:6]))
        c.log["valve"] = True
    else:
        with hc.Store(c.d) as s:
            s.data.get("denials", {}).pop("gate:" + "|".join(sorted(c.log["files"])), None)
    text = "\n".join(fix_notes + warn)
    if updated is not None:
        c.log["action"] = "rewrite"
        return hc.Result("rewrite", text, updated)
    if text:
        c.log["action"] = "warn"
        return hc.Result("context", text)
    return hc.Result()


def _rewrite_input(agent: str, inp: Dict[str, Any], p: "hc.Proposed", fixed: str) -> Optional[Dict[str, Any]]:
    """tool input that produces `fixed` instead of p.new (Write: content; single Edit: new_string)."""
    up = dict(inp)
    if p.kind == "write":
        for k in ("content", "file_text", "text", "contents"):
            if k in up:
                up[k] = fixed
                return up
        return None
    if p.kind == "edit" and p.edit and not p.edit["all"] and p.current is not None:
        idx = p.current.find(p.edit["old"])
        if idx < 0:
            return None
        prefix = p.current[:idx]
        suffix = p.current[idx + len(p.edit["old"]):]
        if fixed.startswith(prefix) and fixed.endswith(suffix) and len(fixed) >= len(prefix) + len(suffix):
            new_mid = fixed[len(prefix): len(fixed) - len(suffix)]
            nk = p.edit["keys"][1] if len(p.edit["keys"]) > 1 else "new_string"
            up[nk] = new_mid
            return up
        return None
    if p.kind == "patch":       # codex / copilot / opencode apply_patch: rebuild the patch text for this one file
        pt = hc.patch_text(inp)
        files = hc.parse_patch(pt or "")
        if len(files) == 1 and files[0]["op"] in ("add", "update") and not files[0].get("move_to"):
            newpt = hc.make_patch(files[0]["path"], None if files[0]["op"] == "add" else p.current, fixed)
            key = next((k for k in ("command", "patch", "patchText", "input") if isinstance(inp.get(k), str)), None)
            if key:
                up[key] = newpt
                return up
    return None


def _import_docs(c: Ctx, path: Path, text: str) -> Optional[str]:
    items = []
    for line in text.splitlines():
        m = re.match(r"^(Library|Resource)\s{2,}(\S+(?: \S+)*?)(?:\s{2,}.*)?$", line)
        if m:
            items.append((m.group(1).lower(), m.group(2)))
    if not items:
        return None
    recs = kwdoc.lib_docs(c.root, items, cwd=path.parent)
    with hc.Store(c.d) as s:
        seen = s.data.setdefault("docs_mentioned", [])
        fresh = [r for r in recs if r["name"] not in seen]
        seen += [r["name"] for r in fresh]
    if not fresh:
        return None
    c.log["docs_lib"] = [r["name"] for r in fresh]
    return ("Keyword docs for the imports: " + ", ".join(f"{r['path']}" for r in fresh)
            + " (one line per keyword; full docs: <Name>.full.md" + ("; being written" if any(r.get("new") for r in fresh)
                                                                    else "") + ").")


def on_post_tool(c: Ctx) -> hc.Result:
    tool = hc.tool_name(c.payload)
    inp = hc.tool_input(c.payload)
    c.log["tool"] = tool
    cmd = _script_of(tool, inp) if (tool.lower() in hc.SHELL_TOOLS or tool.lower() not in hc.EDIT_TOOLS) else None
    if cmd is not None and "*** Begin Patch" not in cmd:
        inv = replfmt.find(cmd)
        runs = hc.robot_invocations(cmd) if inv is None else []
        if inv is None and not runs:
            return hc.Result()
        c.d.make()
        _lazy_init(c)
        if inv is not None:
            return _after_repl(c, cmd, inv)
        return _after_robot(c, runs)
    if tool.lower() not in hc.EDIT_TOOLS and hc.patch_text(inp) is None:
        return hc.Result()
    files = hc.edited_rf_files(tool, inp, c.cwd, c.payload.get("tool_response") or c.payload.get("toolResult"))
    if not files:
        return hc.Result()
    c.d.make()
    _lazy_init(c)
    c.log["files"] = [hc.rel(f, c.root) for f in files]
    texts = collect_pending(c, timeout=min(30.0, c.left()))
    first: List[str] = []
    for f in files:
        text = hc.read(f) or ""
        test = hc.is_test_file(f, text)
        with hc.Store(c.d) as s:
            if test:
                s.data.setdefault("edited_tests", {})[str(f)] = time.time()
            elif f.suffix == ".resource":
                s.data["resource_dirty_ts"] = time.time()
        try:
            note = _import_docs(c, f, text)
        except Exception as e:
            note = None
            c.log["docs_error"] = str(e)[:160]
        if not test and f.suffix != ".resource":
            hc.save_snapshot(c.d, f, text)
            if note:
                texts.append(note)
            continue
        diags = None
        if test:
            lst = hc.daemon_state(c.d, "lint")
            if lst:
                lr = hc.request(lst, {"op": "check", "path": str(f), "wait": 1.0}, timeout=3.0)
                if lr.get("ready"):
                    diags = lr.get("diags")
        baseline = hc.load_snapshot(c.d, f)
        r = run_live(c, {"op": "hookrun", "path": str(f), "mode": "edit", "baseline": baseline, "diags": diags},
                     f"edit of {hc.rel(f, c.root)}")
        hc.save_snapshot(c.d, f, text)
        loop = _live_loops(c, r)
        if loop:
            first.append(loop)
        dl = _deep_link_note(c, r, text)
        if dl:
            texts.append(dl)
        if r.get("ran") or r.get("error") or r.get("status") == "running" or r.get("reloaded"):
            texts.append(format_run(r, c))
        elif r.get("notes") and any("no new lines" in n for n in r["notes"]):
            texts.append(f"Live run of {hc.rel(f, c.root)}: nothing new to execute ({_cut(r['notes'][0], 160)}).")
        if note:
            texts.append(note)
    texts = first + texts
    if not texts:
        return hc.Result()
    c.log["action"] = "context"
    return hc.Result("context", "\n\n".join(texts))


def _deepest(kwi: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    best = None
    while kwi:
        if kwi.get("lib"):
            best = kwi
        kwi = kwi.get("inner")
    return best


def _resource_source(c: Ctx, owner: str) -> Optional[str]:
    for f in hc.rf_files(c.root):
        if f.stem == owner and f.suffix in (".resource", ".robot"):
            return str(f)
    for py in c.root.rglob(f"{owner}.py"):
        if ".rf" not in py.parts and ".venv" not in py.parts:
            return str(py)
    return None


def _failure_docs(c: Ctx, items: List[Tuple[str, str]]) -> List[str]:
    out = []
    for owner, kw in items[:2]:
        if not kw:
            continue
        src = None if owner in kwdoc.STD or owner in kwdoc.DIST else _resource_source(c, owner)
        try:
            d = kwdoc.kw_doc(c.root, owner or "BuiltIn", kw, src, wait=min(kwdoc.DOC_WAIT, max(0.0, c.left() - 2)))
        except Exception:
            continue
        c.log["docs_kw"] = c.log.get("docs_kw", 0) + 1
        out.append(f"  docs: {d['path']}" + (f"  {_cut(d['signature'], 150)}" if d.get("signature") else "")
                   + ("" if d.get("ready") else "  (being written)"))
    return out


def _after_robot(c: Ctx, runs: List[List[str]]) -> hc.Result:
    texts = collect_pending(c, timeout=min(20.0, c.left()))
    first: List[str] = []
    for args in runs[-1:]:
        xml = hc.output_xml_for(args, c.cwd)
        if xml is None or not xml.exists() or time.time() - xml.stat().st_mtime > 900:
            xml = hc.newest_output_xml(c.root, time.time() - 900)
        if xml is None:
            continue
        summ = hc.summarize_output(xml)
        if not summ or summ.get("error"):
            continue
        c.log["robot"] = {k: summ.get(k) for k in ("total", "passed", "failed")}
        verified = []
        with hc.Store(c.d) as s:
            s.data["last_plain"] = {"ts": time.time(), "xml": hc.rel(xml, c.root),
                                    **{k: summ.get(k) for k in ("total", "passed", "failed")},
                                    "failures": [{k: f.get(k) for k in ("test", "source", "line", "msg")}
                                                 for f in summ["failures"][:5]]}
            for src, bs in (summ.get("by_source") or {}).items():
                p = Path(src)
                if not p.is_file() or bs["failed"]:
                    continue
                txt = hc.read(p) or ""
                n_tests = _count_tests(txt)
                if n_tests and bs["total"] >= n_tests:
                    s.data.setdefault("verified", {})[str(p.resolve())] = hc.sha(txt)
                    verified.append(hc.rel(p, c.root))
            if summ.get("failed") == 0 and summ.get("total"):
                s.data["last_green_ts"] = time.time()
                if verified:
                    s.data.pop("resource_dirty_ts", None)
        lines = [f"Plain robot run: {summ['total']} tests, {summ['passed']} passed, {summ['failed']} failed "
                 f"({hc.rel(xml, c.root)})."]
        for e in (summ.get("suite_errors") or [])[:2]:
            lines.append(f"  suite {e['type'].lower()} failed: {e['kw']}: {_cut(e['msg'], 200)}")
        doc_items: List[Tuple[str, str]] = []
        groups: Dict[Tuple[str, str], List[Dict[str, Any]]] = {}
        compact = c.agent in COMPACT
        for f in summ["failures"][:8]:
            kw = f.get("kw") or {}
            inner = kw.get("inner") or {}
            where = kw.get("kw", "") + (f" > {inner['kw']}" if inner.get("kw") else "")
            groups.setdefault((where, re.sub(r"\d+ms", "Nms", f.get("msg") or "")[:160]), []).append(f)
        for (where, _m), fs in list(groups.items())[:4]:
            f = fs[0]
            src = hc.rel(Path(f["source"]), c.root) if f.get("source") else "?"
            names = ", ".join(f"'{x['test']}'" for x in fs[:3]) + (" ..." if len(fs) > 3 else "")
            lns = ",".join(str(x.get("line")) for x in fs[:4])
            lines.append(f"  FAIL{f' x{len(fs)}' if len(fs) > 1 else ''} {names} ({src}:{lns}) at [{_cut(where, 60)}]: "
                         f"{_cut(f['msg'], 130 if compact else 200)}")
        for f in summ["failures"][:4]:
            kw = f.get("kw") or {}
            src = hc.rel(Path(f["source"]), c.root) if f.get("source") else "?"
            dk = _deepest(kw)
            if dk and (dk["lib"], dk["kw"]) not in doc_items:
                doc_items.append((dk["lib"], dk["kw"]))
            ln = _loop_note(c, guards.loop_key(src, f.get("test"), (dk or kw).get("kw", "")), True,
                            f"test '{f.get('test')}'", (dk or kw).get("kw", ""), (dk or {}).get("lib"),
                            ((dk or kw).get("args") or [None])[0])
            if ln:
                first.append(ln)
        lines += _failure_docs(c, doc_items)
        if summ["failed"] == 0 and verified:
            lines.append(f"  -> verified: {', '.join(verified)} (green plain run recorded).")
        texts.append("\n".join(lines))
        repro_at = len(texts)
        if summ["failures"] and REPRODUCE:
            f0 = summ["failures"][0]
            src = Path(f0.get("source") or "")
            if src.is_file() and str(src.resolve()).startswith(str(c.root)) and src.suffix == ".robot":
                r = run_live(c, {"op": "hookrun", "path": str(src.resolve()), "mode": "reproduce", "test": f0["test"]},
                             f"robot run (reproducing '{f0['test']}')")
                c.log["reproduced"] = True
                rep = format_run(r, c, head=(
                    f"Reproduced live: '{f0['test']}' re-run from the top in the hook session, stopped at its first "
                    "failure; that page stays open:"), collapse_pass=True, budget=1300)
                if c.agent in COMPACT:    # weak models: the reproduction (recheck, page, NEXT) before the failure list
                    head_line, _, rest = texts[repro_at - 1].partition("\n")
                    texts[repro_at - 1] = head_line
                    texts.append(rep)
                    if rest:
                        texts.append(rest)
                else:
                    texts.append(rep)
    texts = first[:1] + texts
    if not texts:
        return hc.Result()
    c.log["action"] = "context"
    return hc.Result("context", "\n\n".join(texts))


def _after_repl(c: Ctx, cmd: str, inv: "replfmt.Inv") -> hc.Result:
    out = _response_text(c.payload)
    parsed = replfmt.parse_output(out)
    body = replfmt.body_lines(cmd, inv)
    texts: List[str] = []
    first: List[str] = []
    if _flag(c, "card_shown"):           # first REPL/debug command of the session: the format card
        texts.append(replfmt.CARD)
        c.log["card"] = "post"
    with hc.Store(c.d) as s:
        note = s.data.pop("repl_note", None)
    if note:
        texts.append(note)
    c.d.state.mkdir(parents=True, exist_ok=True)
    try:
        (c.d.state / "repl-last.txt").write_text(f"$ {cmd[:4000]}\n\n{out[-20000:]}")
    except OSError:
        pass
    # failing keywords: robot-debug `* exception Owner.Kw (file:line)`, REPL output.xml leaves, `-k` KEYWORD lines
    items: List[Tuple[str, str]] = []
    for e in parsed["exceptions"]:
        if e.get("kw") and (e.get("owner") or "BuiltIn", e["kw"]) not in items:
            items.append((e.get("owner") or "BuiltIn", e["kw"]))
    xml = _repl_output_xml(c, inv)
    if xml is not None:
        for leaf in _xml_fail_leaves(xml):
            if leaf not in items:
                items.append(leaf)
    for f in parsed["fails"]:
        if f.get("kw") and (f.get("owner") or "BuiltIn", f["kw"]) not in items:
            items.append((f.get("owner") or "BuiltIn", f["kw"]))
    nfail = len(parsed["fails"]) + len(parsed["exceptions"])
    c.log["repl_fails"] = nfail
    if nfail:
        lines = [f"robotcode {inv.sub}: {nfail} failure(s)" + (f" ({', '.join(f'{o}.{k}' for o, k in items[:3])})"
                                                                 if items else "") + ":"]
        seen_e = set()
        for e in parsed["exceptions"]:
            k = (e.get("kw"), e.get("loc"))
            if k in seen_e or len(seen_e) >= 2:
                continue
            seen_e.add(k)
            lines.append(f"  * {e.get('owner') or ''}.{e['kw']} at {e.get('loc')}: {_cut(e.get('msg'), 200)}")
        rf = [l for l in out.splitlines() if l.startswith("[rfh2] ") and ("SLOW" in l or "MISSING" in l or "exists now" in l)]
        for l in rf[:2]:
            lines.append("  " + _cut(l, 260))
        if rf:
            c.log["repl_rechecks"] = len(rf)
        for f in parsed["fails"][:3]:
            lines.append(f"  [ FAIL ] {_cut(f['msg'], 200)}")
            if f.get("unknown"):
                near = kwdoc.near_names(c.root, f["unknown"].split("    ")[0])
                lines.append(f"      unknown keyword '{_cut(f['unknown'], 60)}': " + (
                    f"did you mean {' | '.join(near)}" if near else
                    "if it is `Keyword arg` with ONE space, separate with 4 spaces; else grep -i '<words>' .rf/docs/*.md"))
        lines += _failure_docs(c, items)
        lines.append("  The REPL process has exited, so its page is gone (output saved: .rf/state/repl-last.txt). To "
                     "see the page at a failing step, put the lines into a .robot test file: the hooks run them live "
                     "and capture .rf/state/latest/.")
        texts.append("\n".join(lines))
        for o, k in items[:1]:
            ln = _loop_note(c, guards.loop_key("repl", None, k), True, f"REPL step {k}", k, o, None)
            if ln:
                first.append(ln)
    imps = replfmt.imports_in(body)
    if imps:
        recs = kwdoc.lib_docs(c.root, imps, cwd=c.cwd)
        with hc.Store(c.d) as s:
            seen = s.data.setdefault("docs_mentioned", [])
            fresh = [r for r in recs if r["name"] not in seen]
            seen += [r["name"] for r in fresh]
        if fresh:
            c.log["docs_lib"] = [r["name"] for r in fresh]
            texts.append("Keyword docs for the REPL imports: " + ", ".join(r["path"] for r in fresh)
                         + " (one line per keyword; full: <Name>.full.md).")
    for sp in replfmt.saved_files(body, c.cwd):
        st = hc.read(sp) or ""
        if re.search(r"Set (Browser|Selenium) Timeout|Library\s{2,}(Browser|SeleniumLibrary)\s{2,}.*timeout=", st):
            texts.append(f"{hc.rel(sp, c.root)} (from .save) contains a timeout change you typed into the REPL: remove "
                         "it unless the suite really needs it (the plain run must use the normal timeout).")
    texts = first + texts
    if not texts:
        return hc.Result()
    c.log["action"] = "context"
    return hc.Result("context", "\n\n".join(texts))


def _repl_output_xml(c: Ctx, inv: "replfmt.Inv") -> Optional[Path]:
    d = None
    a = inv.args
    for i, x in enumerate(a):
        if x in ("-d", "--outputdir") and i + 1 < len(a):
            d = a[i + 1]
        elif x.startswith("--outputdir="):
            d = x.split("=", 1)[1]
    o = None
    for i, x in enumerate(a):
        if x in ("-o", "--output") and i + 1 < len(a):
            o = a[i + 1]
        elif x.startswith("--output="):
            o = x.split("=", 1)[1]
    base = Path(d) if d else c.root / ".rf" / "out"
    base = base if base.is_absolute() else c.cwd / base
    cands = [Path(o) if o and os.path.isabs(o) else base / (o or "repl-output.xml"), base / "output.xml"]
    for p in cands:
        try:
            if p.is_file() and time.time() - p.stat().st_mtime < 120:
                return p
        except OSError:
            pass
    return None


def _xml_fail_leaves(xml: Path) -> List[Tuple[str, str]]:
    import xml.etree.ElementTree as ET

    out: List[Tuple[str, str]] = []
    try:
        root = ET.parse(str(xml)).getroot()
    except Exception:
        return out
    for kw in root.iter("kw"):
        st = kw.find("status")
        if st is None or st.get("status") != "FAIL":
            continue
        if any((ch.find("status") is not None and ch.find("status").get("status") == "FAIL")
               for ch in kw.findall("kw")):
            continue
        owner = kw.get("owner") or kw.get("library") or "BuiltIn"
        name = kw.get("name") or ""
        if name and (owner, name) not in out:
            out.append((owner, name))
        if len(out) >= 3:
            break
    return out


def _count_tests(text: str) -> int:
    n, inside = 0, False
    for line in text.splitlines():
        if line.startswith("*"):
            inside = bool(hc.TEST_HEADER.match(line))
            continue
        if inside and line and not line[0].isspace() and not line.startswith("#"):
            n += 1
    return n


def on_stop(c: Ctx) -> hc.Result:
    if not (c.d.hook / "session.json").exists():
        return hc.Result()
    texts = collect_pending(c, timeout=min(30.0, c.left(60.0)))
    with hc.Store(c.d) as s:
        edited = dict(s.data.get("edited_tests") or {})
        verified = dict(s.data.get("verified") or {})
        dirty = (s.data.get("resource_dirty_ts") or 0) > (s.data.get("last_green_ts") or 0)
        unver = []
        for p in edited:
            t = hc.read(Path(p))
            if t is None or not hc.is_test_file(Path(p), t):
                continue
            if dirty or verified.get(p) != hc.sha(t):
                unver.append((p, hc.sha(t)))
        if not unver:
            c.log["action"] = "allow"
            return hc.Result()
        sig = hc.sha(json.dumps(sorted(unver)) + str(dirty))
        blocked = s.data.setdefault("stop_blocks", [])
        if c.payload.get("stop_hook_active") or sig in blocked or len(blocked) >= MAX_STOP_BLOCKS:
            c.log["action"] = "allow-loopguard"
            return hc.Result()
        blocked.append(sig)
        last = s.data.get("last_plain") or {}
    files = [hc.rel(Path(p), c.root) for p, _ in unver]
    msg = [f"Robot Framework quality gate: {', '.join(files)} changed since the last green plain robot run "
           f"(or never ran plainly). Run the final proof now: robot -d results {' '.join(files)}"]
    if last.get("failed"):
        msg.append(f"Last plain run: {last.get('failed')} of {last.get('total')} failed:")
        for f in (last.get("failures") or [])[:3]:
            msg.append(f"  '{f.get('test')}': {_cut(f.get('msg') or '', 200)}")
    msg.append("If it fails, fix the test (never delete/skip tests or weaken assertions) and run it again.")
    msg += texts
    c.log["action"] = "block"
    return hc.Result("block", "\n".join(msg))


def on_session_end(c: Ctx) -> hc.Result:
    if not c.d.rf.exists():
        return hc.Result()
    if c.agent == "copilot":    # copilot fires sessionEnd after EVERY run (incl. Stop continuations): keep the
        c.log["action"] = "keep"   # session; the daemons exit when the agent process is gone / idle
        return hc.Result()
    c.log["stopped"] = hc.stop_daemons(c.d, wait=0.3)     # budgets: Claude 1.5 s, Codex <= 3 s -> signal only
    c.log["gen_removed"] = hc.cleanup_gen_files(c.root)
    return hc.Result()


HANDLERS = {"session-start": on_session_start, "pre-tool": on_pre_tool, "post-tool": on_post_tool,
            "stop": on_stop, "session-end": on_session_end, "prompt": on_prompt}


def main(argv: Optional[List[str]] = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    agent = "claude"
    if "--agent" in argv:
        i = argv.index("--agent")
        agent = argv[i + 1] if i + 1 < len(argv) else agent
        del argv[i:i + 2]
    raw = sys.stdin.read() if not sys.stdin.isatty() else ""
    try:
        payload = json.loads(raw) if raw.strip() else {}
    except ValueError:
        payload = {}
    ev_raw = argv[0] if argv else str(payload.get("hook_event_name") or payload.get("hookEventName") or "")
    event = EVENTS.get(ev_raw.replace("_", "").lower(), EVENTS.get(ev_raw.lower(), ev_raw.lower()))
    handler = HANDLERS.get(event)
    if handler is None:
        return 0
    c = Ctx(event, agent, payload)
    if ev_raw.lower().replace("-", "") != event.replace("-", ""):
        c.log["raw_event"] = ev_raw
    out = ""
    try:
        res = handler(c)
        out = hc.render(agent, event, res, payload)
        c.log.setdefault("action", res.kind)
    except Exception as e:
        c.log["error"] = f"{type(e).__name__}: {e}"[:300]
        c.log["tb"] = traceback.format_exc()[-1200:]
    c.log["ms"] = round((time.monotonic() - c.t0) * 1000, 1)
    c.log["out_bytes"] = len(out)
    if os.environ.get("RFH2_HOOK_LOG") or c.d.rf.exists():
        if not os.environ.get("RFH2_HOOK_LOG"):
            c.d.hook.mkdir(parents=True, exist_ok=True)
        hc.log_event(c.d, c.log)
    if out:
        sys.stdout.write(out + "\n")
        sys.stdout.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main())
