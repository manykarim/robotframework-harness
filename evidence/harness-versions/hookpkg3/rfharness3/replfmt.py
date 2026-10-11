"""REPL / debugger command format enforcement (PreToolUse on Bash) + REPL/debug output parsing (PostToolUse).
STDLIB ONLY (imported by hook.py, which runs as `python -S`).

Commands handled: `robotcode [global opts] repl|shell|robot-debug|run-debug|repl-server ...` (also via a path,
`uv run`, `timeout N`, after `cd x &&`, piped `printf ... |`). Rules: the 40 verified rules of the round-5 research
(data/repl_format_rules.json, robotcode 2.7 / RF 7.3+7.5 / Browser 19.12+20.5) -- body rules vendored from its
prototype linter (repl_lint.py, 34/34) -- plus agent-specific ones:
  command  --plain (no PTY hang), --no-history, -d .rf/out (created; a missing -d costs ~16 s per Browser keyword),
           -o repl-output.xml (REPL: failure details for the hook), 2>&1 ([ FAIL ] goes to stderr), global options
           (-p/-c/-r) moved before the subcommand, unquoted heredoc -> quoted when every `$` is `${` (else deny),
           double-quoted echo with ${ -> deny, statement as positional argument -> deny, interactive REPL without
           input -> deny for agents that cannot type into a running process (claude, opencode), repl-server -> deny
  body     `...` folded into the previous line, blank lines inside FOR/IF dropped, unclosed block -> deny, old :FOR ->
           deny, markdown fences / *** Settings *** / [Tags] lines dropped, *** Keywords *** -> deny, bare ${var} ->
           Log To Console, CRLF, `quit` -> .exit, quotes around .kw/.doc/.break names removed, single-space separator
           split when the longest word prefix is a known keyword, robot-debug: no FOR/WHILE/TRY, Library -> Import
           Library; REPL bodies end with .exit (robot-debug: EOF = continue, nothing appended)
  REPL-only short element timeout: ROBOT_OPTIONS="--listener <pkg>/rfh3_repl_listener.py:..." (inert under robot /
           robot-debug; nothing is typed into the session, so `.save` never copies it).
rewrite() -> (new_command, fixes, deny_reason, warnings, inv).
"""
from __future__ import annotations

import json
import os
import re
import shlex
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

DATA = Path(__file__).resolve().parent / "data"
LISTENER = Path(__file__).resolve().parent / "rfh3_repl_listener.py"
SUBS = ("repl-server", "robot-debug", "run-debug", "repl", "shell")
DEBUG_SUBS = ("robot-debug", "run-debug")
_RC = re.compile(r"(?:^|(?<=[\s;&|(`'\"]))((?:[\w./~-]*/)?robotcode)((?:\s+(?!(?:repl-server|robot-debug|run-debug|"
                 r"repl|shell)\b)-{1,2}[\w-]+(?:[ =](?!-)(?!(?:repl-server|robot-debug|run-debug|repl|shell)\b)\S+)?)*)"
                 r"\s+(repl-server|robot-debug|run-debug|repl|shell)(?=\s|$|[;&|)<>])")
_HEREDOC = re.compile(r"<<(-?)\s*(?:'([^']+)'|\"([^\"]+)\"|\\?([A-Za-z_][\w]*))")
SHELL_OPS = re.compile(r"\s(?:\d?>>?|&>|<<?-?|\||&&|;|&(?!\d))")
SEP = re.compile(r"  +|\t")
OPENERS = {"FOR", "WHILE", "IF", "TRY", "GROUP"}
PAGE_KW = re.compile(r"^(?:[$@&]\{[^}]+\}=?\s{2,})*(Click|Fill Text|Type Text|Get Text|Get Element|Wait For|Check Checkbox|"
                     r"Select Options By|Press Keys|Get Url|Get Title|Hover|Input Text|Click Element|Click Button|"
                     r"GET On Session|POST On Session|Go To|Take Screenshot|Get Aria Snapshot)\b", re.I)
SETUP_KW = re.compile(r"^(?:Import Library|Library|New Browser|New Page|New Context|Open Browser|Create Session|"
                      r"Import Resource|Resource)\b", re.I)

try:
    RULES = json.loads((DATA / "repl_format_rules.json").read_text())
    RULE_MSG = {r["id"]: r.get("message", "") for r in RULES.get("rules", [])}
except (OSError, ValueError):
    RULES, RULE_MSG = {}, {}
try:
    _KWC = json.loads((DATA / "kwnames_cache.json").read_text())
except (OSError, ValueError):
    _KWC = {}

CARD = """RF REPL format (hook card):
robotcode repl --plain --no-history -d .rf/out <<'RF' 2>&1
Library    Browser
New Browser    chromium    headless=True
New Page    file:///abs/path/page.html
${t}=    Get Title
RF
- Quote the heredoc ('RF') or the shell eats ${vars}. 2>&1: [ FAIL ] goes to stderr. Exit code is always 0.
- One statement per line, 4 spaces between cells. No `...` lines: keep all args on one line.
- FOR/IF/WHILE/TRY end with END, no blank line inside; unclosed blocks run nothing.
- No *** sections ***, test names, [Tags]/[Setup], keyword definitions (use Import Resource).
- Only assigned values print. A failure does not stop later lines: fix the first FAIL.
- Each call is a new session; its page is gone after exit (lines in a .robot test run live via hooks).
- .kw <name or text> docs/search, .vars --user, .exit
robotcode robot-debug --plain -d .rf/out x.robot <<'RF' 2>&1 pauses at the first failure:
.where .pp ${v} .s .n .c; one keyword per line, no FOR. .break Kw Name or .break x.robot:12 (no quotes). EOF = continue."""


class Inv:
    """one robotcode REPL/debugger invocation inside a shell command."""

    def __init__(self) -> None:
        self.line_idx = 0
        self.sub = ""
        self.exe_start = 0         # offset of the robotcode token in its line
        self.args_start = 0        # offset right after the subcommand
        self.args_end = 0          # offset where the robotcode args end (first shell operator)
        self.args: List[str] = []
        self.glob = ""             # global options between `robotcode` and the subcommand
        self.heredoc: Optional[Dict[str, Any]] = None
        self.piped = False
        self.redirect_in = False
        self.files: List[str] = []


def find(cmd: str) -> Optional[Inv]:
    if not cmd or "robotcode" not in cmd:
        return None
    lines = cmd.split("\n")
    for i, line in enumerate(lines):
        m = _RC.search(line)
        if not m:
            continue
        inv = Inv()
        inv.line_idx, inv.sub = i, m.group(3)
        inv.exe_start = m.start(1)
        inv.glob = m.group(2) or ""
        inv.args_start = m.end(3)
        rest = line[inv.args_start:]
        op = SHELL_OPS.search(rest)
        inv.args_end = inv.args_start + (op.start() if op else len(rest))
        try:
            inv.args = shlex.split(line[inv.args_start:inv.args_end])
        except ValueError:
            inv.args = line[inv.args_start:inv.args_end].split()
        before = line[:m.start(1)]
        inv.piped = bool(re.search(r"\|\s*(?:[\w./~-]*/)?(?:uv\s+run\s+|timeout\s+\d+\S*\s+|env\s+\S+=\S+\s+|"
                                   r"[A-Z_]+=\S+\s+)*$", before.rstrip()) or re.search(r"\|\s*$", before))
        after = line[inv.args_end:]
        inv.redirect_in = bool(re.search(r"(?<![<\d])<(?!<)\s*\S", after))
        hd = _HEREDOC.search(after)
        if hd:
            delim = hd.group(2) or hd.group(3) or hd.group(4)
            quoted = bool(hd.group(2) or hd.group(3) or (hd.group(0).find("\\") >= 0))
            dash = hd.group(1) == "-"
            end = None
            for j in range(i + 1, len(lines)):
                cand = lines[j].lstrip("\t") if dash else lines[j]
                if cand.rstrip() == delim:
                    end = j
                    break
            inv.heredoc = {"quoted": quoted, "delim": delim, "dash": dash, "start": i + 1,
                           "end": end if end is not None else len(lines), "closed": end is not None,
                           "op_start": inv.args_end + hd.start(), "op_end": inv.args_end + hd.end()}
        inv.files = [a for a in inv.args if not a.startswith("-") and a.endswith((".robot", ".resource", ".txt"))]
        return inv
    return None


def body_lines(cmd: str, inv: Inv) -> List[str]:
    if not inv.heredoc:
        return []
    lines = cmd.split("\n")
    return lines[inv.heredoc["start"]:inv.heredoc["end"]]


def _has_opt(args: List[str], *names: str) -> bool:
    return any(a in names or any(a.startswith(n + "=") for n in names if n.startswith("--")) for a in args)


_KW_LINE = re.compile(r"^([A-Z][\w ]*?)\(")


def known_keywords(docs_dir: Optional[Path]) -> Dict[str, str]:
    """normalized -> real keyword name: compact docs (.rf/docs/*.md) + the research name cache."""
    out: Dict[str, str] = {}
    for names in _KWC.values():
        for n in names:
            out[re.sub(r"[\s_]", "", n.lower())] = n
    if docs_dir and docs_dir.is_dir():
        for f in docs_dir.glob("*.md"):
            if f.name.endswith(".full.md"):
                continue
            try:
                for line in f.read_text(errors="replace").splitlines():
                    m = _KW_LINE.match(line)
                    if m:
                        out[re.sub(r"[\s_]", "", m.group(1).strip().lower())] = m.group(1).strip()
            except OSError:
                pass
    return out


# ------------------------------------------------------------------------------------------------ body linter
def _first_cell(line: str) -> str:
    st = line.strip()
    return SEP.split(st, maxsplit=1)[0].upper() if st else ""


def _opens_block(line: str) -> bool:
    cells = [c for c in SEP.split(line.strip()) if c]
    if not cells:
        return False
    head = cells[0].upper()
    if head == "IF":                      # inline IF (IF  cond  Keyword ...) needs no END
        return len(cells) <= 2
    return head in OPENERS


def _fix_single_space(line: str, known: Dict[str, str]) -> Optional[str]:
    """I01: `Kw Name arg` -> `Kw Name    arg` when a known keyword is the longest word prefix."""
    s = line.strip()
    if not s or "\t" in s or "  " in s or not known:
        return None
    if s.startswith(("$", "@", "&")):
        m = re.match(r"^([$@&]\{[^}]+\})\s?=?\s(\S.*)$", s)
        if not m:
            return None
        rest = _fix_single_space(m.group(2), known)
        return f"{m.group(1)}=    {rest if rest else m.group(2)}"
    if s.startswith((".", "#", "*", "[", "`")):
        return None
    words = s.split(" ")
    if len(words) < 2 or words[0].upper() in OPENERS | {"END", "ELSE", "EXCEPT", "FINALLY", "VAR", "RETURN"}:
        return None
    if re.sub(r"[\s_]", "", s.lower()) in known:
        return None
    for i in range(len(words) - 1, 0, -1):
        key = re.sub(r"[\s_]", "", " ".join(words[:i]).lower())
        if key in known:
            return known[key] + "    " + "    ".join(words[i:])
    return None


def lint_body(lines: List[str], debug: bool, known: Dict[str, str]) -> Tuple[List[str], List[str], List[str], bool]:
    """-> (new lines, messages, fired rule ids, deny)"""
    out: List[str] = []
    msgs: List[str] = []
    fired: List[str] = []
    deny = False
    depth = 0
    for raw in lines:
        line = raw.rstrip("\r")
        if line != raw:
            fired.append("I12_crlf")
        st = line.strip()
        if re.match(r"^(```|~~~)", st):
            fired.append("I07_markdown_fences")
            continue
        m = re.match(r"^\*{3}\s*(Settings|Variables|Test Cases|Tasks|Keywords|Comments)\s*\*{3}", st, re.I)
        if m:
            fired.append("I08_sections_and_definitions")
            if m.group(1).lower() == "keywords":
                deny = True
                msgs.append("The REPL cannot define keywords: put them in a .resource file and "
                            "`Import Resource    path.resource`.")
            continue
        if re.match(r"^\[(Tags|Documentation|Setup|Teardown|Timeout|Template|Arguments|Return)\]", st):
            fired.append("I09_test_settings_ignored")
            if st.startswith(("[Setup]", "[Teardown]")):
                msgs.append(f"`{st.split(']')[0]}]` lines are ignored in the REPL; call the keyword directly.")
            continue
        if re.match(r"^(:FOR\b|\\\s{2,})", st):
            deny = True
            fired.append("I06_old_for_syntax")
            msgs.append("Old :FOR syntax: use FOR ... END.")
            out.append(line)
            continue
        if re.match(r"^\.\.\.(\s{2,}|\t|$)", st) and out:
            j = len(out) - 1
            while j >= 0 and not out[j].strip():
                j -= 1
            tail = SEP.split(st, maxsplit=1)[1] if SEP.search(st) else ""
            if j >= 0 and tail:
                out[j] = out[j].rstrip() + "    " + tail
            fired.append("I03_no_continuation_on_stdin")
            continue
        if not st:
            if depth > 0:
                fired.append("I04_blank_line_inside_block")
                continue
            out.append(line)
            continue
        if re.match(r"^(quit|\.q|:q|exit\(\)|\.e)$", st):
            fired.append("I15_exit_words")
            out.append(".exit")
            continue
        m = re.match(r"^\.(kw|doc|break|b|tbreak)\s+([\"'])(.*?)\2(\s*,.*)?$", st)
        if m:
            fired.append("I16_dot_commands")
            out.append(f".{m.group(1)} {m.group(3)}{m.group(4) or ''}")
            continue
        if re.match(r"^[$@&]\{[^}]+\}(\[[^\]]*\])*$", st):
            fired.append("I10_bare_variable_line")
            out.append((".pp " if debug else "Log To Console    ") + st)
            continue
        if debug:
            if re.match(r"^(FOR|WHILE|TRY|GROUP)\b", st) or (st.upper().startswith("IF") and _opens_block(st)):
                deny = True
                fired.append("D02_rdb_single_lines")
            mm = re.match(r"^(Library|Resource|Variables)(\s{2,}|\t)(.*)$", st)
            if mm:
                fired.append("D03_rdb_import_alias")
                out.append(f"Import {mm.group(1)}    {mm.group(3)}")
                continue
        if re.match(r"^(?:[$@&]\{[^}]+\}=?\s{2,})*Run Keyword (If|Unless)\b", st):
            fired.append("I13_run_keyword_if")
        if not st.startswith((".", "#")):
            fixed = _fix_single_space(st, known)
            if fixed:
                fired.append("I01_single_space_separator")
                line = line[: len(line) - len(line.lstrip())] + fixed
                st = fixed
            cells = [c for c in SEP.split(st) if c]
            while cells and re.match(r"^[$@&]\{[^}]+\}\s*=?$", cells[0]):
                cells = cells[1:]
            if (len(cells) > 2 and any(re.sub(r"[\s_]", "", c.lower()) in known for c in cells[1:])
                    and cells[0].upper() not in OPENERS | {"VAR"}
                    and not re.search(r"Keyword|Promise To|^IF$|^ELSE", cells[0], re.I)):
                fired.append("I11_one_statement_per_line")
            if re.match(r"^(?:[$@&]\{[^}]+\}=?\s{2,})?(Get Aria Snapshot|Get Page Source|Get Source)\b", st):
                fired.append("I20_big_values_flood_stdout")
        if _opens_block(st):
            depth += 1
        elif _first_cell(st) == "END":
            depth = max(0, depth - 1)
        out.append(line)
    if depth > 0:
        deny = True
        fired.append("I05_unclosed_block")
        msgs.append("Unclosed FOR/IF/WHILE/TRY/GROUP: add END (an unclosed block runs nothing, silently).")
    return out, msgs, list(dict.fromkeys(fired)), deny


_FIX_TEXT = {"I01_single_space_separator": "single-space separators -> 4 spaces",
             "I03_no_continuation_on_stdin": "`...` lines folded into one statement",
             "I04_blank_line_inside_block": "blank lines inside a block removed",
             "I07_markdown_fences": "markdown fences removed", "I08_sections_and_definitions": "*** section *** headers removed",
             "I09_test_settings_ignored": "[Setting] lines removed", "I10_bare_variable_line": "bare ${var} -> Log To Console",
             "I12_crlf": "CRLF -> LF", "I15_exit_words": "quit -> .exit", "I16_dot_commands": "quotes around a dot-command name removed",
             "D03_rdb_import_alias": "Library -> Import Library (debug prompt)"}
_WARN_IDS = ("I11_one_statement_per_line", "I13_run_keyword_if", "I20_big_values_flood_stdout")


def _segment_start(line: str, pos: int) -> int:
    """start of the simple command containing `pos` (after the last ; && || | ( before it)."""
    best = 0
    for m in re.finditer(r"&&|\|\||;|\||\(|\bthen\b|\bdo\b", line[:pos]):
        best = m.end()
    while best < len(line) and line[best] == " ":
        best += 1
    return best


def rewrite(cmd: str, agent: str, root: Path, docs_dir: Optional[Path] = None, cwd: Optional[Path] = None,
            listener: Optional[str] = None) -> Tuple[Optional[str], List[str], Optional[str], List[str], Optional[Inv]]:
    """-> (new_command or None, fixes, deny_reason or None, warnings, inv). listener: "<short>:<settle>" -> REPL-only
    short-timeout listener through ROBOT_OPTIONS (only for repl/shell sessions importing Browser/SeleniumLibrary)."""
    inv = find(cmd)
    if inv is None:
        return None, [], None, [], None
    fixes: List[str] = []
    warns: List[str] = []
    lines = cmd.split("\n")
    body = body_lines(cmd, inv)
    debug = inv.sub in DEBUG_SUBS
    has_input = bool(inv.heredoc or inv.piped or inv.redirect_in)
    if inv.sub == "repl-server":
        return None, [], ("`robotcode repl-server` waits for a client and never returns in this shell. Use a piped "
                          "REPL instead (nothing was run):\n" + CARD), [], inv
    if not has_input and not inv.files and agent in ("claude", "opencode"):
        return None, [], ("this would start an INTERACTIVE robotcode " + inv.sub + " that waits for keyboard input "
                          "(your shell tool cannot type into it: it reads EOF and runs nothing, or hangs). Pipe the "
                          "statements in with a quoted heredoc (nothing was run):\n" + CARD), [], inv
    if not has_input and not inv.files:
        warns.append(RULE_MSG.get("C10_no_stdin") or "no piped input: the REPL reads EOF and exits at once")
    line = lines[inv.line_idx]
    if not debug and re.search(r"(['\"])[^'\"\n]*?(\s{2,}|\t)[^'\"\n]*\1", line[inv.args_start:inv.args_end]):
        return None, [], ("Positional arguments of `robotcode repl` are FILES, not statements. Feed statements on "
                          "stdin with a quoted heredoc (nothing was run):\n" + CARD), [], inv
    quote_fix = False
    if inv.heredoc and not inv.heredoc["quoted"] and any(re.search(r"[$@&%]\{", b) for b in body):
        joined = "\n".join(body)
        if all(joined[k + 1:k + 2] == "{" for k, ch in enumerate(joined) if ch == "$") and "`" not in joined:
            quote_fix = True
        else:
            return None, [], ("unquoted heredoc: the shell expands ${...} / $VAR BEFORE Robot Framework sees it. Quote "
                              f"the delimiter (<<'{inv.heredoc['delim']}') and put literal values into the statements "
                              "(nothing was run).\n" + CARD), [], inv
    if inv.piped:
        before = line[:inv.exe_start]
        m = re.search(r"(?:echo|printf)\s+(?:-\w+\s+)?\"([^\"]*)\"", before)
        if m and re.search(r"(?<!\\)[$@&%]\{", m.group(1)):
            return None, [], ("double-quoted echo/printf: the shell expands ${...} before Robot Framework sees it. "
                              "Use a quoted heredoc instead (nothing was run):\n" + CARD), [], inv
    # ---- body
    new_body = body
    if inv.heredoc:
        known = known_keywords(docs_dir)
        new_body, bmsgs, fired, bdeny = lint_body(body, debug, known)
        if bdeny:
            return None, [], ("REPL input refused (nothing was run): " + " ".join(bmsgs or [RULE_MSG.get(f, f) for f in fired
                                                                                          if f.startswith(("I05", "I06", "D02"))])
                              + ("\nAt the debug prompt each line runs alone: single keyword lines or inline IF."
                                 if "D02_rdb_single_lines" in fired else "") + "\n" + CARD), [], inv
        fixes += [_FIX_TEXT[f] for f in fired if f in _FIX_TEXT]
        warns += [m for m in bmsgs]
        warns += [RULE_MSG[f] for f in fired if f in _WARN_IDS and RULE_MSG.get(f)]
        last = next((x.strip() for x in reversed(new_body) if x.strip()), "")
        if not debug and last not in (".exit", ".quit", ".abort") and inv.heredoc["closed"]:
            new_body = list(new_body) + [".exit"]
            fixes.append("appended .exit")
        stm = [b.strip() for b in new_body if b.strip() and not b.strip().startswith((".", "#"))]
        if not debug and stm and any(PAGE_KW.match(x) for x in stm) and not any(SETUP_KW.match(x) for x in stm):
            warns.append(RULE_MSG.get("C12_fresh_session_per_call") or
                         "each robotcode call is a new session: start with Library/New Browser/New Page")
        if any(re.search(r"Set (Browser|Selenium) Timeout|^\s*(Import )?Library\s{2,}(Browser|SeleniumLibrary)\s{2,}"
                         r".*timeout=", b) for b in new_body) and any(b.strip().startswith(".save") for b in new_body):
            warns.append("timeout changes typed into the REPL are copied by .save into the test file -- remove them "
                         "there (the plain run must use the normal timeout)")
    if inv.files and not debug:
        warns.append(RULE_MSG.get("C11_file_argument_all_or_nothing") or "a FILE argument is parsed as one block")
    if "--break-on-failed-test" in line:
        warns.append(RULE_MSG.get("D06_break_on_failed_test_broken") or "--break-on-failed-test is unreliable")
    if not debug and re.search(r"(&&|\|\||;\s*echo\s+\$\?)", line[inv.args_end:]):
        warns.append(RULE_MSG.get("C07_exit_code_meaningless") or "robotcode repl always exits 0")
    # ---- command-level fixes
    add: List[str] = []
    args_part = line[inv.args_start:inv.args_end]
    glob = inv.glob
    moved = re.findall(r"(?:^|\s)(-p|--profile|-c|--config|-r|--root)[ =](\S+)", args_part)
    for opt, val in moved:
        args_part = re.sub(r"(?:^|\s)" + re.escape(opt) + r"[ =]" + re.escape(val), "", args_part, count=1)
        glob += f" {opt} {val}"
        fixes.append(f"moved {opt} before the subcommand")
    if not _has_opt(inv.args, "--plain", "--backend"):
        add.append("--plain")
        fixes.append("added --plain")
    if not _has_opt(inv.args, "--no-history"):
        add.append("--no-history")
    if not _has_opt(inv.args, "-d", "--outputdir"):
        (root / ".rf" / "out").mkdir(parents=True, exist_ok=True)
        add += ["-d", str(root / ".rf" / "out") if re.search(r"(?:^|[\s;&|(])cd\s", cmd) else ".rf/out"]
        fixes.append("added -d .rf/out")
    else:
        a = inv.args
        for k, x in enumerate(a):
            if x in ("-d", "--outputdir") and k + 1 < len(a):
                d = Path(a[k + 1])
                (d if d.is_absolute() else root / d).mkdir(parents=True, exist_ok=True)
    if not debug and not _has_opt(inv.args, "-o", "--output"):
        add += ["-o", "repl-output.xml"]
    tail = line[inv.args_end:]
    if not re.search(r"2>&1|&>|\|&", tail + args_part):
        tail = " 2>&1" + (tail if tail.startswith(" ") or not tail else " " + tail)
        fixes.append("added 2>&1")
    if quote_fix:
        hd = _HEREDOC.search(tail)
        if hd:
            tail = tail[:hd.start()] + f"<<{hd.group(1)}'{inv.heredoc['delim']}'" + tail[hd.end():]
            fixes.append("quoted the heredoc delimiter")
    exe = line[inv.exe_start:inv.exe_start + len(re.match(r"\S+", line[inv.exe_start:]).group(0))]
    head = line[:inv.exe_start]
    prefix = ""
    if listener and inv.sub in ("repl", "shell") and "ROBOT_OPTIONS" not in cmd and (
            any(re.match(r"^\s*(Import Library|Library)\s{2,}(Browser|SeleniumLibrary)\b", b) for b in new_body)):
        prefix = f"ROBOT_OPTIONS='--listener {LISTENER}:{listener}' "
        fixes.append("REPL-only short element timeout via a listener (navigation keeps the normal timeout; locator "
                     "misses are re-checked: slow vs missing; nothing is typed into your session)")
    if prefix:
        seg = _segment_start(line, inv.exe_start)
        head = head[:seg] + prefix + head[seg:]
    new_line = head + exe + glob + " " + inv.sub + (" " + " ".join(shlex.quote(x) for x in add) if add else "") \
        + args_part + tail
    lines[inv.line_idx] = new_line
    if inv.heredoc:
        lines[inv.heredoc["start"]:inv.heredoc["end"]] = new_body
    new = "\n".join(lines)
    if new == cmd:
        return None, [], None, warns, inv
    return new, fixes, None, list(dict.fromkeys(warns)), inv


# ------------------------------------------------------------------------------------------------ output parsing
_FAIL = re.compile(r"^\s*\[ FAIL \]\s?(.*)$")
_EXC = re.compile(r"^\*\s+exception\s+(?:(?P<owner>[^.\s][^\s]*?)\.)?(?P<kw>[^(]+?)\s+\((?P<loc>[^)]+)\)\s+[—-]+\s*(?P<msg>.*)$")
_KWLINE = re.compile(r"^(?P<ind>\s*)KEYWORD (?P<owner>[^.\s]+)\.(?P<kw>.+?)(?:\s{2}.*)?$")


def parse_output(text: str) -> Dict[str, Any]:
    """robotcode repl / robot-debug console output -> {fails:[{msg, kw?, owner?, loc?}], exceptions, imports}"""
    out: Dict[str, Any] = {"fails": [], "exceptions": []}
    last_kw: Optional[Dict[str, str]] = None
    for raw in (text or "").splitlines():
        m = _KWLINE.match(raw)
        if m:
            last_kw = {"owner": m.group("owner"), "kw": m.group("kw").strip()}
            continue
        m = _EXC.match(raw.strip())
        if m:
            out["exceptions"].append({"owner": m.group("owner"), "kw": m.group("kw").strip(), "loc": m.group("loc"),
                                      "msg": m.group("msg").strip()[:300]})
            continue
        m = _FAIL.match(raw)
        if m:
            rec = {"msg": m.group(1).strip()[:300]}
            nk = re.match(r"No keyword with name '([^']+)' found", rec["msg"])
            if nk:
                rec["unknown"] = nk.group(1)
            elif last_kw:
                rec.update(last_kw)
            out["fails"].append(rec)
    return out


def statements(body: List[str]) -> List[str]:
    return [b.strip() for b in body if b.strip() and not b.strip().startswith(("#", "."))]


def imports_in(lines: List[str]) -> List[Tuple[str, str]]:
    """`Import Library    X` / `Import Resource    path` / Settings `Library    X` lines -> [(kind, target)]"""
    out = []
    for b in lines:
        m = re.match(r"^\s*(?:Import\s+(Library|Resource)|(Library|Resource))\s{2,}(\S+(?: \S+)*)", b, re.I)
        if m:
            kind = (m.group(1) or m.group(2)).lower()
            target = re.split(r"\s{2,}|\t", m.group(3).strip())[0]
            out.append((kind, target))
    return out


SHORT_TIMEOUT_MARK = "# rfh3: live-only short timeout"


def inject_short_timeout(cmd: str, inv: Inv, browser_s: str, selenium_s: str) -> Tuple[str, bool]:
    """REPL (not robot-debug): after `Import Library    Browser|SeleniumLibrary` add a short element timeout,
    marked so it can be stripped from anything saved with .save."""
    if inv.sub not in ("repl", "shell") or not inv.heredoc:
        return cmd, False
    lines = cmd.split("\n")
    body = lines[inv.heredoc["start"]:inv.heredoc["end"]]
    if any("Set Browser Timeout" in b or "Set Selenium Timeout" in b for b in body):
        return cmd, False
    out, done = [], False
    for b in body:
        out.append(b)
        m = re.match(r"^(\s*)Import\s+Library\s{2,}(Browser|SeleniumLibrary)\s*(?:$|\s{2,}.*)", b)
        if m:
            kw = (f"Set Browser Timeout    {browser_s}" if m.group(2) == "Browser"
                  else f"Set Selenium Timeout    {selenium_s}")
            out.append(f"{m.group(1)}{kw}    {SHORT_TIMEOUT_MARK}")
            done = True
    if not done:
        return cmd, False
    lines[inv.heredoc["start"]:inv.heredoc["end"]] = out
    return "\n".join(lines), True


def saved_files(body: List[str], cwd: Path) -> List[Path]:
    out = []
    for b in body:
        m = re.match(r"^\s*\.save\s+(?:-\S+\s+(?:\S+\s+)?)*(\S+\.(?:robot|resource))\s*$", b)
        if m:
            p = Path(m.group(1))
            out.append(p if p.is_absolute() else cwd / p)
    return out


def strip_injected(path: Path, values: Tuple[str, ...]) -> int:
    """remove the injected short-timeout statement from a file the REPL saved (.save), with or without the mark."""
    try:
        text = path.read_text()
    except OSError:
        return 0
    pat = re.compile(r"^\s*Set (?:Browser|Selenium) Timeout\s{2,}(?:%s)\s*(?:#.*)?$" % "|".join(map(re.escape, values)))
    lines = text.splitlines(True)
    keep = [l for l in lines if SHORT_TIMEOUT_MARK not in l and not pat.match(l.rstrip("\n"))]
    if len(keep) != len(lines):
        path.write_text("".join(keep))
    return len(lines) - len(keep)
