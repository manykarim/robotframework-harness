## Purpose

Turns every live result into short, correct and actionable feedback — what failed, why, what is on the page and what to try next — sized for the model in use, with full details available as files.

## ADDED Requirements

### Requirement: Failures are classified from execution evidence

Each live failure of an element step SHALL be classified, from the automation library's own
log and the page state at the time of failure, before any re-check. The classes are:
COVERED, NOT_VISIBLE, DISABLED, ANIMATING, AMBIGUOUS, NO_OPTION, WRONG_ELEMENT, PRESENT,
MISSING, IN_IFRAME and SLOW.
- SLOW SHALL be reported only when the element was absent at the timeout and appeared later.
- COVERED SHALL name the covering element and state that waits and forcing do not help. When
  a concrete click target exists, COVERED SHALL give it as a selector that matches exactly
  one element, in this order:
  1. the input's `label[for=…]`;
  2. `label:has(#id)` for an input inside a label without `for=` or text;
  3. the covering element's own unique selector.
- COVERED MUST NOT suggest a positional pick.
- IN_IFRAME SHALL give the frame-qualified selector.

#### Scenario: a styled span over a radio is reported as COVERED

- **WHEN** a `Click` on a radio input fails because a styled `<span>` intercepts pointer events
- **THEN** the verdict is COVERED, the feedback names the input's label as the click target, and no wait is suggested

#### Scenario: a radio inside a text-less label gets a concrete target

- **WHEN** a `Click` targets a radio that sits inside a `<label>` with neither `for=` nor text, covered by a non-unique styled `<span>`
- **THEN** the COVERED verdict suggests `label:has(#<id>)`, that selector matches exactly that label, and clicking it checks the radio

#### Scenario: no false SLOW

- **WHEN** a click fails on an element that existed during the whole timeout
- **THEN** the verdict is not SLOW

### Requirement: Feedback is bounded, model-specific and repeat-free

Live feedback SHALL contain a defined set of parts:
- on success: the passed line range and one page line;
- on failure: the failing line, the error, the verdict, actual vs. expected for value
  checks, up to a profile-defined number of nearest controls with suggested selectors, and a
  `NEXT:` step.

The harness SHALL select an output profile from the model in use: lean for models that
perform best with brief context, rich for models that need more context. Rich adds the
keyword signature, a failure-type hint and a controls list after navigation. The user MUST
be able to force a profile. Each profile SHALL have a character budget. Truncation MUST keep
the mandatory parts. Information that does not change (keyword signatures, hints, file
lists) SHALL be shown at most once per session per item in the lean profile.

#### Scenario: lean profile for a Claude model

- **WHEN** the session runs on a Claude model and a step fails
- **THEN** the feedback fits the lean failure budget and contains the failing line, the error, the verdict and a `NEXT:` step

#### Scenario: rich profile for an open-weight model

- **WHEN** the session runs on a DeepSeek, Qwen, GLM or MiniMax model and navigation succeeds
- **THEN** the feedback includes up to 8 controls with suggested selectors, within the rich budget

#### Scenario: profile override

- **WHEN** the user forces the lean profile for an open-weight model
- **THEN** lean feedback is produced, and the profile and its source are logged

### Requirement: Page state is captured to files for retrieval

After the last executed step of an edit, and on every failure, the harness SHALL write the
current page state to a fixed location in the project:
- the page's visible text with URL and title;
- a controls list with labels, identifiers, hidden state and suggested selectors
  (frame-qualified for iframe controls);
- the accessibility snapshot;
- the page source;
- a screenshot.

Earlier captures SHALL be kept in a step history. Each capture file MUST have a bounded
size. Feedback SHALL name the files instead of inlining them.

#### Scenario: covered inputs are marked in the controls file

- **WHEN** a page contains a visible radio or checkbox whose click point lies under a later sibling element
- **THEN** its controls entry states that it is covered, suggests the label or covering element as the click target, and names the assertion to use on the input

#### Scenario: controls are greppable after navigation

- **WHEN** a live step navigates to a form page
- **THEN** the controls file lists the form's inputs with suggested selectors, and a later failure on that page points to the file

### Requirement: Loops get one targeted hint

When the same failure signature repeats, the harness SHALL add one hint specific to the
failure type (at most 200 characters), once per signature.

#### Scenario: repeated COVERED failure

- **WHEN** the agent retries a covered click with a different wait twice
- **THEN** one hint explains that waits do not fix covered elements and names the label selector, and it is not repeated for that signature

### Requirement: Long read streaks get one nudge

When the agent reads files a configured number of times in a row (default 8) without
editing a file or running a command, the harness SHALL add one non-blocking note. The note
points to searching the controls file and writing the next test lines. It SHALL be repeated
at most once more, at twice the threshold. An edit or command SHALL reset the count. The
note MUST NOT replace or weaken any refusal.

#### Scenario: a paging read loop is interrupted

- **WHEN** the agent reads the page source in chunks eight times in a row without an edit
- **THEN** the eighth read carries the note, the seventh and ninth do not, and the next edit resets the count

### Requirement: The end of a turn requires a green plain run

When a test file changed since its last green plain `robot` run, the harness SHALL ask the
agent, at the end of its turn, to run the suite with plain `robot`. Agents that support
blocking stop hooks SHALL be blocked a bounded number of times. Agents without a blocking
stop hook SHALL receive an equivalent follow-up prompt.

#### Scenario: unfinished suite is not left behind

- **WHEN** the agent tries to finish after editing a test that never passed a plain run
- **THEN** it is asked to run `robot` on that file before finishing
