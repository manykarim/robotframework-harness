# Failure verdicts

Every failing element step gets a verdict. It comes from evidence: the Browser library's Playwright log and the page
state at the moment of failure, both read **before** any re-check. The verdict tells the agent what kind of fix is
needed: a different selector, a different element, waiting for something specific, or different data.

| verdict | meaning | what to do |
|---|---|---|
| `COVERED` | another element intercepts the click, such as a styled `<span>` over a radio or an overlay | click the label or the element on top (the harness gives a concrete selector); waits and `force=True` do not help |
| `NOT_VISIBLE` | the element exists but is hidden | open its menu, tab or dialog first, or click its visible label |
| `DISABLED` | exists but disabled | complete the steps that enable it |
| `ANIMATING` | kept moving | `Wait For Elements State    <sel>    stable` before it |
| `AMBIGUOUS` | several matches (Browser strict mode) | make the selector unique, or `>> nth=0` if order really matters |
| `NO_OPTION` | a `<select>` without that option | use the exact option label shown |
| `WRONG_ELEMENT` | the selector matched an element that can't do this action | target the control itself |
| `PRESENT` | the element exists; not a timing issue | the action or assertion is wrong, not the timing |
| `MISSING` | nothing matches | wrong selector, or the element is in an iframe; pick one from `controls.txt` |
| `IN_IFRAME` | found inside an iframe | use the given `frame >>> selector` form |
| `SLOW` | was absent at the timeout and appeared later | the page keeps the normal timeout; add a wait only when close to the limit |
| `DETACHED` | the page re-rendered the element | locate it again after the update |
| `STATIC <code>` | the line is invalid before it runs (static analysis) | fix the reported problem |

Value checks (`Get Text … ==`, `Should Be Equal …`) show `actual … vs expected …`, so the agent fixes the data or the
steps, not the timing.

## Concrete targets for covered inputs

For `COVERED`, the harness computes a click target that matches **exactly one** element, in this order:

1. the input's `label[for="…"]`;
2. `label:has(#id)`, when the input sits inside a label that has neither `for=` nor text (for example the Tricentis
   price table: `<label><input id="selectplatinum"><span class="ideal-radio"></span></label>`);
3. the covering element's own unique selector, for example `css=#id + span.ideal-radio`.

It never suggests a positional `>> nth=` pick. In round 7, agents without a concrete target improvised
`label.choosePrice >> nth=2`. That works, but it is brittle. v3.2 introduced these targets, and in that round's
transcripts no v3.2 agent made a positional pick. See [round 7](../../evidence/rounds/07-v31-v32/).

## Nearest controls and `NEXT:`

Failures also list the controls nearest to the failing selector, as `kind "name" => selector`. Word matches come
first, then the keyword's usual targets. The answer ends with a concrete `NEXT:` step.

## Why evidence first

Round 6 found that a short timeout followed by a re-check misreads covered elements as slow ones: 110 of 111 `SLOW`
verdicts were false. Reading Playwright's call log first ("… intercepts pointer events", "… element is not visible")
gets the class right before any waiting. See [round 6 diagnosis](../../evidence/rounds/06-v3-main/).
