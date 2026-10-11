# Static validation, keyword discovery and results via robotcode — findings (2026-10-01)

Source: static subagent report (saved by the coordinating session; the harness blocks subagent report files). Evidence: `scripts/`, `corpus/` (48 cases + 5 suites), `outputs/` (raw JSON, tables, script-generated `outputs/detection_matrix.md`).

## Verdict
- **Static validation**: use `robotcode analyze code` **plus** `robot --dryrun`, not either alone. 33 planted errors: analyze 28, dryrun 30 (what rf-mcp uses today), **both 32**. Only miss: `POST On Session` without url (runtime-only; signature `*args, **kwargs`). analyze adds undefined/unclosed variables, line:col ranges, and checks keyword bodies never executed; dryrun adds type conversion (Browser `AssertionOperator` enum, int), library init args, duplicate test names.
- **Works on a remote server without the libraries**: client uploads `libdoc --format JSON --specdocformat RAW` once; `scripts/spec_to_stub.py` turns each spec into a signature-only stub library; a bare venv with only RF 7.5 + robotcode runs analyze and dryrun. analyze identical to real libraries 47/48 (the 48th: stubs caught an error the real run missed); typed-stub dryrun matched 48/48 incl. enum check, 0.053 s/case in-process.
- **Keyword search**: robotcode matches names only (`.kw post json`, `.kw wait until visible` → "No keywords found"). Server-side BM25 + model2vec over uploaded specs: 551 keywords indexed in 0.6 s, ~1.3 ms/query, ranking ≈ rf-mcp `find_keywords` (0.3–0.9 s, 3–7 KB/call). rf-mcp's catalog already uses `LibraryDocumentation()`, which also loads JSON specs.
- **Results**: `robotcode results` gives more failure detail than `run_test_suite` at ~0.95 s/call. `summary --failed` 0.5–1.6 KB; `log --failed` 2.8–5.6 KB with keyword tree, args as written, full HTTP request/response, screenshot paths (`--extract` copies them). rf-mcp standard output 2.4 KB, names only failing keyword + message.

## Key numbers
- analyze latency: warm single step 0.8–1.4 s (≈ all process start; analysis 40–80 ms); cold 3–7 s; 48-file corpus 14–20 s cold / 2–5 s warm; `--cache-namespaces` no difference at this size.
- analyze output: ~90 tokens for a step with errors, ~20 clean. Corpus: 12 KB JSON, 4.7 KB concise, 46 KB SARIF.
- Spec sizes RAW/gzip: Browser 818/108 KB, Selenium 402/42, Requests 88/8, BuiltIn 370/42.
- Language-server daemon: warm diagnostics 0.05–0.5 s, but completion payloads 600 KB and push semantics fiddly.

## Traps that make a broken step look clean
- **G1**: files outside the project root, in hidden or git-ignored dirs are skipped (`Files: 0`, exit 0) → check `summary.files`.
- **G2**: library cache keyed by module, not args → bad init arg (`Library Collections extra_arg`) hidden once a valid import is cached.
- **G3**: robotcode picks project root from path args and `chdir`s there (once wrote a file to the wrong place) → always `-r` + absolute paths.
- False positives: dynamic `Set Test/Suite Variable` and in-body `Set Library Search Order` not understood → fix with `-v`, session profile `extend-variables`, or `global-library-search-order` in a merged `-c` overlay.

## Detection by error class (analyze / dryrun)
| Class | analyze | dryrun |
|---|---|---|
| keyword typo, single-space separator, wrong `Lib.` prefix | yes (`KeywordNotFound`) | yes |
| arg count (BuiltIn, Browser, user kw, Requests `Create Session`) | yes | yes |
| unknown named arg / missing named-only | yes | yes |
| undefined variable, unclosed `${` | **yes** | **no** |
| missing import; Browser kw with only Selenium (and reverse) | yes (no library hint) | yes |
| ambiguous keyword (custom libs; Browser+Selenium `Get Text`) | yes (`MultipleKeywords`) | yes |
| bad embedded-arg call; FOR/IF/RETURN/empty test/section/setting/resource syntax | yes | yes |
| library init args | flaky (G2) | yes |
| enum/int conversion | **no** | **yes** |
| duplicate test name | no | yes (WARN) |
| `* On Session` missing url | no | no |
| false positives on 16 valid runs | 3 | 0 |

Generated suites: s03 (Browser BDD, 6 static errors) — analyze 6/6 with line:col; dryrun 4/6 (misses `${usrname}`; `Clik` in an unreached keyword); rf-mcp `run_test_suite(mode="dry")` 2 unique errors, no line numbers. s01 (real rf-mcp generated) and s02 clean in both.

## Capability map
| rf-mcp tool | Client command | Warm latency | Size | Replaces? |
|---|---|---|---|---|
| pre-validation | analyze (step file under root) + dryrun, or server-side with stubs | ~1 s client / ~0.05 s server | ~90 tokens | yes, better |
| find_keywords | server search over uploaded specs | ~1.3 ms | – | robotcode alone: no |
| get_keyword_info | `libdoc <Lib> show "<Kw>"` or cached spec | 1.2 s / 0 ms | 0.5–2.4 KB | yes |
| check_library_availability | importlib one-liner (`discover info` lists no libraries) | 0.16 s | 218 B | yes, but installed ≠ runnable (worktree Browser had no Playwright browsers) |
| run_test_suite | `robot` + `results summary --failed` / `results log --failed --extract` | run + 0.95 s | 0.5–6 KB | yes, richer |
| session store | `-c robot.toml -c session.toml -p sess-N` | – | – | works: profile variables + search order remove false positives |

## Open questions
1. Trust model for uploaded specs/generated stubs (curated catalog vs accept anything).
2. Sending resolved variables from Python variable files without the server running user code.
3. Step wrapper carries all previous steps or just a variable table?
4. Report G1, G2 and a language-server process leak upstream?
5. ~1 s per client CLI call acceptable, or client helper daemon?
6. Filtering/redaction of results logs (tokens in plain text; full log ~15k tokens).

## Housekeeping
- robotcode 2.7.0 installed into the worktree venv via `uv pip install` (an exact `uv sync` removes it).
- A bare venv left in the session scratchpad.
- `experiments/` is in the main repo's `.git/info/exclude` → these files don't show in `git status` (force-add needed to commit).
