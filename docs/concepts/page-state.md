# Page-state files

After the last executed step of an edit, and on every failure, the harness writes the current page to files. The
agent reads or greps them instead of asking for the page source again and again.

| file | content | typical use |
|---|---|---|
| `.rf/state/latest/page.txt` | URL, title and the page's **visible text** (≤ 4 KB) | "what does the page say now?", values to assert |
| `.rf/state/latest/controls.txt` | every control with label, id, name, data-test, hidden or covered state, and a suggested selector (`=> …`); iframe controls with `frame >>> …` | pick a selector: `grep -i "postal" .rf/state/latest/controls.txt` |
| `.rf/state/latest/aria.yaml` | accessibility snapshot, per frame | roles and accessible names |
| `.rf/state/latest/source.html` | page source | last resort; large |
| `.rf/state/latest/screenshot.jpg` | screenshot | only for models that read images |
| `.rf/state/step-NNN-<keyword>/` | earlier captures | compare before and after |

`controls.txt` rows look like this:

```text
input[type=radio]  id=selectplatinum  name=Select Option  unchecked   => label:has(#selectplatinum)   (styled input covered by <span class="ideal-radio">: click its label `label:has(#selectplatinum)`; assert on the input: Get Checkbox State    id=selectplatinum    ==    checked)
select  "Make"  id=make   => id=make   (native select [– please select –|Audi|BMW|…] -> Select Options By    id=make    label    <option>)
```

## Rules

- Suggested selectors use stable attributes first: `data-test=`, then `id=` (unless generated), then `name`, then
  `role=…[name="…"]`.
- Same-origin `href`s are never surfaced as selectors. Deep links would skip the user journey.
- Feedback names the files instead of inlining them. In the lean profile, only one page line appears in the answer.

## The read-streak nudge

Some models page through `source.html` in small chunks. In round 7, Gemini 3.8 Flash made about 71 reads per session
and hit the turn cap. After **8 reads in a row** without an edit or command (`RFH_READ_STREAK_AT`), the agent gets one
non-blocking note: grep `controls.txt`, then write the next 2–4 lines. It repeats once at 16. Any edit resets the count.
