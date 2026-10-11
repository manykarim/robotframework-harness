# Round 2 — keyword documentation via robotcode, locally, no upload (2026-10-01)

Source: keyword-docs subagent report (saved by the coordinating session; subagents can't write report files). Evidence: `scripts/` (e1–e7, `gold.json`), `outputs/` (e*_table.txt + raw), `helper/KwDocs.py` (working prototype), `project/` (scratch project: resource + library with init args). robotcode main clone + venv (98 MB) in the session scratchpad.

## Corrections to round 1
- **robotcode returns full keyword docs locally**: signature with types/defaults, tags, return type, full doc, data-type docs — for one keyword, a glob, several keywords in one call, or a whole library/resource.
- "Name-only" is true only for **search**: every robotcode surface matches names only (`libdoc list`, `.kw <text>`, `doc keywords <pattern>` + `--tag`). None searches doc text.
- `.kw post json` → "No keywords found" is designed: `.kw` shows a full doc on exact name, otherwise lists names containing the text. Trap: `.kw post` shows the doc of `POST` (exact name wins) instead of listing matches.
- Round 1's `.doc Fill Text` was a misuse: `.doc` takes a library/resource name.
- No upload needed for search: the ranking round 1 proposed server-side runs locally in < 2 ms/query.

## Local surfaces (robotcode 2.7.0)
| Way | Returns | Latency | Size |
|---|---|---|---|
| `robotcode libdoc <Lib> show "<Kw>" ["<Kw2>"…\|"Wait For*"\|intro]` | full doc (Markdown on RF 7.5, plain on 7.3) | 1.0–1.4 s (CLI floor ~0.9 s) | 1 kw 0.5–1.4 KB; 5 kws 6.6–12 KB; whole Browser 282 KB (~70k tokens), BuiltIn 133 KB, Requests 42 KB |
| `libdoc --format JSON --specdocformat RAW <Lib> /dev/stdout` | full spec | 1.1–1.3 s | Browser 818 KB |
| piped `repl --plain`: `.kw Name`, `.doc Lib\|resource`, `.imports` | full doc for whatever the session imported incl. resources, project libs with init args | ~1.3 s start, then ~45 ms/command | `.kw Click` 1.4 KB, `.doc Browser` 301 KB |

- `robotcode libdoc` = RF libdoc passthrough; honours robot.toml `python-path`; global `--format json` ignored. Init-arg libraries need `path::arg`; resource files work directly.
- **Dot-commands don't work over repl-server `executeCell`** (`.kw Click` → "No keyword with name '.kw Click' found.").
- REPL lookup functions need the live RF context (`EXECUTION_CONTEXTS`) → only inside the RF process (library keyword or `Evaluate`), not from a separate helper process.

## Python API, fresh process per call
| Path | Browser | Selenium | Requests |
|---|---|---|---|
| RF `LibraryDocumentation(name)` total (in-process build) | 0.71 s (0.24 s) | 0.60 s (0.21 s) | 0.35 s (0.07 s) |
| robotcode `get_library_doc(name, args, …)` | 0.79 s | 0.67 s | 0.58 s |
| load locally cached JSON spec | 0.29 s (build 17 ms) | 0.25 s | 0.28 s |
| robotcode analyze cache (`SqliteDataCache` on `.robotcode_cache`) | build 15 ms, total ~0.5 s (import) | – | 7 ms build |

robotcode `KeywordDoc`: arguments (name, kind, types, default), tags, `return_type`, `to_markdown()`; `*args` signatures contain U+200D joiners to strip. Project sources fast: library by path with args 8 ms; resource via `get_model_doc` 2 ms.

## Unreleased `robotcode doc` (main c1cf903; installed in 4 s from local clone)
`lib`, `keywords [PATTERN…] [--tag]`, `keyword NAME…` (exact/glob/embedded-arg match + type docs), `browse` (Markdown when piped). `--format json` → `{name, args, short_doc, tags, doc}` per keyword. Does **not** search doc text (`doc keywords Browser visible` → nothing); one target per call; 0.9–2.3 s. Sizes: `keyword Browser Click` JSON 1.7 KB; `keywords Browser` text 32 KB (one line per kw: signature + short doc), JSON 258 KB. Unknown keyword → exit 1, no suggestion.

## Local search (544 keywords, 6 libraries; 30 self-labelled queries) — hit@5 / MRR
| Strategy | All six libs (n=30) | Session scope (n=46) | ms/query |
|---|---|---|---|
| a1 whole query as name substring (robotcode) | .17/.17 | .13/.13 | <1 |
| a2 `libdoc list` one pattern per word | .43/.31 | .54/.37 | <1 |
| a3 name-word overlap | .93/.76 | .87/.75 | 1 |
| b grep, all words in doc | .73/.63 | .67/.59 | 25–37 |
| **c BM25 stdlib** | **.93/.86** | **.96/.85** | **0.5** |
| d1 rf-mcp KeywordMatcher lexical | .63/.56 | .72/.61 | 280–420 |
| d2 rf-mcp KeywordMatcher + model2vec | .73/.64 | .83/.67 | 285–430 |
| d3 model2vec only | .97/.89 | .91/.81 | 1 |
| **e BM25 + model2vec** | **.97/.90** | **.98/.84** | 1.6 |

Corpus build in-process 0.64 s; BM25 index 20–40 ms; model2vec load 0.4 s, embed 544 kws 22 ms, ~80 MB deps (numpy, tokenizers) + 30 MB model. rf-mcp's current matcher is slowest and weakest. Remaining miss: "switch to iframe" (Selenium calls it `Select Frame`).

## Output shaping
Signature + short doc: mean 161–175 chars (~40–45 tokens)/kw; top-5 ≈ 0.9 KB vs 3–7 KB per rf-mcp `find_keywords`. + arg notes + one example: mean 270–348 chars, p90 ~600. Full doc: mean 0.9–1.3 KB, p90 ≤ 2.7 KB. RequestsLibrary `*args, **kwargs`: all 14 real signatures recovered by unwrapping decorator closures (local only), e.g. `POST On Session(alias, url, data=None, json=None, expected_status=None, msg=None, **kwargs)`.

## `KwDocs` helper prototype
Keywords `Search Keywords` (BM25) and `Keyword Doc` (compact/full/json); reads whatever the current session imported (resources, init-arg project libs). Over repl-server `executeCell`: first search 52 ms (index build), then 4–6 ms; responses 1.3–3.5 KB (REPL log JSON contains output twice). Also works in piped REPL.

## Recommended design (no uploads; at most query + compact results cross the wire)
1. Local helper in the project venv indexes what is actually imported: in-session via the live keyword store (as `KwDocs`); out-of-session via `LibraryDocumentation`/`get_library_doc` once per library, cached locally as JSON spec keyed by library version + RF version + resource mtime (2–17 ms load).
2. Stdlib BM25 default; model2vec optional extra for hybrid ranking.
3. Return signature + short doc for top-5; arg notes/full doc on request; repair `*args, **kwargs` via closure unwrapping.
4. robotcode for exact lookups (`libdoc show` today, `doc keyword --format json` once released); inside a live session use the helper (4 ms) rather than the CLI (~1.2 s).
5. Server holds only tool schemas and optionally query rewriting (iframe → frame).

## Open questions
Reliance on RF private `_kw_store` (robotcode REPL does the same); wait for `robotcode doc` release?; pickled analyze cache stability across versions; small self-labelled gold set → needs agent-in-the-loop eval; synonym handling server vs local; ask upstream for doc-text search + multi-target `doc`.
