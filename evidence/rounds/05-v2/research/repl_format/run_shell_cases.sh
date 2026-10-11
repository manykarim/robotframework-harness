#!/usr/bin/env bash
# Round 5: shell-level REPL format checks (heredoc quoting, PTY vs pipe, history, -d resolution,
# file arguments, exit words, truncation of assigned values). Logs -> logs/S*.log
set -u
HERE="$(cd "$(dirname "$0")" && pwd)"
LAB="$HERE/lab"; LOGS="$HERE/logs"; mkdir -p "$LOGS"
RC=~/workspace/robotcode-experiments/.venv/bin/robotcode
cd "$LAB"
log() { echo "=== $1"; }

{ log S01_unquoted_heredoc
$RC repl --plain --no-history -d "$LAB/out" <<RF 2>&1
\${x}=    Set Variable    5
\${x}=    Set Variable    escaped-ok
${x}=    Set Variable    unescaped
Log To Console    value=${x}
Log To Console    value=\${x}
RF
echo "rc=$?"; } > "$LOGS/S01_unquoted_heredoc.log" 2>&1

{ log S02_quoted_heredoc
$RC repl --plain --no-history -d "$LAB/out" <<'RF' 2>&1
${x}=    Set Variable    quoted-ok
Log To Console    value=${x} py=${{ len($x) }}
RF
echo "rc=$?"; } > "$LOGS/S02_quoted_heredoc.log" 2>&1

{ log S03_echo_single_quotes
echo 'Log To Console    ${SPACE}single-quoted-echo' | $RC repl --plain --no-history -d "$LAB/out" 2>&1
log S03b_echo_double_quotes
echo "Log To Console    \${SPACE}dq-escaped  \${x}" | $RC repl --plain --no-history -d "$LAB/out" 2>&1
log S03c_printf_tabs
printf 'Log To Console\\tprintf-tab\n' | $RC repl --plain --no-history -d "$LAB/out" 2>&1
} > "$LOGS/S03_echo.log" 2>&1

{ log S04_stderr_dropped_without_2to1
$RC repl --plain --no-history -d "$LAB/out" <<'RF' 2>/dev/null
Log To Console    visible
Should Be Equal    a    b
Log To Console    still-visible
RF
log S04b_pipe_tail_without_2to1_stdout_only
$RC repl --plain --no-history -d "$LAB/out" <<'RF' 2>/dev/null | tail -5
Should Be Equal    a    b
RF
echo "(nothing above means FAIL went to stderr)"
} > "$LOGS/S04_stderr.log" 2>&1

{ log S05_history_file_probe
before=$(find ~ -maxdepth 4 -newer "$LAB/robot.toml" -name "*history*" 2>/dev/null | grep -i robotcode)
echo 'Log To Console    hist' | $RC repl --plain -d "$LAB/out" 2>&1
sleep 0.5
find ~/.local ~/.cache ~/.config ~ -maxdepth 4 -mmin -1 \( -name "*hist*" -o -name "*repl*" \) 2>/dev/null | grep -iv "zsh\|bash" | head
echo "(above: history-like files modified in the last minute)"
} > "$LOGS/S05_history.log" 2>&1

{ log S06_relative_d_from_subdir
mkdir -p "$LAB/sub"; cd "$LAB/sub"
echo 'Log To Console    OUTDIR=${OUTPUT DIR} EXECDIR=${EXECDIR} CURDIR=${CURDIR}' | $RC repl --plain --no-history -d rel_out 2>&1
echo "exists lab/rel_out: $(test -d "$LAB/rel_out" && echo yes || echo no); exists lab/sub/rel_out: $(test -d "$LAB/sub/rel_out" && echo yes || echo no)"
log S06b_root_override
echo 'Log To Console    OUTDIR=${OUTPUT DIR} EXECDIR=${EXECDIR}' | $RC --root "$LAB/sub" repl --plain --no-history -d rel_out 2>&1
cd "$LAB"
} > "$LOGS/S06_relative_d.log" 2>&1

cat > "$LAB/steps_cont.robotrepl" <<'RF'
${d}    Create Dictionary    a=1
...    b=2
Log To Console    file-d=${d}

Log To Console    after-blank-in-file
RF
cat > "$LAB/steps_err.robotrepl" <<'RF'
Log To Console    first-line-of-bad-file
FOR    ${i}    IN RANGE    2
    Log To Console    i=${i}
Log To Console    last-line-of-bad-file
RF
{ log S07_file_arg_continuation
$RC repl --plain --no-history -d "$LAB/out" steps_cont.robotrepl 2>&1; echo "rc=$?"
log S07b_file_arg_syntax_error
$RC repl --plain --no-history -d "$LAB/out" steps_err.robotrepl 2>&1; echo "rc=$?"
log S07c_file_then_stdin_inspect
echo 'Log To Console    from-stdin d=${d}' | $RC repl --plain --no-history -d "$LAB/out" -i steps_cont.robotrepl 2>&1; echo "rc=$?"
log S07d_file_then_stdin_no_inspect
echo 'Log To Console    from-stdin-ignored?' | $RC repl --plain --no-history -d "$LAB/out" steps_cont.robotrepl 2>&1; echo "rc=$?"
} > "$LOGS/S07_file_args.log" 2>&1

{ for w in exit quit .quit .q .e ':q' 'exit()'; do
  log "S08_exit_word [$w]"
  printf '%s\nLog To Console    after-exit-word\n' "$w" | $RC repl --plain --no-history -d "$LAB/out" 2>&1 | head -5
done; } > "$LOGS/S08_exit_words.log" 2>&1

{ log S09_assign_truncation
$RC repl --plain --no-history -d "$LAB/out" <<'RF' 2>&1 | awk '{print length($0) ": " substr($0,1,120)}'
${big}=    Evaluate    'x' * 20000
Log    ${big}
Log To Console    len=${{ len($big) }}
RF
} > "$LOGS/S09_truncation.log" 2>&1

{ log S10_variable_cli
$RC repl --plain --no-history -d "$LAB/out" -v HOST:example.local -v "TIMEOUT:2s" <<'RF' 2>&1
Log To Console    host=${HOST} timeout=${TIMEOUT}
RF
} > "$LOGS/S10_variable_cli.log" 2>&1

{ log S11_show_keywords
$RC repl --plain --no-history -d "$LAB/out" -k <<'RF' 2>&1
${x}=    Set Variable    1
Log To Console    k
RF
} > "$LOGS/S11_show_keywords.log" 2>&1

{ log S12_source_cwd
mkdir -p "$LAB/sub/res2"; printf '*** Keywords ***\nSub Kw\n    Log To Console    sub-kw\n' > "$LAB/sub/res2/b.resource"
$RC repl --plain --no-history -d "$LAB/out" -s "$LAB/sub/anything.robot" <<'RF' 2>&1
Log To Console    CURDIR=${CURDIR}
Import Resource    res2/b.resource
Sub Kw
RF
} > "$LOGS/S12_source_cwd.log" 2>&1

echo done
