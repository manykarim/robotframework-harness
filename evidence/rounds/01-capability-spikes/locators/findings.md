# Locator intelligence as robotcode-executable RF steps — findings (2026-10-01)

Source: locators subagent report (saved by the coordinating session; the harness blocks subagent report files). Evidence: `logs/*.log`, `logs/60_rfmcp_inprocess_comparison.txt`; prototype: `resources/guard.resource` + `resources/guard.js` (Browser), `resources/guard_selenium.resource`; runner `scripts/run_repl.sh`; suite form `suites/guarded_steps.robot`.

## Verdict
Mostly yes — and for Browser the guarded step is *more informative* than today's rf-mcp. The client holds a resource (`guard.resource` + `guard.js`); each agent step becomes one line:

```
Guarded    Click    [data-test="login-btn"]    expect=url:inventory.html
```

It prints exactly one machine-readable line `GUARD {json}` with: failure class (13 classes, e.g. INVALID_SELECTOR, NOT_FOUND, MULTI_MATCH, NOT_VISIBLE, OUT_OF_VIEWPORT, DISABLED, COVERED, EXPECT_FAILED), evidence (element states, covering element, why hidden e.g. "ancestor display:none (div#finish)"), candidate locators each **live re-counted** (`n=1` = unique), Selenium→Browser rewrites (`id:x` → `id=x`), `frame >>> selector` fix for iframes, post-verification (value, checked, selected, URL, `expect=` condition), and a client-side screenshot path. Remote server role in this split: build the line (string rewriting), serve the versioned resource, map failure class → advice.

Sample:
```
GUARD {"v":1,"ok":false,"kw":"Click","sel":"text=Enable","phase":"pre","count":2,"cls":"MULTI_MATCH","visible_count":2,
 "matches":[{"i":0,"tag":"h4","loc":"role=heading[name=\"Enable/disable\"]","n":1},{"i":1,"tag":"button","loc":"role=button[name=\"Enable\"]","n":1}],
 "shot":".../guard-2.jpeg","ms":202,"diag_ms":159}
```

## Key numbers
- **Fix accuracy**: 33/37 Browser failure/success cases pointed at the right fix; 3 partial (text inside shadow DOM; which control enables a disabled field); 1 correctly "wait longer". Determinism: 22/22 identical lines across reruns (ignoring timings).
- **Overhead per step** (saucedemo, 10 reps):

| Step | Plain | Guarded precheck | Guarded fast |
|---|---:|---:|---:|
| Fill Text | 17 ms | 149 ms | 91 ms |
| Click | 48 ms | 200 ms | 85 ms |
| Get Text | 18 ms | 104 ms | 65 ms |

  Fast mode = action with 1.5 s timeout, rely on Playwright's actionability checks.
- **Time to fail**: precheck 0.65–0.95 s; fast ~1.7 s; plain step on missing/hidden element 5 s (timeout). Click behind modal: guard 0.75 s (COVERED, `cov="div#auth-modal.auth-modal"`) vs rf-mcp 10.3 s then suggests `force=True` (wrong fix).
- **Output size**: GUARD line 160–230 chars success, 500–1,580 failure (~125–400 tokens). Per page for comparison: ARIA snapshot 0.3–33 KB, page source 2.7–490 KB, rf-mcp actionable elements 0.8–17 KB (no ready locator; drops `data-test`: only 5/67 entries on demoshop had id/name).
- **Screenshots**: JPEG ~85 ms, 20–70 KB, saved on client; agent reads it locally (covering modal obvious). Uploading ≈ 72K base64 chars through model context — don't.

## rf-mcp (live, in-process) vs guard on identical cases
| Case | rf-mcp today | Guard |
|---|---|---|
| typo `[data-test="login-btn"]` | "missing visible/enabled" + wait-longer hints (wrong fix) | `[data-test="login-button"]` n=1 |
| `Fill Text id:user-name` | full Playwright SyntaxError trace + generic hints | `id=user-name` n=1 (1.25 s) |
| bare word `user-name` | generic hints | `id=user-name` n=1, `[name="user-name"]` n=1 |
| strict multi-match `text=Add to cart` | 2.3 KB strict-mode message; suggests `>> nth=N` | 0.28 s, 6 matches each with unique data-test locator, first 3 verified n=1 |
| hidden menu item | "missing visible" + wait hints | OUT_OF_VIEWPORT/NOT_VISIBLE + why="off-canvas … in aria-hidden div.bm-menu-wrap" |
| covered by modal | 10.26 s timeout, suggests `force=True` | 0.75 s COVERED + covering element + screenshot |

## REPL quirks that shape the design
1. REPL rejects `*** Keywords ***` → guard must live in a resource file (inlining costs 1–8 KB per step vs a 60–120 char line).
2. Plain REPL prints every nested `[ INFO ]` line; `Set Log Level` doesn't silence it (~25 lines/guarded step) → agent must `grep '^GUARD '`. `robotcode robot` output is clean.
3. A wrapper keyword with `&{kwargs}` swallows locators containing `=` as named args.
4. `Import Resource` inside the REPL overrides `-v` CLI variables.
5. REPL exit code always 0.

## SeleniumLibrary
Same pattern works (`guard_selenium.resource`). Selenium isn't strict (silently clicks the first of many) → the guard flags multi-match. Default strategy matches id/name, so Browser-style bare CSS fails; guard suggests `css:` form.

## Not reproducible this way
- Hidden server state (session, memory, step recording for build_test_suite).
- Authoritative keyword→library resolution / libdoc signatures on the server side (server must guess unless the client sends owner info).
- Enforcement: the agent can bypass the guard and run plain steps.
- Silent automatic retries; server-side Python DOM filtering.
- Blind spots: closed shadow roots, cross-origin iframes, text nodes inside shadow DOM.
- Cross-step advice (which control enables a disabled field).

## Side findings
- rf-mcp's aggressive page-source filter crashes on demoshop and selectorshub and falls back to raw 48 KB / 490 KB HTML.
- Browser `role=button[name=…]` matching is case-sensitive.
- `PostActionVerifier`, `WrapperSuggester`, `ActionableElementsCollector` exist only on unmerged `feature/improve_complex_sites_handling`.

## Open questions
- Filterable per-command output via repl-server (one-shot REPL runs restart the browser each time, ~2–4 s).
- Guard as a Python library (quieter, faster) vs RF + JS resource.
- Default mode: fast vs precheck.
- Versioning/checksumming a remotely served resource file.
