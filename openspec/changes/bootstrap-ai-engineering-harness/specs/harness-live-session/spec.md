## Purpose

Executes the agent's Robot Framework work live on the user's machine — line by line as test files are edited — while keeping browser, API and desktop state between tool calls and leaving no processes or settings behind.

## ADDED Requirements

### Requirement: Editing a test file executes its new or changed lines live

After each agent write or edit of a `.robot` test file, the harness SHALL execute the new or
changed lines of the affected test in a live Robot Framework session that keeps state (open
pages, sessions, variables) from the previous executed lines of that test. It SHALL attach a
result to the agent's tool result. A failing line SHALL stay open: a subsequent edit that
fixes it, or inserts lines before it, re-runs from that point without repeating the lines
that passed. Changing a line that has already executed SHALL restart the test from its
beginning with a fresh browser context. Test teardown SHALL run only in plain runs.

#### Scenario: incremental execution keeps the page

- **WHEN** the agent writes a test that opens a page, then in a second edit appends a `Click` line
- **THEN** only the appended line executes in the second edit, on the page opened by the first edit, and the tool result reports the line range and its status

#### Scenario: fixing the failing line resumes there

- **WHEN** line 14 failed and the agent edits only line 14
- **THEN** execution resumes at line 14 without re-running lines that passed before it

#### Scenario: changing an executed line restarts the test

- **WHEN** the agent edits line 10, which already passed
- **THEN** the test restarts from its first line in a fresh browser context

### Requirement: Live element timeouts are short, adaptive and never persisted

During live execution, element-level steps SHALL use a short timeout (default 2.5 seconds);
navigation and explicit wait keywords keep their normal timeout. When an element is
observed to appear later than the short timeout, the harness SHALL stop shortening timeouts
for that page and SHALL use a learned value for the site. These timeout adjustments MUST NOT
be written into any file the agent edits, and MUST NOT change the behavior of a plain
`robot` run.

#### Scenario: a missing element fails fast live

- **WHEN** a live `Click` targets a selector that matches nothing on a stable page
- **THEN** the step fails within about 3 seconds instead of the library's default timeout

#### Scenario: suites stay portable

- **WHEN** the agent's final suite is run with plain `robot` outside the harness
- **THEN** no harness timeout setting, listener or import is required, and none appears in the suite

### Requirement: Plain robot runs are summarized and their first failure is reproduced live

When the agent runs `robot` on a suite, the harness SHALL attach one line per failing test
and reproduce the first failure in the live session, stopping at the failing line. If the
failure does not reproduce live, the harness SHALL report it as a timing race and advise
waiting for the needed state before the failing step. It SHALL then stop further live
reproductions of that failure for the session.

#### Scenario: an existing failing suite is diagnosed

- **WHEN** the agent runs `robot` on a suite whose third test fails at a `Select Options By` line
- **THEN** the tool result lists the failing test with its error, and the live session stands at that line with page state captured

#### Scenario: a race is named as such

- **WHEN** a plain run fails at a step that passes when reproduced live
- **THEN** the feedback states that the failure was not reproduced and is a timing race

### Requirement: REPL and debugger calls are kept in the required format

When the agent invokes the robotcode REPL or debugger, the harness SHALL show the required
call format once per session. It SHALL rewrite correctable format errors: missing quoted
heredoc, a single space between cells, `...` continuation lines, a missing output-directory
option. It SHALL refuse calls it cannot correct, with a message containing the required
format.

#### Scenario: a REPL call with single-space cells is corrected

- **WHEN** the agent runs a REPL heredoc whose statements separate cells with one space
- **THEN** the call runs with cells separated by four spaces, and the agent is told about the correction once

### Requirement: The helper process has a safe lifecycle

The live-session helper SHALL start lazily on first need and run as a single instance per
project. It SHALL execute steps serially, even when the agent's hooks run concurrently. It
SHALL survive the agent's per-command process cleanup, exit after an idle period, and on
session end shut down so that no browser, Playwright, robotcode or desktop-automation
processes remain after a bounded time. It MUST NOT send test data or session state to any
remote service.

#### Scenario: no orphans after the session

- **WHEN** an agent session that opened a browser ends
- **THEN** within 30 seconds no process started by the helper (including Playwright node processes) is still running

#### Scenario: concurrent hook calls are serialized

- **WHEN** two edits trigger hooks at the same time
- **THEN** their steps execute one after another and each tool result contains only its own steps

### Requirement: Desktop automation keeps its safety guards

Live desktop (PlatynUI) steps SHALL pass through the same safety, isolation and focus guards
that rf-mcp applies today, including refusal to drive the user's active desktop by default.
The harness MUST NOT weaken any of these guards.

#### Scenario: active desktop is protected

- **WHEN** an agent edit adds a desktop input step while the session targets the user's active desktop without an isolation opt-in
- **THEN** the step is refused with the same guidance rf-mcp gives, and no input is sent
