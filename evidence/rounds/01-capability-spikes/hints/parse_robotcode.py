"""Parser spike: extract (keyword, owner, args, error) for failing steps from robotcode output.

Four sources, from least to most structured:

  parse_plain(text, input_lines)   plain `robotcode repl --plain` output. It has no step
                                   boundaries, so FAIL blocks are correlated back to the
                                   agent's own input lines by evidence scoring.
  parse_k(text)                    `robotcode repl --plain -k` output: `KEYWORD Owner.Name  a1  a2`
                                   header lines give boundaries, keyword and raw args.
  parse_results_json(obj)          `robotcode --format json results log -o output.xml`
  parse_replserver(cells)          `robotcode repl-server` executeCell responses (JSON tree)

Every parser returns a list of Step dicts:
  {"keyword", "owner", "args", "status", "error", "line_index", "confidence", "source"}
Only FAIL steps are returned by the text parsers (parse_k returns all, with status).
Pure stdlib; no robotcode / rf-mcp import.
"""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional

LEVEL_RE = re.compile(r"^(?P<indent>\s*)\[ (?P<level>INFO|WARN|FAIL|ERROR|DEBUG|TRACE|SKIP) \] ?(?P<msg>.*)$")
KEYWORD_RE = re.compile(r"^(?P<indent>\s*)KEYWORD (?P<rest>.*)$")
CELL_SPLIT_RE = re.compile(r" {2,}|\t+")
ASSIGN_RE = re.compile(r"^[$&@]\{[^}]+\}\s*=?$")
# Lines that are allowed to continue a FAIL message even when not indented.
CONT_ALLOW_RE = re.compile(r"^(Call log:|Traceback \(most recent call last\):|PYTHONPATH:|\s*$)")


def _norm(s: str) -> str:
    return re.sub(r"[\s_]+", "", s or "").lower()


# ---------------------------------------------------------------------------
# input-line handling (the agent knows what it typed)
# ---------------------------------------------------------------------------

def split_line(line: str) -> Dict[str, Any]:
    """Split one RF step line into assign / keyword / args (REPL cell syntax)."""
    cells = [c for c in CELL_SPLIT_RE.split(line.strip()) if c != ""]
    assign = []
    while cells and ASSIGN_RE.match(cells[0]):
        assign.append(cells.pop(0))
    kw = cells[0] if cells else ""
    return {"assign": assign, "keyword": kw, "args": cells[1:]}


def executable_lines(input_lines: List[str]) -> List[Dict[str, Any]]:
    out = []
    for i, raw in enumerate(input_lines):
        s = raw.strip()
        if not s or s.startswith("#") or s.startswith("."):
            continue
        d = split_line(raw)
        d["line_index"] = i
        d["raw"] = raw
        out.append(d)
    return out


# ---------------------------------------------------------------------------
# message blocks
# ---------------------------------------------------------------------------

def _blocks(text: str) -> List[Dict[str, Any]]:
    """Split output into KEYWORD headers and message blocks (level + multi-line text)."""
    blocks: List[Dict[str, Any]] = []
    cur: Optional[Dict[str, Any]] = None
    for line in text.splitlines():
        km = KEYWORD_RE.match(line)
        if km:
            cur = None
            blocks.append({"kind": "keyword", "indent": len(km.group("indent")), "rest": km.group("rest")})
            continue
        lm = LEVEL_RE.match(line)
        if lm:
            cur = {"kind": "msg", "level": lm.group("level"), "indent": len(lm.group("indent")),
                   "lines": [lm.group("msg")]}
            blocks.append(cur)
            continue
        if cur is not None and cur["level"] in ("FAIL", "ERROR", "WARN"):
            # continuation of a multi-line failure message?
            if line.startswith(" ") or CONT_ALLOW_RE.match(line):
                cur["lines"].append(line)
                continue
            cur = None
        elif cur is not None:
            # INFO continuation only when it cannot be console output: indented lines, or
            # the "Argument types are:\n<class 'int'>\n<class 'str'>" shape
            if line.startswith(" ") or (cur["lines"][0].rstrip().endswith(":") and line.startswith("<")):
                cur["lines"].append(line)
                continue
            cur = None
        blocks.append({"kind": "console", "text": line})
    for b in blocks:
        if b["kind"] == "msg":
            b["text"] = "\n".join(b["lines"]).rstrip()
    return blocks


# ---------------------------------------------------------------------------
# -k parser
# ---------------------------------------------------------------------------

def _split_kw_header(rest: str) -> Dict[str, Any]:
    cells = rest.split("  ")
    full = cells[0]
    args = [c for c in cells[1:] if c != ""]
    if full.startswith("None."):
        owner, name = None, full[len("None."):]
    elif "." in full:
        owner, name = full.rsplit(".", 1)
    else:
        owner, name = None, full
    return {"owner": owner, "keyword": name, "full_name": full, "args": args}


def parse_k(text: str) -> List[Dict[str, Any]]:
    steps: List[Dict[str, Any]] = []
    stack: List[Dict[str, Any]] = []
    for b in _blocks(text):
        if b["kind"] == "keyword":
            hdr = _split_kw_header(b["rest"])
            step = {**hdr, "status": "PASS", "error": "", "depth": b["indent"] // 2,
                    "confidence": "high", "source": "k", "line_index": None, "messages": []}
            steps.append(step)
            while stack and stack[-1]["depth"] >= step["depth"]:
                stack.pop()
            step["parent"] = stack[-1] if stack else None
            stack.append(step)
        elif b["kind"] == "msg" and stack:
            # message indent = (depth+1)*2
            depth = max(0, b["indent"] // 2 - 1)
            owner = next((s for s in reversed(stack) if s["depth"] <= depth), stack[-1])
            owner["messages"].append((b["level"], b["text"]))
            if b["level"] == "FAIL":
                owner["status"] = "FAIL"
                owner["error"] = b["text"]
                # -k prints a nested failure only once, at the innermost keyword: propagate it to
                # the enclosing (top-level) step unless an ancestor swallows errors
                par = owner.get("parent")
                while par is not None and _norm(par["keyword"]) not in _SWALLOW:
                    if par["status"] != "FAIL":
                        par["status"], par["error"] = "FAIL", b["text"]
                    par = par.get("parent")
    for st in steps:
        st.pop("parent", None)
    return steps


_SWALLOW = {_norm(k) for k in ("Run Keyword And Ignore Error", "Run Keyword And Return Status",
                                "Run Keyword And Expect Error", "Run Keyword And Warn On Failure",
                                "Wait Until Keyword Succeeds", "TRY")}


def top_failures_k(text: str) -> List[Dict[str, Any]]:
    return [s for s in parse_k(text) if s["status"] == "FAIL" and s["depth"] == 0]


# ---------------------------------------------------------------------------
# plain parser + correlation to input lines
# ---------------------------------------------------------------------------

_EVIDENCE = [
    # (regex on error, group -> what it identifies)
    (re.compile(r"No keyword with name '([^']+)' found"), "keyword"),
    (re.compile(r"Keyword '(?:[^'.]+\.)?([^']+)' (?:expected|missing value|got|argument)"), "keyword"),
    (re.compile(r"Importing library '([^']+)' failed"), "import"),
    (re.compile(r"Evaluating expression ['\"](.+?)['\"] failed"), "expr"),
    (re.compile(r"Resolving variable '(\$\{[^']+\})' failed"), "var"),
    (re.compile(r"Variable '(\$\{[^']+\})' not found"), "var"),
    (re.compile(r"locator\('(.+?)'\)"), "arg"),
    (re.compile(r"while parsing (?:css )?selector \"?(.+?)\"?(?:\. |$)", re.M), "arg"),
    (re.compile(r"waiting for (?!locator)(.+)$", re.M), "arg"),
    (re.compile(r"Argument '[^']+' got value '(.+?)'"), "arg"),
    (re.compile(r"Keyword argument '([^']+)' is not supported"), "argprefix"),
    (re.compile(r"(?:for url|Url): https?://[^/\s]+(/\S*)"), "argprefix"),
    (re.compile(r"Invalid URL '([^']+)'"), "arg"),
    (re.compile(r"alias '([^']+)'"), "arg"),
    (re.compile(r"unexpected keyword argument '([^']+)'"), "argprefix"),
    (re.compile(r"navigating to \"([^\"]+)\""), "arg"),
    (re.compile(r"Dictionary does not contain key '([^']+)'"), "arg"),
    (re.compile(r"old FOR loop syntax"), "for"),
]


def _score_line(err: str, line: Dict[str, Any]) -> int:
    score = 0
    kw = _norm(line["keyword"])
    kw_base = _norm(line["keyword"].split(".")[-1])
    args = line["args"]
    for rx, kind in _EVIDENCE:
        for m in rx.finditer(err):
            val = m.group(1) if m.groups() else ""
            if kind == "keyword" and (_norm(val) == kw or _norm(val.split(".")[-1]) == kw_base):
                score += 10
            elif kind == "import" and kw_base == "importlibrary" and args and args[0].endswith(val.split("/")[-1]):
                score += 10
            elif kind == "expr" and kw_base == "evaluate" and args:
                # expression is shown AFTER variable substitution: compare non-variable residue
                residue = re.sub(r"[$&@%]\{[^}]*\}", "", args[0]).strip()
                if residue and residue in val:
                    score += 8
            elif kind == "var" and any(val in a for a in [line["raw"]]):
                score += 8
            elif kind == "arg" and any(val.strip() == a or val.strip() in a for a in args):
                score += 6
            elif kind == "argprefix" and any(a.startswith(val) or val in a for a in args):
                score += 6
            elif kind == "for" and line["keyword"].upper().lstrip(":") == "FOR":
                score += 10
    return score


def parse_plain(text: str, input_lines: Optional[List[str]] = None) -> List[Dict[str, Any]]:
    fails = [b for b in _blocks(text) if b["kind"] == "msg" and b["level"] == "FAIL" and b["indent"] == 0]
    lines = executable_lines(input_lines or [])
    out: List[Dict[str, Any]] = []
    min_idx = -1
    for f in fails:
        err = f["text"]
        step = {"keyword": None, "owner": None, "args": None, "status": "FAIL", "error": err,
                "line_index": None, "confidence": "none", "source": "plain"}
        if lines:
            cands = [ln for ln in lines if ln["line_index"] > min_idx]
            scored = sorted(((_score_line(err, ln), ln["line_index"], ln) for ln in cands),
                            key=lambda t: (-t[0], -t[1]))
            if scored and scored[0][0] > 0:
                best = scored[0][2]
                step["confidence"] = "high" if scored[0][0] >= 8 else "medium"
            elif cands:
                # no evidence: fall back to the LAST executable line (typical "mistake is the
                # last thing I typed") - low confidence
                best = cands[-1]
                step["confidence"] = "low"
            else:
                best = None
            if best is not None:
                step.update(keyword=best["keyword"], args=best["args"], line_index=best["line_index"])
                min_idx = best["line_index"]
        out.append(step)
    return out


# --- v2: generic message-family evidence + positional anchors -----------------

_FAMILY = [
    # (regex on error, predicate on normalised keyword base name, score)
    (re.compile(r" != |should be '.*' \(|should (?:not )?be equal", re.I), lambda k: "shouldbe" in k or k.startswith("get"), 3),
    (re.compile(r"does not contain|should (?:not )?contain", re.I), lambda k: "contain" in k, 3),
    (re.compile(r"HTTPError|Expected status|Client Error|Server Error", re.I),
     lambda k: k.endswith("onsession") or k in ("get", "post", "put", "patch", "delete", "head", "options"), 3),
    (re.compile(r"locator\.|strict mode violation", re.I),
     lambda k: k not in _NON_ELEMENT_KWS and not k.startswith("should"), 2),
    (re.compile(r"page\.goto|navigating to", re.I), lambda k: k in ("newpage", "goto"), 3),
]
_NON_ELEMENT_KWS = {"log", "logtoconsole", "setvariable", "evaluate", "importlibrary", "importresource",
                    "newbrowser", "newcontext", "newpage", "goto", "closebrowser", "closepage", "sleep"}
_IMPORT_KWS = {"importlibrary", "importresource", "importvariables"}
_IMPORT_ERR_RE = re.compile(r"Importing (?:library|resource|variable file)|Import Library", re.I)
_VAR_RE = re.compile(r"[$&@%]\{[^}]*\}")
ASSIGN_INFO_RE = re.compile(r"^([$&@]\{[^}]+\}) = ")
BROWSER_ACTION_INFO_RE = re.compile(r"^(?:Clicks|Fills|Types|Hovers|Checks|Unchecks|Focuses|Selects|Presses keys to) (?:the )?(?:element|text|field)?.*?'(.+?)'")


def _score_line_v2(err: str, line: Dict[str, Any]) -> int:
    score = _score_line(err, line)
    kw_base = _norm(line["keyword"].split(".")[-1])
    for rx, pred, s in _FAMILY:
        if rx.search(err) and pred(kw_base):
            score += s
    # literal (non-variable) argument text echoed in the message
    for a in line["args"]:
        lit = _VAR_RE.sub("", a).strip()
        if len(lit) >= 3 and "=" not in lit[:1] and lit in err:
            score += 2
    return score


def parse_plain_v2(text: str, input_lines: Optional[List[str]] = None) -> List[Dict[str, Any]]:
    """Like parse_plain, plus anchors from non-FAIL output that pin execution position:
    - `[ INFO ] ${x} = ...`  -> the line assigning ${x} PASSED; later failures are after it
    - Browser action INFO (`Clicks the element 'X'.`) -> the next FAIL is probably that line
    - console output equal to a `Log To Console` literal -> that line passed
    Ties are broken towards the EARLIEST candidate after the anchor (sequential execution).
    """
    blocks = _blocks(text)
    lines = executable_lines(input_lines or [])
    out: List[Dict[str, Any]] = []
    min_idx = -1
    hint_idx: Optional[int] = None

    def first_after(pred):
        return next((ln for ln in lines if ln["line_index"] > min_idx and pred(ln)), None)

    for b in blocks:
        if b["kind"] == "msg" and b["level"] == "INFO" and b["indent"] == 0:
            am = ASSIGN_INFO_RE.match(b["text"])
            if am:
                name = am.group(1)[2:-1]
                ln = first_after(lambda ln, n=name: any(a.strip("=").strip()[2:-1] == n for a in ln["assign"]))
                if ln:
                    min_idx, hint_idx = ln["line_index"], None
                continue
            bm = BROWSER_ACTION_INFO_RE.match(b["text"])
            if bm:
                sel = bm.group(1)
                ln = first_after(lambda ln, s=sel: bool(ln["args"]) and ln["args"][0] == s)
                if ln:
                    # this keyword STARTED; everything before it passed
                    min_idx, hint_idx = ln["line_index"] - 1, ln["line_index"]
            continue
        if b["kind"] == "console":
            txt = b["text"].strip()
            if txt:
                ln = first_after(lambda ln, t=txt: _norm(ln["keyword"]) == "logtoconsole" and ln["args"]
                                 and _VAR_RE.sub("", ln["args"][0]).strip() != ""
                                 and all(part in t for part in _VAR_RE.split(ln["args"][0]) if part.strip()))
                if ln:
                    min_idx, hint_idx = ln["line_index"], None
            continue
        if not (b["kind"] == "msg" and b["level"] == "FAIL" and b["indent"] == 0):
            continue
        err = b["text"]
        step = {"keyword": None, "owner": None, "args": None, "status": "FAIL", "error": err,
                "line_index": None, "confidence": "none", "source": "plain_v2"}
        cands = [ln for ln in lines if ln["line_index"] > min_idx]
        if not _IMPORT_ERR_RE.search(err):
            # an import line that already executed is not a plausible source of a keyword error
            cands = [ln for ln in cands if _norm(ln["keyword"]) not in _IMPORT_KWS] or cands
        if cands:
            scored = []
            for ln in cands:
                s = _score_line_v2(err, ln)
                if hint_idx is not None and ln["line_index"] == hint_idx:
                    s += 3
                scored.append((s, ln["line_index"], ln))
            scored.sort(key=lambda t: (-t[0], t[1]))
            top = scored[0]
            if top[0] > 0:
                best = top[2]
                step["confidence"] = "high" if top[0] >= 8 else "medium"
            else:
                best = cands[0]  # sequential: the next un-anchored line
                step["confidence"] = "low"
            step.update(keyword=best["keyword"], args=best["args"], line_index=best["line_index"])
            min_idx, hint_idx = best["line_index"], None
        out.append(step)
    return out


# ---------------------------------------------------------------------------
# structured sources
# ---------------------------------------------------------------------------

def _split_full(full: str) -> Dict[str, Any]:
    if "." in full:
        owner, name = full.rsplit(".", 1)
        return {"owner": owner, "keyword": name}
    return {"owner": None, "keyword": full}


def parse_results_json(obj: Dict[str, Any]) -> List[Dict[str, Any]]:
    out = []
    for t in obj.get("tests", []):
        for i, kw in enumerate(t.get("body", [])):
            if kw.get("type") != "KEYWORD" or kw.get("status") != "FAIL":
                continue
            out.append({**_split_full(kw.get("name", "")), "args": kw.get("args", []), "status": "FAIL",
                        "error": (kw.get("message") or "").rstrip(), "line_index": i,
                        "confidence": "high", "source": "results_json"})
    return out


def parse_replserver(cells: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out = []
    for i, c in enumerate(cells):
        resp = (c.get("response") or {}).get("result") or {}
        if not isinstance(resp, dict):  # e.g. the `initialize` reply is a plain string
            continue
        for item in resp.get("items") or []:
            if item.get("mime") == "x-application/robotframework-repl-log":
                tree = json.loads(item["data"])
                for kw in tree.get("items", []):
                    if kw.get("node_type") == "keyword" and kw.get("status") == "FAIL":
                        out.append({"keyword": kw.get("name"), "owner": kw.get("owner") or None,
                                    "args": kw.get("args", []), "status": "FAIL",
                                    "error": (kw.get("message") or "").rstrip(),
                                    "line_index": i - 1, "confidence": "high", "source": "replserver",
                                    "source_line": c.get("source")})
            elif item.get("mime") == "application/vnd.code.notebook.stderr":
                out.append({"keyword": None, "owner": None, "args": None, "status": "FAIL",
                            "error": item.get("data", ""), "line_index": i - 1, "confidence": "high",
                            "source": "replserver-stderr", "source_line": c.get("source")})
    return out


if __name__ == "__main__":
    import sys
    txt = open(sys.argv[1]).read()
    inp = open(sys.argv[2]).read().splitlines() if len(sys.argv) > 2 else None
    print(json.dumps({"k": top_failures_k(txt), "plain": parse_plain(txt, inp)}, indent=2, default=str))


# ---------------------------------------------------------------------------
# robot-debug (`robotcode robot-debug --plain`, default break-on-exception)
# ---------------------------------------------------------------------------

DEBUG_EXC_RE = re.compile(r"^\* exception\s+(?P<full>\S.*?)\s+\((?P<file>[^()]+?):(?P<line>\d+)\)\s+— Keyword failed: (?P<msg>.*)$")


def parse_robot_debug(text: str, root: str = ".") -> List[Dict[str, Any]]:
    """`* exception  Owner.Kw  (file:line)  — Keyword failed: msg` + the following `| FAIL |` full message.
    Args are recovered from the source line (the agent has the file)."""
    import os
    out: List[Dict[str, Any]] = []
    lines = text.splitlines()
    for i, ln in enumerate(lines):
        m = DEBUG_EXC_RE.match(ln)
        if not m:
            continue
        full = m.group("full")
        owner, name = (full.rsplit(".", 1) if "." in full else (None, full))
        path = m.group("file") if os.path.isabs(m.group("file")) else os.path.join(root, m.group("file"))
        args: Optional[List[str]] = None
        try:
            src = open(path).read().splitlines()[int(m.group("line")) - 1]
            d = split_line(src)
            args = d["args"]
        except Exception:  # noqa: BLE001
            pass
        # the full (untruncated) message follows the next "| FAIL |" marker
        err = m.group("msg")
        for j in range(i + 1, min(i + 60, len(lines))):
            if lines[j].rstrip().endswith("| FAIL |"):
                msg_lines = []
                for k in range(j + 1, len(lines)):
                    if lines[k].startswith("----") or lines[k].startswith("===="):
                        break
                    msg_lines.append(lines[k])
                if msg_lines:
                    err = "\n".join(msg_lines).strip()
                break
        out.append({"keyword": name, "owner": owner, "args": args, "status": "FAIL", "error": err,
                    "file": m.group("file"), "line": int(m.group("line")), "confidence": "high",
                    "source": "robot-debug"})
    return out
