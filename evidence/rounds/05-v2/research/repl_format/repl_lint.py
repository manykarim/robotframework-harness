#!/usr/bin/env python3
"""Prototype PreToolUse(Bash) linter for `robotcode repl` / `robot-debug` commands.

Applies the rules in ../repl_format_rules.json (ids referenced in output).
lint(command, cwd) -> {"match": bool, "decision": "allow"|"rewrite"|"deny",
                       "command": <possibly rewritten>, "messages": [...], "fired": [...], "card": str|None}
stdlib only. `python3 repl_lint.py --selftest` runs the examples.
"""
import json, os, re, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
CARD = (HERE / "format_card.txt").read_text() if (HERE / "format_card.txt").exists() else ""
try:
    _KW = json.loads((HERE / "kwnames_cache.json").read_text())
except Exception:
    _KW = {}
KNOWN = {}
for lib, names in _KW.items():
    for n in names:
        KNOWN[re.sub(r"[\s_]", "", n.lower())] = n

INVOKE = re.compile(r"(?P<pre>(?:^|[;&|(]\s*|\bthen\s+|\bdo\s+)(?:\S*=\S*\s+)*)(?P<exe>\S*robotcode)(?P<glob>(?:\s+-{1,2}[\w-]+(?:[ =](?!-)\S+)?)*?)\s+(?P<sub>repl|shell|robot-debug|run-debug)\b(?P<rest>[^\n]*)")
HEREDOC = re.compile(r"<<(-?)\s*(['\"]?)([A-Za-z_][A-Za-z0-9_]*)\2")
OPENERS = {"FOR", "WHILE", "IF", "TRY", "GROUP"}
SEP = re.compile(r"  +|\t")


def project_root(cwd):
    p = Path(cwd).resolve()
    for d in [p, *p.parents]:
        if any((d / m).exists() for m in ("robot.toml", "pyproject.toml", ".git")):
            return d
    return p


def first_cell(line):
    s = line.strip()
    return SEP.split(s, maxsplit=1)[0].upper() if s else ""


def opens_block(line):
    cells = [c for c in SEP.split(line.strip()) if c]
    if not cells:
        return False
    head = cells[0].upper()
    if head == "IF":  # inline IF: IF  cond  Keyword ...  -> 3+ cells and no END needed
        return len(cells) <= 2
    return head in OPENERS


def fix_single_space(line):
    """I01: split `Kw Name arg1 arg2` when a known keyword is the longest word-prefix."""
    s = line.strip()
    if not s or "\t" in s or "  " in s or s.startswith((".", "#", "$", "@", "&", "*", "[", "`")):
        m = re.match(r"^([$@&]\{[^}]+\})\s?=?\s(\S.*)$", s)
        if not m or "  " in s:
            return None
        rest = fix_single_space(m.group(2))
        return f"{m.group(1)}=    {rest if rest else m.group(2)}"
    words = s.split(" ")
    if len(words) < 2 or words[0].upper() in OPENERS | {"END", "ELSE", "EXCEPT", "FINALLY", "VAR", "RETURN"}:
        return None
    for i in range(len(words) - 1, 0, -1):
        key = re.sub(r"[\s_]", "", " ".join(words[:i]).lower())
        if key in KNOWN:
            return KNOWN[key] + "    " + "    ".join(words[i:])
    return None


def lint_body(body, debug=False):
    out, msgs, fired, deny = [], [], [], False
    lines = body.split("\n")
    depth = 0
    in_kw_section = False
    for raw in lines:
        line = raw.rstrip("\r")
        if line != raw:
            fired.append("I12_crlf")
        st = line.strip()
        if re.match(r"^(```|~~~)", st):
            fired.append("I07_markdown_fences"); continue
        m = re.match(r"^\*{3}\s*(Settings|Variables|Test Cases|Tasks|Keywords|Comments)\s*\*{3}", st, re.I)
        if m:
            sec = m.group(1).lower()
            in_kw_section = sec == "keywords"
            if in_kw_section:
                deny = True; fired.append("I08_sections_and_definitions")
                msgs.append("The REPL cannot define keywords: put them in a .resource file and `Import Resource    path.resource`.")
            else:
                fired.append("I08_sections_and_definitions")
            continue
        if line and not line[0].isspace() and not st.startswith(("$", "@", "&", ".", "#")) and out == [] and False:
            pass
        if re.match(r"^\[(Tags|Documentation|Setup|Teardown|Timeout|Template|Arguments|Return)\]", st):
            fired.append("I09_test_settings_ignored")
            if st.startswith(("[Setup]", "[Teardown]")):
                msgs.append(f"`{st.split(']')[0]}]` lines are ignored in the REPL; call the keyword directly.")
            continue
        if re.match(r"^(:FOR\b|\\\s{2,})", st):
            deny = True; fired.append("I06_old_for_syntax"); msgs.append("Old :FOR syntax: use FOR ... END."); out.append(line); continue
        if re.match(r"^\.\.\.(\s{2,}|\t|$)", st) and out:
            j = len(out) - 1
            while j >= 0 and not out[j].strip():
                j -= 1
            tail = SEP.split(st, maxsplit=1)[1] if SEP.search(st) else ""
            if j >= 0 and tail:
                out[j] = out[j].rstrip() + "    " + tail
            fired.append("I03_no_continuation_on_stdin"); continue
        if not st:
            if depth > 0:
                fired.append("I04_blank_line_inside_block"); continue
            out.append(line); continue
        if re.match(r"^(quit|\.q|:q|exit\(\)|\.e)$", st):
            fired.append("I15_exit_words"); out.append(".exit"); continue
        m = re.match(r"^\.(kw|doc|break|b|tbreak)\s+([\"'])(.*?)\2(\s*,.*)?$", st)
        if m:
            fired.append("I16_dot_commands"); out.append(f".{m.group(1)} {m.group(3)}{m.group(4) or ''}"); continue
        if re.match(r"^[$@&]\{[^}]+\}(\[[^\]]*\])*$", st):
            fired.append("I10_bare_variable_line"); out.append((".pp " if debug else "Log To Console    ") + st); continue
        if debug:
            if re.match(r"^(FOR|WHILE|TRY|GROUP)\b", st) or (st.upper().startswith("IF") and not opens_block(st) is False and opens_block(st)):
                deny = True; fired.append("D02_rdb_single_lines")
            mm = re.match(r"^(Library|Resource|Variables)(\s{2,}|\t)(.*)$", st)
            if mm:
                fired.append("D03_rdb_import_alias"); out.append(f"Import {mm.group(1)}    {mm.group(3)}"); continue
        if re.match(r"^(?:[$@&]\{[^}]+\}=?\s{2,})*Run Keyword (If|Unless)\b", st):
            fired.append("I13_run_keyword_if")
        if not st.startswith((".", "#")):
            fixed = fix_single_space(st)
            if fixed:
                fired.append("I01_single_space_separator"); line = line[: len(line) - len(line.lstrip())] + fixed; st = fixed
            cells = [c for c in SEP.split(st) if c]
            while cells and re.match(r"^[$@&]\{[^}]+\}\s*=?$", cells[0]):
                cells = cells[1:]
            if len(cells) > 2 and any(re.sub(r"[\s_]", "", c.lower()) in KNOWN for c in cells[1:]) and not cells[0].upper() in OPENERS | {"VAR"} and not re.search(r"Keyword|Promise To|^IF$|^ELSE", cells[0], re.I):
                fired.append("I11_one_statement_per_line")
        if opens_block(st):
            depth += 1
        elif first_cell(st) == "END":
            depth = max(0, depth - 1)
        out.append(line)
    if depth > 0:
        deny = True; fired.append("I05_unclosed_block"); msgs.append("Unclosed FOR/IF/WHILE/TRY/GROUP: add END (an unclosed block runs nothing, silently).")
    return "\n".join(out), msgs, fired, deny


RULE_MSG = {r["id"]: r.get("message", "") for r in json.loads((HERE.parent / "repl_format_rules.json").read_text())["rules"]}


def lint(command, cwd="."):
    res = {"match": False, "decision": "allow", "command": command, "messages": [], "fired": [], "card": None}
    m = INVOKE.search(command)
    if not m:
        return res
    res["match"] = True
    sub = m.group("sub")
    debug = sub in ("robot-debug", "run-debug")
    fired, msgs, deny = [], [], False
    glob, rest = m.group("glob"), m.group("rest")
    # C09: global options after the subcommand
    mv = re.findall(r"\s(-p|--profile|-c|--config|-r|--root)[ =](\S+)", rest)
    for opt, val in mv:
        rest = re.sub(r"\s" + re.escape(opt) + r"[ =]" + re.escape(val), "", rest, count=1)
        glob += f" {opt} {val}"
        fired.append("C09_global_option_position")
    flags = ""
    if not re.search(r"--plain\b|--backend[ =]plain", rest):
        flags += " --plain"; fired.append("C01_plain_backend")
    if "--no-history" not in rest:
        flags += " --no-history"; fired.append("C02_no_history")
    # C08 statement as argument (repl only)
    if not debug and re.search(r"(['\"])[^'\"\n]*?(\s{2,}|\t)[^'\"\n]*\1", rest.split("<<")[0].split("|")[0]):
        deny = True; fired.append("C08_statement_as_argument")
    # C03 output dir
    dm = re.search(r"(?:^|\s)(?:-d|--outputdir)[ =](\S+)", rest)
    prefix = ""
    root = project_root(cwd)
    rr = re.search(r"(?:-r|--root)\s+(\S+)", glob)
    if rr:
        root = Path(cwd, rr.group(1)).resolve()
    if dm:
        d = dm.group(1).strip("'\"")
        target = Path(d) if os.path.isabs(d) else root / d
        if not target.exists():
            prefix = f"mkdir -p {target} && "; fired.append("C03_outputdir_must_exist")
            if not os.path.isabs(d) and Path(cwd).resolve() != root:
                msgs.append(f"Note: relative -d {d} resolves to {target} (project root {root}), not your cwd.")
    else:
        toml = root / "robot.toml"
        od = None
        if toml.exists():
            mm = re.search(r'^\s*output-dir\s*=\s*"([^"]+)"', toml.read_text(), re.M)
            od = mm.group(1) if mm else None
        target = root / (od or "results")
        if od and not target.exists():
            prefix = f"mkdir -p {target} && "; fired.append("C03_outputdir_must_exist")
        if not od:
            flags += " -d out"; prefix = f"mkdir -p {root / 'out'} && "; fired.append("C03_outputdir_must_exist")
    # C06 stderr
    after = command[m.end("rest") - len(m.group("rest")):]
    tail_cmd = rest
    if re.search(r"\|(?!\|)|(?<![0-9&])>\s*\S", tail_cmd.split("<<")[0] + (tail_cmd.split("<<")[1] if "<<" in tail_cmd else "")) and not re.search(r"2>&1|&>|\|&", tail_cmd):
        rest = re.sub(r"(\s*)(\|(?!\|)|(?<![0-9&<])>(?!&))", r" 2>&1\1\2", rest, count=1)
        fired.append("C06_merge_stderr")
    # C07
    if not debug and re.search(r"(&&|\|\||;\s*echo\s+\$\?)", rest + command[m.end():]):
        fired.append("C07_exit_code_meaningless")
    new_cmd = command[: m.start("exe")] + prefix + m.group("exe") + glob + " " + sub + flags + rest + command[m.end("rest"):]
    # heredoc body
    hm = HEREDOC.search(new_cmd)
    if hm:
        delim = hm.group(3)
        start = new_cmd.find("\n", hm.end())
        endm = re.search(r"^" + ("\\s*" if hm.group(1) else "") + re.escape(delim) + r"\s*$", new_cmd[start + 1:], re.M) if start >= 0 else None
        if start >= 0 and endm:
            body = new_cmd[start + 1: start + 1 + endm.start()]
            nb, bm, bf, bdeny = lint_body(body.rstrip("\n"), debug=debug)
            fired += bf; msgs += bm; deny = deny or bdeny
            quote = hm.group(2)
            head = new_cmd[: hm.start()]
            opener = hm.group(0)
            if not quote and re.search(r"[$@&%]\{", body):
                if all(nb[i + 1: i + 2] == "{" for i in [k for k, ch in enumerate(nb) if ch == "$"]):
                    opener = f"<<{hm.group(1)}'{delim}'"; fired.append("C04_quote_heredoc")
                else:
                    deny = True; fired.append("C04_quote_heredoc")
            new_cmd = head + opener + new_cmd[hm.end(): start + 1] + nb + "\n" + new_cmd[start + 1 + endm.start():]
    elif re.search(r"(echo|printf)\s+(-e\s+)?\"[^\"]*(?<!\\)[$@&%]\{", command):
        deny = True; fired.append("C05_double_quoted_echo")
    elif not re.search(r"\|\s*\S*robotcode|<\s*\S|\s[\w./-]+\.(robot|robotrepl|txt|resource)\b", command):
        fired.append("C10_no_stdin")
    if "--break-on-failed-test" in command:
        fired.append("D06_break_on_failed_test_broken")
    fired = list(dict.fromkeys(fired))
    for f in fired:
        txt = RULE_MSG.get(f, "")
        if txt and txt != "(silent)" and txt not in msgs:
            msgs.append(f"[{f}] {txt}")
    res.update(fired=fired, messages=msgs, card=CARD or None)
    if deny:
        res["decision"] = "deny"
    elif new_cmd != command:
        res["decision"] = "rewrite"; res["command"] = new_cmd
    return res


EXAMPLES = [
    # (id, command, expected decision, must-fire subset)
    ("ok_canonical", "mkdir -p out && robotcode repl --plain --no-history -d out <<'RF' 2>&1\nLog To Console    hi\nRF", "allow", []),
    ("no_plain", "robotcode repl --no-history -d out <<'RF' 2>&1\nLog To Console    hi\nRF", "rewrite", ["C01_plain_backend"]),
    ("missing_d", "robotcode repl --plain --no-history -d /tmp/r5_definitely_missing_dir <<'RF' 2>&1\nLog To Console    hi\nRF", "rewrite", ["C03_outputdir_must_exist"]),
    ("unquoted_heredoc", "robotcode repl --plain --no-history -d out <<RF 2>&1\n${x}=    Set Variable    5\nLog To Console    ${x}\nRF", "rewrite", ["C04_quote_heredoc"]),
    ("unquoted_heredoc_shellvar", "robotcode repl --plain --no-history -d out <<RF 2>&1\n${x}=    Set Variable    $HOME\nRF", "deny", ["C04_quote_heredoc"]),
    ("dq_echo", "echo \"Log To Console    ${x}\" | robotcode repl --plain -d out", "deny", ["C05_double_quoted_echo"]),
    ("pipe_no_2to1", "robotcode repl --plain --no-history -d out <<'RF' | tail -20\nShould Be Equal    a    b\nRF", "rewrite", ["C06_merge_stderr"]),
    ("exit_code", "robotcode repl --plain --no-history -d out <<'RF' 2>&1 && echo PASSED\nLog    x\nRF", "allow", ["C07_exit_code_meaningless"]),
    ("stmt_as_arg", "robotcode repl --plain -d out 'Log To Console    x'", "deny", ["C08_statement_as_argument"]),
    ("profile_after", "robotcode repl -p dev --plain --no-history -d out <<'RF' 2>&1\nLog    x\nRF", "rewrite", ["C09_global_option_position"]),
    ("no_stdin", "robotcode repl --plain --no-history -d out", "allow", ["C10_no_stdin"]),
    ("single_space", "robotcode repl --plain --no-history -d out <<'RF' 2>&1\nLog To Console single-space\nRF", "rewrite", ["I01_single_space_separator"]),
    ("single_space_assign", "robotcode repl --plain --no-history -d out <<'RF' 2>&1\n${t} = Get Title\nRF", "rewrite", ["I01_single_space_separator"]),
    ("continuation", "robotcode repl --plain --no-history -d out <<'RF' 2>&1\n${d}    Create Dictionary    a=1\n...    b=2\nLog To Console    ${d}\nRF", "rewrite", ["I03_no_continuation_on_stdin"]),
    ("blank_in_block", "robotcode repl --plain --no-history -d out <<'RF' 2>&1\nFOR    ${i}    IN RANGE    3\n\n    Log To Console    ${i}\nEND\nRF", "rewrite", ["I04_blank_line_inside_block"]),
    ("unclosed", "robotcode repl --plain --no-history -d out <<'RF' 2>&1\nFOR    ${i}    IN RANGE    3\n    Log To Console    ${i}\nRF", "deny", ["I05_unclosed_block"]),
    ("inline_if_ok", "robotcode repl --plain --no-history -d out <<'RF' 2>&1\nIF    $x == 1    Log To Console    one\nRF", "allow", []),
    ("old_for", "robotcode repl --plain --no-history -d out <<'RF' 2>&1\n:FOR    ${i}    IN RANGE    2\n\\    Log    ${i}\nRF", "deny", ["I06_old_for_syntax"]),
    ("fences", "robotcode repl --plain --no-history -d out <<'RF' 2>&1\n```robotframework\nLog To Console    x\n```\nRF", "rewrite", ["I07_markdown_fences"]),
    ("pasted_settings", "robotcode repl --plain --no-history -d out <<'RF' 2>&1\n*** Settings ***\nLibrary    Collections\nRF", "rewrite", ["I08_sections_and_definitions"]),
    ("keywords_section", "robotcode repl --plain --no-history -d out <<'RF' 2>&1\n*** Keywords ***\nMy Kw\n    Log    x\nRF", "deny", ["I08_sections_and_definitions"]),
    ("tags", "robotcode repl --plain --no-history -d out <<'RF' 2>&1\n[Setup]    Log    s\nLog    x\nRF", "rewrite", ["I09_test_settings_ignored"]),
    ("bare_var", "robotcode repl --plain --no-history -d out <<'RF' 2>&1\n${x}=    Set Variable    1\n${x}\nRF", "rewrite", ["I10_bare_variable_line"]),
    ("two_stmts", "robotcode repl --plain --no-history -d out <<'RF' 2>&1\nLog To Console    a    Log To Console    b\nRF", "allow", ["I11_one_statement_per_line"]),
    ("crlf", "robotcode repl --plain --no-history -d out <<'RF' 2>&1\nLog To Console    a\r\nRF", "rewrite", ["I12_crlf"]),
    ("rki", "robotcode repl --plain --no-history -d out <<'RF' 2>&1\nRun Keyword If    ${True}    Log    x\nRF", "allow", ["I13_run_keyword_if"]),
    ("quit_word", "robotcode repl --plain --no-history -d out <<'RF' 2>&1\nLog    x\nquit\nRF", "rewrite", ["I15_exit_words"]),
    ("kw_quoted", "robotcode repl --plain --no-history -d out <<'RF' 2>&1\n.kw \"Get Text\"\nRF", "rewrite", ["I16_dot_commands"]),
    ("dbg_ok", "robotcode robot-debug --plain --no-history -d out suite.robot <<'RF' 2>&1\n.where\n.pp ${total}\n.c\nRF", "allow", []),
    ("dbg_for", "robotcode robot-debug --plain --no-history -d out suite.robot <<'RF' 2>&1\nFOR    ${j}    IN RANGE    2\n    Log    ${j}\nEND\n.c\nRF", "deny", ["D02_rdb_single_lines"]),
    ("dbg_library", "robotcode robot-debug --plain --no-history -d out suite.robot <<'RF' 2>&1\nLibrary    String\n.c\nRF", "rewrite", ["D03_rdb_import_alias"]),
    ("dbg_break_quotes", "robotcode robot-debug --plain --no-history -d out --stop-on-entry suite.robot <<'RF' 2>&1\n.break \"Process Item\"\n.c\nRF", "rewrite", ["I16_dot_commands"]),
    ("dbg_bare_var", "robotcode robot-debug --plain --no-history -d out suite.robot <<'RF' 2>&1\n${total}\n.c\nRF", "rewrite", ["I10_bare_variable_line"]),
    ("not_robotcode", "robot -d out tests/", "allow", []),
]


def selftest():
    os.makedirs(HERE / "lab" / "out", exist_ok=True)
    ok = 0
    rows = []
    for cid, cmd, want, must in EXAMPLES:
        r = lint(cmd, cwd=str(HERE / "lab"))
        good = r["decision"] == want and all(f in r["fired"] for f in must)
        ok += good
        rows.append({"id": cid, "ok": good, "decision": r["decision"], "fired": r["fired"], "command": r["command"] if r["decision"] == "rewrite" else None})
        print(f"{'OK ' if good else 'BAD'} {cid:24s} {r['decision']:7s} {','.join(x.split('_')[0] for x in r['fired'])}")
    (HERE / "logs" / "repl_lint_selftest.json").write_text(json.dumps(rows, indent=1))
    print(f"{ok}/{len(EXAMPLES)} examples as expected")
    return ok == len(EXAMPLES)


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        sys.exit(0 if selftest() else 1)
    data = json.load(sys.stdin)
    print(json.dumps(lint(data.get("command", ""), data.get("cwd", "."))))
