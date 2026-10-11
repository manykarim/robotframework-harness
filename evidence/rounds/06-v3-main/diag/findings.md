# Round 6 diagnosis — why v2 cost Claude more and what v3 must change (2026-10-09)

Source: diagnosis subagent report (saved by the coordinating session). Scripts/data here: `parse_claude.py`, `episodes.py`, `reactions.py`, `rechecks_all.py`, `composition.py`, `opencode_sessions.py`, `summary_diag.json`. Cell dirs were pruned (no hook logs); Claude/OpenCode transcripts contain hook text, Codex numbers from row metrics.

**Main finding:** v2's extra cost is not wait time — it comes from misleading verdicts and a live run that no longer matches the plain run.

## 1. Claude +13 turns / +173 s (v1 → v2)
Model time 186 → 240 s (≈ 4.6 s/turn, just more turns); edit hooks 96 → 135 s; plain robot runs 68 → 128 s (2.2 → 4.1 runs). Extra calls: Bash +7.8 (grep source.html 1.9 → 6.3, robot +1.9), Read +3.8 (.rf/state/latest 7.7 → 10.3), edits +4.8 (refused 0.4 → 1.1). Hook text per edit 1,094 → 1,290 chars; per session 22.2k → 33.8k; cache reads +60% (1.77M → 2.84M). Extra per edit: docs signature 77, file list 75, recheck 52, loop 30, history 24 chars; controls shrank 295 → 165 but 82% of v2 `controls:` lines repeat site header/nav; 71% of docs lines and 71% of hint lines repeat within a session. `page.txt` holds only URL+title → agents grep source.html.

## 2. SLOW re-checks almost all misclassified
110/111 SLOW (Claude 49, OpenCode 62) had the element present immediately (appear time = 2.5 s short timeout; Playwright `locator resolved to`); only 3 passed on re-run; Codex 16 SLOW all Tricentis. Real failures: clicks intercepted by styled `<span class="ideal-radio">` over radio/checkbox inputs and the `get_automobile` link; v2 cut messages at 380 chars, dropping "intercepts pointer events" (11× in v1, 0× in v2). Agents added useless waits after SLOW 19/49 (Claude), 32/60 (OpenCode) vs after MISSING 8/53, 10/79. 29 instant Claude MISSING ("page unchanged > 10 s"), 13 with the element present; "similar control" = same selector. Genuinely late elements: 1/243 (7.9 s). Direct time per edit: SLOW 6.4 s, instant MISSING 3.7 s, waited MISSING 14.4 s, v1 failure 6.6 s → net direct wall effect ≈ 0; loss comes from reacting to wrong advice.
Policy: keep 2.5 s presence timeout; skip re-check/re-run when the locator resolved — classify from the Playwright log (covered by X → click its label; not visible; disabled; animating); re-check only when count = 0; MISSING at once when DOM stable ≥ 2 s; per site after a real absent→present appearance raise to min(normal, 1.5 × appear time). Expected savings ≈ 7 s per waited MISSING (Claude ~11 s/session, OpenCode ~26 s), 8–10 s/session of SLOW re-runs, ~1 wasted wait-edit per 2–3 false SLOWs.

## 3. Codex slowdown = one session
tricentis_quote rep2 1,088 s: live pass, plain fail ×9, 8 live reproductions, 165 captures (median post-tool 4.3 s). Without it Codex v2 ≈ 209 s vs v1 207 s.

## Live vs plain divergence (drives 1 and 3)
Explore: live pass → plain fail 13/20 (v2) vs 5/14 (v1); 19/42 v2 reproductions passed live (v1 2/18) yet output said "stopped at its first failure"; failing plain run + reproduction ≈ 37 s vs 19 s passing. Cause: per-click settle 0.4–1.5 s + ~150 ms per capture (48/Claude session) = hidden waits → races pass live, fail plain. Example: Claude demoshop_order rep1, 10 plain runs, 905 s.

## 4. Which context helps (Claude failure → next progress)
v2 fix median 21 s / mean 49 s / 2.4 edits vs v1 19 s / 30 s / 1.8. Similar controls shown: median 7 s / 1.4 edits vs 25 s / 2.6 without; OpenCode waited MISSING 13 s vs 30 s. SLOW hurts: Claude 33 s vs 16 s; OpenCode 39 s / 4.3 edits vs 27 s / 3.4. Value-check failures: v2 143 s / 5.8 edits vs v1 62 s / 2.5 (no page text). Signature line present in 96% of failures (effect unmeasurable). kw-doc files read 0.1×/session; sessions reading them slowest.

## 5. Debug scenarios
+146 s wall = 99% OpenCode tricentis_debug (rep3 hit 1,803 s timeout: same counter check `'1' should be '0'` failed 42×, 26 loop hints); v1 average pulled down by a 14 s zero-tool OpenCode run; without that cell 346 vs 348 s. tricentis_debug −0.22 = two cell flips (Codex rep1 stopped driving the female radio after 6 false SLOWs; OpenCode failed the start-date check); Claude failed the start-date check 3/3 on both versions (hook-unrelated). Loop hint generic/timing-focused, rendered `Wait For Elements State    Text    visible` (Text as selector); real defect was a past start date.

## v3 changes (priority)
1. Classify click failures before any re-check; keep "intercepts" fragment; SLOW only for absent→present; no instant MISSING when element exists.
2. Live run as strict as plain run: no per-step settle; capture only at last step or on failure (≤ 2 per edit); reproduction passing live → "NOT reproduced — race; add a wait for the state before line N", stop reproducing after first such case.
3. Budgets per edit: Claude/Codex ≤ 700 chars failure, ≤ 250 pass; OpenCode ≤ 600 (keep NEXT:); signature/hint/file list/import note once per session; cut history + repeated controls; keep step lines, error, ≤ 3 nearest similar controls, iframe probe, NEXT; target ~15k chars/session.
4. Visible text (≤ 4 KB) in page.txt.
5. Loop hint: one line ≤ 200 chars, once per failure signature, failure-type specific (value checks: actual vs expected).
6. kw-doc files on demand only; keep page captures.
Expected Claude ≈ −100 s wall/session, cost ≈ v1 ($0.37–0.40). Suggest 5 reps on tricentis for Claude/OpenCode.
