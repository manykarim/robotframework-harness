# Live timeouts

A wrong selector with the Browser library's default timeout costs 10–30 seconds per attempt. Live, the harness answers
much faster without changing your test.

## What happens

- **Element steps** (click, fill, get text, …) use a short live timeout: **2.5 s** by default (`RFH_SHORT_TIMEOUT`).
  Navigation and explicit `Wait For …` keywords keep their normal timeout.
- **Stable pages fail at once.** A page counts as stable when:
  - the DOM has been quiet for 2 s (`RFH_STABLE_S`);
  - no fetch, XHR or long timer is pending;
  - the page is at least 6 s old.

  A selector that matches nothing on a stable page is reported as `MISSING` immediately.
- **Learning.** When an element really appears late (`SLOW`: absent at the timeout, present later), that page keeps
  the normal timeout from then on. The site's live timeout becomes min(normal, 1.5 × observed delay)
  (`RFH_ADAPT_FACTOR`). Learned values live in `.rf/exec/timeouts.json`.
- **Nothing reaches your files.** The timeouts are set inside the live session only. A plain `robot` run uses exactly
  what your suite says.

## Why

- Round 5 used a fixed 2.5 s timeout plus a re-check. About 45% of the re-checks were genuinely slow elements, and many
  `SLOW` verdicts were wrong: a covered radio button looked like a timing problem.
- Round 6 diagnosed this:
  - 110 of 111 `SLOW` verdicts were false;
  - settle waits between live steps made live runs pass where plain runs failed.
- The v3 design reads Playwright's own log first ([verdicts](verdicts.md)), adds no hidden waits, and learns per site.
  It produced zero false `SLOW` verdicts in round 6.

Evidence: [round 5](../../evidence/rounds/05-v2/), [round 6](../../evidence/rounds/06-v3-main/).

## Configure

| variable | default | effect |
|---|---|---|
| `RFH_SHORT_TIMEOUTS` | `1` | `0` turns the short live timeouts off |
| `RFH_SHORT_TIMEOUT` | `2.5` | live element timeout in seconds |
| `RFH_STABLE_S` | `2` | DOM quiet time for a page to count as stable |
| `RFH_ADAPT_FACTOR` | `1.5` | learned site timeout = factor × observed delay (capped at the normal timeout) |

See the [environment reference](../reference/environment.md) for all variables.
