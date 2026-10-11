# Static-Analysis Quality Gates for rf-mcp: Robocop + robotcode analyze

**Status:** research results (no product code changed)
**Date:** 2026-10-02
**Branch / worktree:** `research/robotcode-remote-mcp` → `~/workspace/rf-mcp-robotcode` (based on `main` @ c1a18eb, rf-mcp v0.36.0)

**Tool versions:**

| Tool | Version |
|---|---|
| Robot Framework | 7.5 (cross-checked on 7.3.2) |
| robotcode | 2.7.0 (`robotcode analyze code`, language server) |
| Robocop | 9.1.0 |
| Browser | 20.5.0 (cross-checked on 19.12.7) |
| RequestsLibrary | 0.9.7 |

**Question:** does running **Robocop** and **robotcode's static analyzer** next to rf-mcp raise the quality of the test suites rf-mcp and its agents produce? Which defects do they catch that rf-mcp misses today, at what cost? Which `build_test_suite` defects did they expose?

---

## 1. Executive summary

- **rf-mcp ships no static analysis today.**
  - Its only pre-run check is `robot --dryrun` inside `run_test_suite(mode="dry")`.
  - Its error hints fire only *after* a keyword fails at runtime.
  - On a generated BDD suite with 6 planted errors, rf-mcp's dry run surfaced **2 unique errors with no line numbers**. robotcode analyze found **6/6 with `line:col`**.
- **robotcode analyze and Robocop are complementary; neither replaces `--dryrun`.** On 33 planted errors in agent-style RF files:

  | Gate | Errors caught (of 33) | False positives (15 valid files) |
  |---|---:|---:|
  | Robocop, default rules | 8 | 0 errors (but 3–6 style warnings per file) |
  | Robocop, **agent profile** (project rules on, style noise off) | **26** | 1 |
  | robotcode analyze | **28** | 3 |
  | `robot --dryrun` (what rf-mcp uses) | 30 | 0 |
  | **Robocop agent profile + robotcode analyze** | **30** | – |
  | **+ `robot --dryrun`** | **32** | – |

  The one miss in every tool is `POST On Session` without a URL. RequestsLibrary's `*args, **kwargs` signature only fails at runtime.
- **Each tool covers what the others miss:**
  - robotcode adds **undefined variables**, **named-argument names**, unexecuted keyword bodies and precise ranges.
  - Robocop adds **outdated syntax with safe auto-fix**, the **lowercase-`else` silent pass**, duplicate tests and correct library-priority handling.
  - `--dryrun` adds **type conversion** (Browser `AssertionOperator` enum, int arguments) and **library init arguments**.
- **Outdated syntax (common in LLM output) is fixed automatically.** Robocop flagged **7/7** deprecated constructs (`Run Keyword If`, `[Return]`, `WITH NAME`, `Exit For Loop`, `Force Tags`, …); robotcode analyze flagged 4/7. `robocop check --fix` repaired **7/7 safely**, and every fixed file ran clean, including assigned `Run Keyword If … ELSE` and ELSE IF chains.
- **The noise is manageable with a tuned profile.** On 36 real agent-written and rf-mcp-generated suites:

  | Rule set | Findings | Of which real problems |
  |---|---:|---|
  | Robocop default | 609 | mostly style |
  | built-in `robocop:minimal` | 95 | mostly unused variables |
  | **agent profile** | **63** | **all** (in 5 files) |

  robotcode itself reports only errors by default.
- **The gates are cheap:**
  - **Robocop via its Python API:** **0.04 s per file** with its persistent cache.
  - **robotcode analyzer in-process:** **16 ms** per 100-line file, about 0.1 ms per line, once its library cache is warm.
  - **CLI start-up:** 0.5–1.4 s per call.
  - **Output:** about 60–90 tokens per file with errors in compact format.
- **Bugs caught in `build_test_suite`:**
  - **Bug A, current in v0.36.0.** Arguments that are empty or whitespace-only (empty string, single space, no-break space U+00A0) are written raw. Robot Framework then drops them or merges them into the separator. Found by Robocop `ARG08` in a real rf-mcp carconfig run saved byte-for-byte via `output_path`, and reproduced in-process. Static analysis catches the resulting **wrong argument count** (Robocop ARG08, robotcode `DataError`, dryrun). It does **not** catch the **silent semantic change**: `Catenate  SEPARATOR=  a  ' '  b` turns `a b` into `ab`. Only a runtime assertion exposes that.
  - **Bug B, a corrupted-suite trap on the save path.** When an agent saves the returned `rf_text` with RF's `Create File` keyword (through rf-mcp's own `execute_step`), RF resolves `${var}` to the variable's value and expands `\n`. The suite becomes unparseable and its assertions become tautologies (`Should Be Equal  Hello, Robot!  Hello, Robot!`). `build_test_suite` itself renders correctly and `output_path` writes byte-identical text, both re-verified. But nothing in rf-mcp stops the bad save path. Robocop found **two real corrupted suites** this way: file-proc with 52 findings, cc-web with 2. On the reproduced file, Robocop reports 29 findings and robotcode analyze 16 errors. **`robot --dryrun` misleadingly reports the real test as PASS** and fails only on phantom "tests" built from data lines.
- **Recommendation: add a static-analysis quality gate to rf-mcp:**
  - **`build_test_suite`:** run both checks on the rendered text before returning or writing it. Return diagnostics with line numbers, auto-fix only deprecated syntax, and block writing on errors.
  - **`run_test_suite`:** run both checks before `--dryrun`, and add analyze + Robocop to `mode="dry"`.
  - **Writing RF content with `Create File`:** refuse or warn when `execute_step("Create File", …)` writes RF suite content.
  - **Agent-written files:** a post-edit hook running the same checks.
  - **Bug A:** fix the escaping (`${EMPTY}`, `${SPACE}`, `\xa0`, …).

  Details are in §7 and §10.

---

## 2. Why rf-mcp needs this

**rf-mcp validates by execution:**
- `execute_step` runs keywords in a live RF context. Element pre-validation and error hints help only when a step fails at runtime.
- `build_test_suite` renders recorded steps into a `.robot` file without validating the result.
- `run_test_suite(mode="dry")` runs `robot --dryrun`. That's a solid check for keyword existence, argument count and type conversion, but it misses undefined variables and outdated syntax. Its error report is coarse (§5.4).

That leaves three classes of defects:

1. **Defects in files the agent writes itself** (resources, user keywords, hand-edited suites). The agent writes these with its own file tools, outside rf-mcp's step pipeline. Nothing checks them until a full run.
2. **Defects introduced while rendering or persisting a suite** (Bug A, Bug B). The steps passed live, so the agent believes the suite is good.
3. **Mistakes runtime hints don't cover.** In round 1, **11 of 44** realistic agent mistakes got **no hint** from rf-mcp (also none from the same rules applied to robotcode output). Several of them are static defects these gates catch before running:

   | Mistake (no rf-mcp hint today) | robotcode analyze | Robocop agent profile |
   |---|---|---|
   | Wrong argument count (`Fill Text` without text, `Should Be Equal` with 1 arg) | yes (`DataError`, with expected range) | yes (ARG08) |
   | Variable-name typo (`${usernme}`) | **yes** (`VariableNotFound`) | no |
   | Old `:FOR` syntax | yes (explains the old syntax) | generic KW05 / parsing error |
   | Unknown named argument | yes | no |

---

## 3. Tools evaluated

| Tool | What it is | Needs installed libraries? | Interfaces |
|---|---|---|---|
| **robotcode analyze** (`robotcode analyze code`) | Static analyzer of the robotcode language server: syntax/model errors, keyword resolution, argument checks, variable resolution, imports | Yes; resolves real library signatures | CLI (`--format json`, `--output-format json/sarif/github/gitlab`, bitmask exit codes), in-process `CodeAnalyzer`, LSP diagnostics |
| **Robocop 9** (`robocop check`) | Linter + formatter (198 rules, 74 auto-fixable). **New project rules** (disabled by default) import libraries: KW05 keyword-not-found, ARG08 invalid-argument-count, KW06 ambiguous keyword, IMP07/IMP09 unresolved imports | Only for the project rules (`analyze_libraries`) | CLI, Python API `robocop.run.check_files(return_result=True)`, JSON/SARIF/GitLab reports, `--fix`, robotcode LSP integration |
| **`robot --dryrun`** (rf-mcp's current gate) | Robot Framework runs the suite without executing library keywords | Yes | CLI |

---

## 4. Method

| Corpus | Content | Purpose |
|---|---|---|
| Round-1 static corpus | 33 planted errors + 15 valid controls, agent-style Browser/Requests/BuiltIn/user-keyword/BDD/embedded-arg/FOR/IF files | Detection per error class, false positives |
| Outdated / incorrect syntax corpus | 28 cases: 7 deprecated-but-running constructs, 13 real errors, misc | Deprecation detection, auto-fix safety |
| Real agent suites ("noise corpus") | 36 suites: earlier rf-mcp experiment runs (MiniMax/Claude/Kilo agents), A/B eval outputs, rf-mcp e2e test suites, stepwise recordings | Noise of each rule set, real defects found |
| Generated suites | s01 (real rf-mcp-generated), s02, s03 (Browser BDD with 6 planted static errors) | Gate quality on `build_test_suite`-style output |
| Repros (this report) | In-process rf-mcp v0.36.0: `execute_step` → `build_test_suite(output_path)`, plus the `Create File` save path; whitespace/empty-argument steps | Confirm and characterise Bug A / Bug B |

Every number below comes from these runs; the evidence paths are in Appendix A.

---

## 5. Results

### 5.1 Detection by error class (33 planted errors)

| Error class | Robocop default | Robocop agent profile | robotcode analyze | `robot --dryrun` |
|---|---|---|---|---|
| Keyword typo, single-space separator, wrong `Lib.` prefix, missing import, wrong library (e.g. Browser kw with only SeleniumLibrary) | no | yes (KW05) | yes (`KeywordNotFound`) | yes |
| Argument count (BuiltIn, Browser, Requests `Create Session`, user kw, keyword-only) | no | yes (ARG08) | yes (`DataError`) | yes |
| Unknown named argument | no | **no** | yes | yes |
| Undefined variable, unclosed `${` | no | **no** | **yes** | **no** |
| Ambiguous keyword (two libraries) | no | yes (KW06) | yes (`MultipleKeywords`) | yes |
| Bad embedded-argument call | no | yes | yes | yes |
| FOR / IF / RETURN / setting / section / empty test syntax | yes (ERR*, NAME16, LEN05) | yes | yes | yes |
| Unresolved resource; library not installed / bad init args | no | yes (IMP07/IMP09, incl. init args) | init args flaky (cache trap G2, §8) | yes |
| Enum / int argument conversion (e.g. Browser `AssertionOperator`) | no | no | **no** | **yes** |
| Duplicate test name | yes (DUP01) | yes | no | warning only |
| `* On Session` missing URL (`*args, **kwargs`) | no | no | no | no |
| **Caught** | **8** | **26** | **28** | **30** |
| False positives on 15 valid controls | 0 errors (3–6 DOC/SPC warnings per file) | 1 (in-body search order) | 3 | 0 |

**Combined:** agent profile + analyze = **30/33**; + dryrun = **32/33**.

**Where the tools differ in correctness:**
- **Library priority.** Robot Framework prefers a custom library over a standard one. robotcode reported `Take Screenshot` (Browser + Screenshot both imported) as ambiguous **3 times in real suites**, although RF runs it fine. Robocop was correctly silent.
- **Keyword names containing a variable** are skipped by Robocop. So `Should Be Equal ${a}` written with single spaces is missed by Robocop and caught by robotcode.
- **Robocop "fails open".** When a library fails to import, KW05/ARG08 go silent for every file importing it; you only get IMP09.

### 5.2 Outdated syntax and auto-fix (28-case corpus)

| Group | Robocop agent profile | robotcode analyze | `--dryrun` | `robocop check --fix` |
|---|---|---|---|---|
| Deprecated but still runs (7): `Run Keyword If/Unless`, `[Return]`, `Exit/Continue For Loop (If)`, `WITH NAME`, `Force/Default Tags`, singular headers, `Return From Keyword` | **7/7** | 4/7 | runs (warnings only) | **7/7 repaired, all fixed files run clean** |
| Real errors (13) | 12 | 13 | fails 12 | 4 repaired safely: `...arg` without separator, `[Documentation]text`, `VAR ${y}=2`, lowercase `else` |

- **The hard deprecation cases are rewritten correctly:** `${r}=  Run Keyword If … ELSE …`, ELSE IF chains, `Run Keywords … AND …`. An assigned `Run Keyword Unless` gets an `ELSE` that sets `${None}`.
- **The lowercase `else` trap:** `IF … else …` makes `else` a keyword call. The real run **passes silently**, because the else branch becomes dead code. Robocop's NAME09 flags it and `--fix` repairs it.
- **One unsafe "safe" fix:** SPC22 turns a typo'd `Test Setupp    Log` into `Test Setup    p    Log`. The agent profile marks SPC22 `unfixable`.
- **`robocop format`** is semantically safe (error counts unchanged) but rewrote all 37 noise files (715 changed lines). **Don't run the formatter after every generation or edit**; use targeted `--fix` only.

### 5.3 Generated suites

| Suite | robotcode analyze | `robot --dryrun` | rf-mcp `run_test_suite(mode="dry")` |
|---|---|---|---|
| s03 (Browser BDD, 6 planted static errors) | **6/6 with `line:col`** | 4/6: misses `${usrname}` and `Clik` inside a keyword the run never reaches | **2 unique errors, no line numbers** |
| s01 (real rf-mcp-generated), s02 | clean | clean | clean |

### 5.4 Noise on real suites (36 agent-written / rf-mcp-generated suites)

| Rule set | Findings | Notes |
|---|---:|---|
| Robocop default | 609 | 465 warnings: line length, blank lines, unused variables, DEPR05/06 ("use VAR"), docs |
| Built-in `robocop:minimal` | 95 | mostly VAR02/VAR03 |
| **Agent profile** | **63** | in 5 files, **all real problems** |
| robotcode analyze | errors only by default | caught `${greeting}` never assigned, which Robocop missed |

**The 63 agent-profile findings were real defects:**
- **Two corrupted rf-mcp suites (Bug B):** file-proc (52 findings) and cc-web (2 × KW05).
- **A `build_test_suite` argument-escaping defect (Bug A):** web-carconfig, ARG08.
- **An agent working around the Browser library:** it drove an iframe with `Execute JavaScript` and `contentDocument`, so its Browser keywords went unused (ARG08/KW05 on the misuse).
- **Unused `[Arguments]`** pointing at typo'd variables.

DEPR05/06 ("use VAR instead of Set Variable/Create List") are excluded from the agent profile on purpose. That code is valid RF 7, and flagging it makes agents rewrite working steps.

### 5.5 False positives and how to suppress them

These show up mostly in files built step by step, where variables are created at runtime:

| Pattern | Static result | Suppression |
|---|---|---|
| `${x}=` assigned earlier in the same test, `VAR … scope=TEST/SUITE`, BDD prefixes, embedded-arg resource keywords, `${resp.json()}[0][id]` | clean | – |
| `Set Test/Suite Variable  ${x}` then using `${x}` | FP (VariableNotFound) | write `VAR … scope=…` (Robocop DEPR05 suggests the same); or filter against the live session |
| Variable set inside a resource keyword or a called keyword | FP | filter against the live session |
| Variable passed only with `-v` / robot.toml | FP | put it in `robot.toml [variables]` or pass it to the analyzer (`-v`) |
| In-body `Set Library Search Order` (Browser + Selenium `Get Text`) | FP (MultipleKeywords) | `global-library-search-order` in a robot.toml profile, or qualified names |
| `Get Variable Value  ${maybe}` / `Variable Should Exist` | FP | inline `# robotcode: ignore[VariableNotFound]` **on the same line** |

- **Comment placement matters.** An `# robotcode: ignore[...]` on its **own line** silences *every following line* until a `reset` comment; in testing it hid a real typo.
- **Don't ignore globally.** Ignoring `VariableNotFound` in robot.toml also hides real undefined variables.
- **rf-mcp can fix these better than an LSP.** It owns the live session, so it can drop any diagnostic for a variable or keyword that **exists in the live session right now**. That "live filter" removed **5/5** dynamic-variable false positives in the file-based step prototype.

### 5.6 Cost

| Operation | Latency | Output |
|---|---|---|
| robotcode analyze CLI, single file, warm | 0.8–1.4 s (almost all process start-up; analysis itself 40–80 ms) | ~90 tokens with errors, ~20 clean (concise) |
| robotcode analyze CLI, cold (library load) | 3–7 s | – |
| robotcode analyzer **in-process** (100-line file) | **16 ms** (about 0.1 ms per line; first check ~170 ms with warm library cache, 2.6–5 s cold); about 7.5 MB extra memory | structured diagnostics |
| Robocop CLI, agent profile | 0.54–0.60 s with cache (0.95 s without) | compact format ~60 tokens for 3 issues |
| Robocop CLI with project rules on a 37 / 181-file project | 2.0 s / 2.3 s cold, 0.65 s / 0.82 s cached (**lints the whole project root**, so filter to the target file) | 7 KB / 31 KB |
| Robocop **Python API**, agent profile | **0.04 s per call** with persistent cache (0.25 s without); one-time import 0.3 s | – |
| `robot --dryrun` | process start-up + library load (not separately benchmarked) | – |

Output formats: Robocop compact `--issue-format "{source}:{line}:{col} {rule_id} {desc}"` is 238 B for 3 issues, JSON 938 B, SARIF 117 KB. robotcode JSON for the 48-file corpus: 12 KB, concise 4.7 KB, SARIF 46 KB.

### 5.7 Which tool for which defect

| Defect type | Best gate |
|---|---|
| Undefined variable, named-argument name, unexecuted keyword bodies, precise ranges | **robotcode analyze** |
| Outdated syntax (+ safe auto-fix), lowercase `else`, duplicate tests, library-priority correctness, bad library init args | **Robocop agent profile** |
| Enum/int conversion, library init args, runtime import paths | **`robot --dryrun`** |
| Silent semantic change (e.g. whitespace argument merged into separator), wrong locator, wrong business value | none of them → runtime assertions / rf-mcp execution |

---

## 6. Bugs caught in `build_test_suite`

### 6.1 Bug A: empty and whitespace-only arguments are written raw (current, v0.36.0)

**How it was found.** Robocop's agent profile flagged `ARG08 Replace String expects 3 to 4 arguments but 1 provided` in a real rf-mcp-generated carconfig suite (`experiments/web-carconfig/carconfig.robot`). The agent had saved that suite with `build_test_suite(output_path=…)`, which writes `rf_text` byte for byte. So the defect is in `build_test_suite`'s rendering, not in the save path.

```text
${updated_total_normalized} =    Replace String    ${updated_total}    <U+00A0>    <space>
```

The search argument was a **no-break space** (carconfig prices are formatted `82.400,00 €`), the replacement a plain space. Both are written raw. Robot Framework strips cell values and treats whitespace runs as separators, so both arguments vanish.

**Reproduced in-process against v0.36.0** (`execute_step` → `build_test_suite(output_path)`; script `experiments/robotcode-remote/build_suite_bugs/repro_ws.py`). All steps passed live; the rendered suite is:

```robot
${price} =    Set Variable    61.000,00 €                  # U+00A0 kept inside the value: fine
${price_norm} =    Replace String    ${price}    <U+00A0>    <space>   # both args lost
Should Be Equal    ${price_norm}    61.000,00 €
${no_cents} =    Replace String    ${price}    ,00    <empty>          # empty replacement lost
Should Be Equal    ${no_cents}    61.000 €
${joined} =    Catenate    SEPARATOR=    a         b                   # ' ' merged into the separator
Should Be Equal    ${joined}    a b
Should Be Equal    \#notacomment    \#notacomment                      # leading '#' is escaped correctly
```

| Gate | Result on the rendered suite |
|---|---|
| Robocop agent profile | **ARG08** ×2: `Replace String expects from 3 to 4 arguments but 1 provided` / `… 2 provided` |
| robotcode analyze | **2 errors**: `Keyword 'String.Replace String' expected 3 to 4 arguments, got 1.` / `got 2.` |
| `robot --dryrun` | FAIL with the same two messages |
| `robot` (real run) | FAIL at the first `Replace String` |
| **`Catenate … a ' ' b` → `ab`** | **not detected by any static gate.** It's a valid call with different semantics; only the following `Should Be Equal … a b` would expose it at runtime |

**Likely root cause.** The `.robot` text generator escapes `#`, but has no rule for arguments that are empty, whitespace-only, or start or end with whitespace (including U+00A0 and other Unicode spaces).

**Fix.** Render such arguments with RF escapes:
- `''` → `${EMPTY}`
- `' '` → `${SPACE}`
- `'  '` → `${SPACE * 2}`
- U+00A0 → `\xa0`
- leading or trailing spaces → `\` + space or `${SPACE}`

Add a unit test with exactly the cases above. Re-parse the rendered text with `robot.api.get_model` and compare the argument tuples to the recorded steps. That round-trip check would catch this whole class, including the `Catenate` case that static analysis cannot.

### 6.2 Bug B: saving with RF's `Create File` corrupts the suite (file-proc, cc-web)

**How it was found.** The agent profile reported **52 findings** (DUP01, LEN05, KW05, ARG08) on `experiments/file-proc/fileproc/suite.robot` and **KW05 ×2** on `experiments/cc-web/suite.robot`. Both came from July rf-mcp experiment runs.

```robot
    Create File    /artifacts/fileproc/report.txt    line1
line2
line3
    line1
line2
line3
line4 =    Get File    /artifacts/fileproc/report.txt
    Should Contain    line1
line2 …
```

```robot
    RF-MCP Lab =    Get Title
    Should Be Equal    RF-MCP Lab    RF-MCP Lab         # tautology: can never fail
    Hello, Robot! =    Get Text    id=result
    Should Be Equal    Hello, Robot!    Hello, Robot!
```

**Root cause, re-verified.** The July findings (F1) first blamed `build_test_suite`. The corruption actually happens when the agent **saves** `rf_text` with RF's `Create File` keyword through `execute_step`. RF resolves `${file_content}` / `${title}` to their values and expands `\n` into newlines. The re-run with v0.36.0 (script `build_suite_bugs/repro_f1.py`) confirms this:
- `build_test_suite` returns correct text (`line1\nline2\nline3`, `${file_content} =    Get File …`, `Should Contain    ${file_content}    line1`).
- `output_path` writes it **byte-identically**.
- Saving that same text with `execute_step("Create File", [path, rf_text])` reproduces the corrupted file-proc suite **exactly**.

| Gate | `build_test_suite` output (`output_path`) | Same text saved via `Create File` |
|---|---|---|
| Robocop agent profile | 0 | **29** (DUP01 ×13, LEN05 ×11, KW05 ×3, ARG08 ×2) |
| robotcode analyze | 0 errors | **16 errors** (`Test cannot be empty`, `No keyword with name 'line4' found`, …) |
| `robot --dryrun` | 1 test PASS | 19 "tests": **the real test PASSES**, 16 phantom tests built from data lines fail |
| `robot` (real run) | PASS | phantom tests fail |

**Why it still matters:**
- rf-mcp's current mitigation is the `output_path` parameter plus a WORKFLOW GUIDE warning ("NEVER write the returned rf_text via the Create File keyword"). It's only guidance; `execute_step` still executes the destructive save.
- The **cc-web variant is the dangerous one.** If the resolved values had been valid RF tokens, the result would be a suite that parses and **always passes** (`Should Be Equal  X  X`).
- `--dryrun` is the wrong detector here: it reports the real test as passing.

**Fixes (any one helps, all three together are robust):**
1. In `execute_step`, refuse or warn on `Create File` / `Append To File` when the content looks like RF suite text (`*** Settings ***`, `*** Test Cases ***`). Point to `build_test_suite(output_path=…)`.
2. Have `build_test_suite` run the quality gate (§7) and return the diagnostics, so a later corrupted copy can be told apart from the validated original.
3. Add a robocop-style tautology check (`Should Be Equal` with two identical literal arguments) to rf-mcp's own suite-quality checks. Robocop has no such rule.

### 6.3 Other `build_test_suite` observations (lower severity)

| Observation | Source | Note |
|---|---|---|
| Generic auto documentation: `[Documentation]  Test case that verifies result, verifies result, verifies result.` | repro (v0.36.0) | cosmetic; misleads readers |
| Misleading generated comments: `Should Contain  ${file_content}  line1    # Verify page contains '${file_content}'` (not a page) | repro | cosmetic |
| `execute_step` warns `Keyword 'Get File' may not return a useful value for assignment` (false: it returns the content) | repro | false heuristic warning |
| The builder ignores each step's recorded `resolved_library` and asks the live namespace instead | code reading (host-dependency map) | risk of wrong imports/prefixes when the namespace changed |
| Legacy (single-test) mode does not copy `bdd_group`/`bdd_intent` into step dicts, so explicit BDD grouping only works in multi-test mode | code reading | unverified at runtime |
| Steps executed via the attach bridge are never recorded | code reading | `build_test_suite` can't see them |

---

## 7. Integrating the gates into rf-mcp

### 7.1 Where the gates go

```
agent ─ execute_step ──▶ live RF context ──▶ recorded steps
                                              │
build_test_suite ──▶ render rf_text ──▶ [GATE] Robocop agent profile (in-process, 0.04 s)
                                              + robotcode analyzer (in-process, ~16 ms warm)
                                              + live filter (drop diagnostics for vars/keywords alive in the session)
                                              ├─ safe auto-fix: DEPR03/04/07/08/09/10/11, NAME09 only
                                              ├─ errors → returned with line:col + rule ids (block output_path write, or write + flag)
                                              └─ round-trip check: get_model(rf_text) args == recorded args   (catches Bug A incl. Catenate)
run_test_suite ──▶ [GATE] same checks ──▶ robot --dryrun ──▶ robot
execute_step("Create File", <RF suite text>) ──▶ refuse/warn → build_test_suite(output_path)  (Bug B)
agent-written .robot/.resource ──▶ post-edit hook (same checks, errors only)            (optional)
```

### 7.2 Response shape (suggested)

```json
{
  "success": true,
  "rf_text": "...",
  "quality": {
    "status": "errors",
    "robotcode": [{"line": 12, "col": 22, "code": "DataError",
                   "message": "Keyword 'String.Replace String' expected 3 to 4 arguments, got 2."}],
    "robocop":   [{"line": 12, "col": 22, "rule": "ARG08", "message": "..."}],
    "autofixed": [{"rule": "DEPR08", "line": 31, "message": "Run Keyword If → IF"}],
    "roundtrip_mismatches": [{"step": 6, "keyword": "Catenate", "recorded": ["SEPARATOR=", "a", " ", "b"],
                              "rendered": ["SEPARATOR=", "a", "b"]}]
  }
}
```

That's about 60–90 tokens per finding in compact form. Return only errors, plus warnings that map to real failures.

### 7.3 Implementation notes

- **Dependencies:** rf-mcp has neither Robocop nor robotcode today; it only uses `robot --dryrun`. Add both as an optional extra (e.g. `rf-mcp[quality]`), and fall back to `--dryrun` when they're absent.
- **In-process APIs:**
  - **Robocop:** `robocop.run.check_files(return_result=True)` with a persistent `.robocop_cache`.
  - **robotcode:** its analyzer internals (`CodeAnalyzer` / `DocumentsCacheHelper`) are undocumented, so pin `robotcode>=2.7,<2.8` behind an adapter, or use the `robotcode analyze code --format json` CLI (about 1 s).
  - Scripts that import the robotcode analyzer need an `if __name__ == "__main__"` guard, because robotcode loads libraries in spawned processes.
- **Project root and paths:** analyze files **inside** the project root and not in hidden or git-ignored folders (traps G1/G3). Pass `-r <root>` and absolute paths. Write the temporary suite to a visible project subfolder, not `.rf/` or `/tmp`.
- **Variables and search order:** give the analyzer the session's suite variables (`-v` or a generated robot.toml overlay with `extend-variables`) and its search order (`global-library-search-order`). This removes the dynamic false positives in §5.5.
- **Robocop project rules lint the whole project root,** even when you pass one file. Filter results to the target file.
- **Auto-fix policy:**
  - Apply only the deprecation fixes and NAME09.
  - Never apply SPC22, and never run `robocop format` on generated output.
  - Always re-check after a fix.
- **Severity mapping:** treat robotcode errors and Robocop `[E]` as blocking for `output_path`; return everything else as advisory.

### 7.4 Robocop "agent profile"

The profile is in `experiments/robotcode-remote/build_suite_bugs/robocop-agent.toml` (also `round3/robocop/configs/robocop-agent.toml`). Excerpt:

```toml
[tool.robocop]
analyze_libraries = true            # project rules import libraries (executes their code)

[tool.robocop.lint]
select = [
  "ERR*", "ARG05", "DUP01", "DUP02", "DUP03", "DUP09", "LEN05", "LEN15", "LEN16", "LEN17", "LEN21",
  "MISC08", "NAME09", "NAME10", "NAME11", "NAME16", "SPC14", "SPC16", "SPC17", "SPC19", "SPC20", "SPC21", "SPC22",
  "KW05", "KW06", "ARG08", "IMP07", "IMP09",                                  # project semantics
  "DEPR03", "DEPR04", "DEPR07", "DEPR08", "DEPR09", "DEPR10", "DEPR11",       # outdated syntax (safe --fix)
  "VAR11", "VAR13", "MISC10", "ARG01",
]
unfixable = ["SPC22"]   # its "safe" fix corrupts typo'd settings (verified)
configure = ["ARG01.severity=I", "DEPR11.severity=W", "IMP09.severity=E", "IMP07.severity=E",
             "KW06.severity=E", "SPC17.severity=W"]
```

Deliberately excluded: DOC*, naming conventions, lengths and line length, blank lines and trailing whitespace, tags, and DEPR05/06.

### 7.5 Files agents write themselves: hooks beat an LSP today

- **The robotcode language server gives the same diagnostics** (48/48 codes identical to `analyze`, plus full keyword docs on hover in 3–6 ms). But it **doesn't work as-is in coding agents**:
  - Claude Code sends whole-file changes the server silently drops, then discards its stale diagnostics.
  - OpenCode labels `.robot` files as plaintext and treats robotcode's empty on-demand answer as final.
  - Copilot CLI never starts the server on edits.
  - Codex has no LSP support at all.

  A small shim fixes Claude and OpenCode (raw 0/2 → shim 2/2 fixed). The stock server also takes **1.3 s** per change because of a 1 s idle poll (74 ms when patched).
- **Recommended instead: a post-edit hook** running `robotcode analyze code --severity error` plus the Robocop agent profile on edited `*.robot`/`*.resource` files. It's synchronous (about 0.9 s warm), reports errors only, costs about 90–200 tokens per firing, and worked in **all 4 valid hook runs** (Claude, Codex ×2, Copilot):
  - **Claude:** `.claude/settings.json` PostToolUse with matcher `Edit|Write|MultiEdit`, returning `hookSpecificOutput.additionalContext`.
  - **Codex:** `config.toml` `[[hooks.PostToolUse]] matcher="apply_patch|Edit|Write"`. Hooks must be trusted (`/hooks`, or `--dangerously-bypass-hook-trust` headless).
  - **Copilot CLI:** plugin `hooks/hooks.json` with top-level `{"additionalContext": …}`. Repository `.github/hooks` didn't run in `-p` mode.
  - **OpenCode:** a `tool.execute.after` plugin (prototype only).
- **Not every model acts on the feedback.** Codex fixed all planted errors after the hook text; MiniMax-M2.7 received the text and left 2 errors.

---

## 8. Pitfalls and silent traps (all verified)

| Tool | Trap | Effect | Workaround |
|---|---|---|---|
| robotcode | **G1**: files outside the project root, in hidden or git-ignored folders (e.g. `.rf/`) are skipped | `Files: 0`, exit 0, so a broken file "passes" | check `summary.files`; keep checked files in visible project folders |
| robotcode | **G2**: library cache keyed by module, not arguments | a bad init argument is hidden once a valid import is cached | use dryrun or Robocop IMP09 for init arguments |
| robotcode | **G3**: picks the project root from the path arguments and `chdir`s there | wrote a file to the wrong place once | always `-r <root>` + absolute paths |
| robotcode | `# robotcode: ignore[...]` on its own line | silences every following line until `reset` | put it on the same line |
| robotcode LSP | full-text `didChange` without range is dropped; pull diagnostics returns `[]` | no feedback | shim, or hooks |
| Robocop | `--select A,B` (comma) | selects **nothing**, "No issues found", exit 0 | repeat the flag or use the config file |
| Robocop | a `--config` file not named `robocop.toml` without `[tool.robocop]` tables | whole file ignored | name it `robocop.toml` or use `[tool.robocop]` |
| Robocop | git-ignored resource files dropped from project analysis | KW05/ARG08 silent | `--skip-gitignore` |
| Robocop | a library fails to import | KW05/ARG08 silent for all importing files ("fails open") | treat IMP09 as blocking |
| Robocop | project rules lint the whole project root | slow output for large projects | filter to the target file; `--ignored-library` for heavy libraries |
| Robocop | upstream pre-commit hook runs in an isolated env | IMP09 noise; KW05/ARG08 skipped | local `language: system` hook in the project venv |
| `--dryrun` | corrupted suites (Bug B) | the real test shows PASS | always run the static gate as well |

---

## 9. Limitations

- **Corpus size.** 33 + 28 planted cases and 36 real suites; the cases were planted by us and the gold set is small. More real-world suites would sharpen the noise numbers.
- **Library coverage.** Browser, RequestsLibrary, SeleniumLibrary (partial), BuiltIn, Collections, String, OperatingSystem. Not tested: AppiumLibrary, DatabaseLibrary, PlatynUI.
- **Effect on agent success not isolated.** In the round-1 A/B (180 sessions), the skill + local-package arm included these hooks (about 2 firings per session). That arm scored 0.92 vs 0.97 for current rf-mcp (not significant), but the hooks' own contribution was not measured separately. A focused A/B is still to do: rf-mcp with vs without the `build_test_suite` gate, and agent hooks on vs off.
- **Static analysis can't see runtime semantics:** wrong locators, wrong business values, timing, and silent argument changes like `Catenate`. Keep runtime execution, assertions and the round-trip check in §6.1.
- **Internal APIs.** robotcode's in-process analyzer API is internal (pin it). Robocop's project rules execute library code during analysis.

---

## 10. Recommendations (prioritised)

| Priority | Action | Effort | Catches |
|---|---|---|---|
| **P0** | Fix **Bug A**: escape empty, whitespace-only and leading/trailing-whitespace arguments (incl. U+00A0) in the `.robot` generator; add unit tests | small | lost and merged arguments in generated suites |
| **P0** | Add a **round-trip check** to `build_test_suite`: re-parse `rf_text` with `robot.api.get_model` and compare the arguments with the recorded steps | small | the whole rendering-defect class, incl. silent semantic changes |
| **P0** | Guard **Bug B**: `execute_step` refuses or warns on `Create File`/`Append To File` with RF suite content and points to `build_test_suite(output_path)` | small | corrupted and tautological suites |
| **P1** | Add the **static quality gate** to `build_test_suite` and `run_test_suite(mode="dry")`: Robocop agent profile + robotcode analyze (in-process when installed, CLI otherwise), live filter, line-numbered diagnostics, safe deprecation auto-fix | medium | +2 of 33 planted errors over dryrun alone (32 vs 30: undefined variable, keyword typo in an unexecuted body), plus outdated syntax (7/7 vs warnings only), lowercase `else`, precise ranges, auto-fixed deprecations |
| **P1** | Ship the **Robocop agent profile** and a robot.toml template (variables, search order, python-path) with rf-mcp | small | low-noise, high-value rule set |
| **P2** | Offer **post-edit hooks** for agent-written files (installer writes them per agent) | medium | defects in files rf-mcp never sees |
| **P2** | Extend rf-mcp's runtime **hint rules** with the analyzer's messages for the 11 hint-less mistakes (arg count, variable typos, named args, old `:FOR`) | small | better recovery when the static gate was skipped |
| **P3** | Report upstream: robotcode G1/G2, LSP full-document sync / language id / pull diagnostics, the 1 s diagnostics poll; Robocop `--select` comma parsing and a tautological-assertion rule | – | ecosystem fixes |
| **P3** | Run a focused A/B: rf-mcp with vs without the gate and hooks | medium | quantifies the gate's effect on agent success |

---

## Appendix A: Evidence and reproduction

All paths are relative to `~/workspace/rf-mcp-robotcode/experiments/robotcode-remote/` unless absolute. This folder is in the repository's `.git/info/exclude`; commit it with `git add -f`.

| Topic | Evidence |
|---|---|
| Static detection corpus, robotcode analyze vs dryrun, generated suites, traps G1–G3 | `static/findings.md`, `static/corpus/`, `static/outputs/` (`detection_matrix.md`, `suites_analyze.*`, `suites_dryrun.txt`) |
| Robocop detection, deprecation/auto-fix corpus, noise corpus, agent profile, hooks | `round3/robocop/findings.md`, `round3/robocop/{corpus1,corpus2,noise_corpus,configs,scripts,out}/` |
| robotcode LSP quality, false positives, in-process analyzer, live filter | `round3/lsp_quality/findings.md`, `round3/lsp_quality/results/summary.json` |
| LSP and hooks in coding agents | `round3/agent_lsp/findings.md`, `round3/agent_lsp/{shim,hooks}/`, `round3/agent_lsp/runs/` |
| Round-1 hint coverage (11/44 without hints) | `hints/findings.md`, `hints/results/coverage.md` |
| Bug A and Bug B repros (v0.36.0) | `build_suite_bugs/repro_ws.py`, `build_suite_bugs/repro_f1.py`, `build_suite_bugs/out/{ws_suite,suite_output_path,suite_via_create_file}.robot`, `build_suite_bugs/robocop-agent.toml` |
| Original corrupted suites | `~/workspace/rf-mcp/experiments/file-proc/fileproc/suite.robot`, `~/workspace/rf-mcp/experiments/cc-web/suite.robot`, `~/workspace/rf-mcp/experiments/web-carconfig/carconfig.robot`; July diagnosis in `~/workspace/rf-mcp/experiments/FINDINGS.md` (F1) |
| A/B context | `ab/findings.md` (round 1); live round in `ab/harness/results_live.jsonl` (in progress at time of writing) |

**Reproduce the bug repros:**

```bash
cd ~/workspace/rf-mcp-robotcode
uv run --no-sync python experiments/robotcode-remote/build_suite_bugs/repro_ws.py /tmp/ws    # Bug A
uv run --no-sync python experiments/robotcode-remote/build_suite_bugs/repro_f1.py /tmp/f1    # Bug B

# gate a suite (robotcode-experiments venv has robocop 9.1 + robotcode 2.7)
V=~/workspace/robotcode-experiments/.venv/bin
$V/robocop check --config robocop.toml -c print_issues.output_format=simple \
   --issue-format "{source}:{line}:{col} {rule_id} {desc}" tests/
$V/robotcode -r "$PWD" analyze code --severity error tests/
$V/robot --dryrun --output NONE --report NONE --log NONE tests/
```

## Appendix B: Relation to the robotcode / skill direction

The same gates apply unchanged in the "Agent Skill + local package + robotcode" architecture explored on this branch. There they run inside the local helper, before executing file-based steps (in-process analyzer + live filter, 85 ms per step including the check), and as post-edit hooks. The helper is the one place no step can bypass. So whichever architecture rf-mcp takes, **the quality gate is valuable and portable**, and the P0 fixes for Bug A and Bug B belong in rf-mcp's current code base either way.
