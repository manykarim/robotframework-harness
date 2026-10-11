## Purpose

Keeps harness changes honest: every change to the skill, hooks or runtime is measured against the previous version on real agents and live user journeys, with graders that cannot be gamed and a runner that survives interruptions.

## ADDED Requirements

### Requirement: Scenarios grade complete user journeys from execution evidence

The evaluation SHALL include live exploratory scenarios (writing a new end-to-end test
against a public site) and debugging scenarios (repairing an existing failing suite).
Grading SHALL rerun the agent's final suite in a clean environment at TRACE log level and
grade the journey from that run's output. The checks are:
- the confirmation was read from the page;
- expected values were read from the page;
- form fields were driven with the given data;
- the journey was not shortcut by deep links, JavaScript navigation or hard-coded
  assertions.

These checks come in addition to file, pass and deprecated-syntax checks.

#### Scenario: deep-link shortcut fails the journey

- **WHEN** an agent's suite navigates directly to the confirmation URL instead of clicking through the checkout
- **THEN** the "no shortcut" check fails, and the session does not count as a pass

### Requirement: Arms are isolated and contamination is detected

Each evaluation cell SHALL run in its own workspace and agent home, with only its arm's tools
installed. The evaluation SHALL flag a cell as contaminated when its transcript shows
another arm's tools or markers. It SHALL detect leaked fixture content and exclude
contaminated cells from results. Example content shipped with the skill MUST NOT contain
scenario fixtures.

#### Scenario: foreign tool use is excluded

- **WHEN** a cell of the MCP arm invokes a harness helper
- **THEN** the cell is marked contaminated and excluded from pass-rate statistics

### Requirement: The runner survives interruptions and invalid sessions

The evaluation runner SHALL resume an interrupted run without repeating completed cells. It
SHALL discard aborted cells and cells whose agent failed to authenticate, and then rerun
them. It SHALL exit with distinct codes for complete, incomplete, authentication failure and
budget exhausted, so that a supervisor can restart it only when appropriate. A per-run lock
MUST prevent two runners from writing the same results.

#### Scenario: resume after an external kill

- **WHEN** the runner is killed mid-run and restarted by its supervisor
- **THEN** it drops the aborted cells, reruns them, and completes without duplicating finished cells

#### Scenario: expired credentials do not pollute results

- **WHEN** an agent's subscription login expires during a run
- **THEN** affected cells are discarded, and the runner exits with the authentication-failure code instead of recording them as failed sessions

### Requirement: Sessions that did no real work are detected and rerun

The evaluation SHALL inspect each session's transcript for provider failures (authentication
errors, HTTP 401/402, exhausted credits) and agent-backend outages that ended the session
without real work. Such sessions MUST be excluded from results and scheduled for rerun, even
when the agent reports a successful exit. Before starting, and between passes, the runner
SHALL check that the provider account still has a usable balance, not only that the key is
valid. Below a configured minimum it SHALL stop with a distinct exit code.

#### Scenario: credit exhaustion recorded as success is caught

- **WHEN** an agent session's only answer is "API Error: 402 … requires more credits" and the agent exits with success
- **THEN** the cell is excluded and queued for rerun, and the runner refuses to start new provider-routed cells until the balance check passes

#### Scenario: backend outage

- **WHEN** a session ends after three tool calls because the agent's model backend timed out repeatedly
- **THEN** the cell is flagged as an infrastructure failure and rerun instead of counted as a harness failure

### Requirement: Value graders accept equivalent assertion forms

File-content graders that check an expected value SHALL accept the value written as a plain
literal and as a regex-escaped literal (for example `916.99` and `916\.99`). The published
report SHALL show the sensitivity of pass rates to grader artifacts found after a run.

#### Scenario: regex assertion of a total

- **WHEN** a suite asserts the order total with `Should Match Regexp    ${summary}    Total\s*\$916\.99`
- **THEN** the "total asserted" grader passes

### Requirement: Model routes, costs and secrets are handled safely

The evaluation SHALL support subscription-authenticated agents and agents routed to
third-party model providers (for example OpenRouter), selectable per run. It SHALL record
per-cell token usage, estimated cost and, where available, provider-reported spend. It SHALL
stop scheduling new cells when a configured budget is exhausted. A run's budget MUST count
only that run's own spend, so concurrent runs that share an API key do not exhaust each
other's budgets; a separate guard MUST respect the key's overall limit. API keys MUST be
read from the environment at run time and MUST NOT be written to result files, logs,
transcripts or commands stored on disk.

#### Scenario: budget guard stops the run

- **WHEN** provider-reported spend reaches the configured budget
- **THEN** no further cells start, running cells finish, and the runner exits with the budget-exhausted code

#### Scenario: concurrent runs keep separate budgets

- **WHEN** two runs share one OpenRouter key and the first run spends $25
- **THEN** the second run's remaining budget is unchanged by that spend

#### Scenario: key never on disk

- **WHEN** a run with an OpenRouter route completes
- **THEN** searching the run's output directory for the API key value and its prefix finds nothing

### Requirement: Harness changes ship only with same-window A/B evidence

A change to the harness skill, hooks, feedback or runtime SHALL be released only after an
A/B run that compares it with the current release (and, while rf-mcp is supported, with
rf-mcp) in the same time window on the same scenarios. The report SHALL give, overall and
per agent and scenario kind:
- pass rates with 95% confidence intervals;
- Fisher and per-cell sign tests;
- cost, wall time and turns.

The change MUST NOT ship when the main target agent's pass rate is lower than the current
release's by more than the configured non-inferiority margin (default 0.05), or when any
supported agent shows a significant regression.

#### Scenario: regression blocks a release

- **WHEN** a harness change lowers Claude Code's pass rate by 0.10 versus the current release in the same-window run
- **THEN** the evaluation report marks the change as failing the release gate
