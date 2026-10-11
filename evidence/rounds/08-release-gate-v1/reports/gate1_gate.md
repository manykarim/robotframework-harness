# Release gate: rf-harness vs prototype-v32 — **PASS**

Sources: `results_live_gate1.jsonl` · rows used: 90 (rf-harness 45, prototype-v32 45) · excluded non-ok rows: none · contaminated: 0 (excluded) · main agent: claude · margin 0.05 · alpha 0.05

## Verdict

- PASS: claude non-inferior within 0.05, no agent with a significant regression, same time window.

## 1. Non-inferiority: claude (rule: rf-harness ≥ prototype-v32 − 0.05)

| arm | n | passes | rate | 95% CI |
|---|---:|---:|---:|---|
| rf-harness | 15 | 15 | 1.00 | 0.80–1.00 |
| prototype-v32 | 15 | 15 | 1.00 | 0.80–1.00 |

Δ = +0.00 (Newcombe 95% CI -0.20–0.20); threshold 0.95 → **PASS**

## 2. Per agent (pooled over paired scenario cells)

| agent | cells | rf-harness | prototype-v32 | Δ | Fisher p | cells +/− | sign p | significant regression |
|---|---:|---:|---:|---:|---:|---|---:|---|
| claude | 5 | 1.00 (15/15) | 1.00 (15/15) | +0.00 | 1.000 | 0/0 | 1.000 | no |
| codex | 5 | 0.93 (14/15) | 0.93 (14/15) | +0.00 | 1.000 | 1/1 | 1.000 | no |
| opencode | 5 | 0.53 (8/15) | 0.53 (8/15) | +0.00 | 1.000 | 2/1 | 1.000 | no |

## 3. Overall, per scenario kind and per scenario

| subset | cells | rf-harness (95% CI) | prototype-v32 (95% CI) | Δpool | Δcell | Fisher p | cells +/− | sign p |
|---|---:|---|---|---:|---:|---:|---|---:|
| **all** (paired cells) | 15 | 0.82 (37/45) [0.69–0.91] | 0.82 (37/45) [0.69–0.91] | +0.00 | -0.00 | 1.000 | 3/2 | 1.000 |
| kind explore | 9 | 0.85 (23/27) [0.68–0.94] | 0.85 (23/27) [0.68–0.94] | +0.00 | -0.00 | 1.000 | 2/1 | 1.000 |
| kind debug | 6 | 0.78 (14/18) [0.55–0.91] | 0.78 (14/18) [0.55–0.91] | +0.00 | +0.00 | 1.000 | 1/1 | 1.000 |
| tricentis_quote | 3 | 1.00 (9/9) [0.70–1.00] | 0.89 (8/9) [0.56–0.98] | +0.11 | +0.11 | 1.000 | 1/0 | 1.000 |
| carconfig_order | 3 | 0.78 (7/9) [0.45–0.94] | 1.00 (9/9) [0.70–1.00] | -0.22 | -0.22 | 0.471 | 0/1 | 1.000 |
| demoshop_order | 3 | 0.78 (7/9) [0.45–0.94] | 0.67 (6/9) [0.35–0.88] | +0.11 | +0.11 | 1.000 | 1/0 | 1.000 |
| demoshop_debug | 3 | 0.89 (8/9) [0.56–0.98] | 1.00 (9/9) [0.70–1.00] | -0.11 | -0.11 | 1.000 | 0/1 | 1.000 |
| tricentis_debug | 3 | 0.67 (6/9) [0.35–0.88] | 0.56 (5/9) [0.27–0.81] | +0.11 | +0.11 | 1.000 | 1/0 | 1.000 |

Arm totals over all scored rows (incl. cells only one arm has): rf-harness 0.82 (37/45) [0.69–0.91]; prototype-v32 0.82 (37/45) [0.69–0.91]

## 4. Cost, wall time and turns (means per session)

| agent | arm | n | pass | cost $ | wall s | turns | tool calls |
|---|---|---:|---:|---:|---:|---:|---:|
| claude | rf-harness | 15 | 1.00 | 0.027 | 282 | 30.4 | 28.4 |
| claude | prototype-v32 | 15 | 1.00 | 0.030 | 268 | 32.2 | 30.2 |
| codex | rf-harness | 15 | 0.93 | — | 204 | — | 27.1 |
| codex | prototype-v32 | 15 | 0.93 | — | 218 | — | 30.6 |
| opencode | rf-harness | 15 | 0.53 | — | 345 | 44.4 | 43.8 |
| opencode | prototype-v32 | 15 | 0.53 | — | 492 | 50.6 | 50.1 |

## 5. Same time window

- rf-harness: 2026-10-11T07:18:02.915627+00:00 .. 2026-10-11T11:19:26.949922+00:00
- prototype-v32: 2026-10-11T07:18:02.915514+00:00 .. 2026-10-11T11:20:41.672591+00:00
- overlap: yes

## 6. Sensitivity to value-grader artifacts

Rows that failed ONLY value graders (a regex-escaped assertion such as `\$916\.99` may be the cause; graders of new runs accept that form): 0

| arm | pass rate (as graded) | upper bound if every such row were an artifact |
|---|---:|---:|
| rf-harness | 0.82 (37/45) | 0.82 (37/45) |
| prototype-v32 | 0.82 (37/45) | 0.82 (37/45) |
