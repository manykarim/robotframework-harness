## Purpose

Catches defective or outdated Robot Framework code as soon as the agent writes it, refusing only edits that are certainly wrong and turning everything else into one-line warnings the live run can confirm or dismiss.

## ADDED Requirements

### Requirement: Edited Robot Framework files are statically checked

After each agent write or edit of a `.robot` or `.resource` file, the harness SHALL
statically analyze the file with the project's libraries, resources and live-session state
in scope. It SHALL report only error-level findings and warnings that correspond to run-time
failures, each with line, column and rule or diagnostic code. Findings for variables or
keywords that exist in the live session MUST be dropped. The analysis MUST complete within 2
seconds on a warm cache for files up to 500 lines; on timeout it SHALL be skipped with a
note, and the edit SHALL proceed.

#### Scenario: undefined variable reported with location

- **WHEN** the agent writes a line using `${usrname}` that is never defined
- **THEN** the tool result contains a one-line finding with the line, column and an undefined-variable code

#### Scenario: runtime variable not flagged

- **WHEN** a variable created live with `Set Test Variable` is used in a later line
- **THEN** no undefined-variable finding is reported for it

### Requirement: Only certainly-wrong edits are refused

The harness SHALL refuse an edit only when the edit would:
- break the file's syntax or structure;
- delete or rename an existing test;
- hide failures (for example ignoring errors around assertions, or adding skip or
  non-critical markers to failing tests);
- install packages or browsers.

Each refusal message SHALL name the reason and the accepted alternative. Other findings
(unknown keyword, argument-count mismatch, `-P`/`PYTHONPATH` usage, `Sleep`, fewer
assertions, very large reads) SHALL be allowed with a one-line warning.

#### Scenario: deleting a failing test is refused

- **WHEN** the agent's edit removes a failing test case from an existing suite
- **THEN** the edit is refused with a message to fix the test instead

#### Scenario: unknown keyword is only a warning

- **WHEN** the agent writes a keyword name that static analysis cannot resolve
- **THEN** the edit is applied, a one-line warning is attached, and the live run decides

### Requirement: Only safe deprecated-syntax fixes are applied

The harness SHALL automatically modernize only deprecated-but-equivalent syntax:
`Run Keyword If/Unless`, `[Return]`, `Return From Keyword (If)`,
`Exit/Continue For Loop (If)`, `WITH NAME`, `Force/Default Tags`, singular section headers,
lowercase `else`/`else if`. It SHALL report each fix to the agent and re-check the file. It
MUST NOT reformat files or apply any other automatic rewrite.

#### Scenario: Run Keyword If modernized

- **WHEN** the agent writes `Run Keyword If    ${x}    Log    yes`
- **THEN** the file contains an equivalent `IF` block, and the agent is told about the fix

### Requirement: Suites stay portable

The harness SHALL keep the agent's suites runnable by plain `robot` without the harness.
Project libraries and resources SHALL be imported by path relative to the suite, and the
agent SHALL be warned when it relies on `-P`/`PYTHONPATH`. The harness MUST NOT insert
harness-specific imports, listeners or settings into suites.

#### Scenario: PYTHONPATH workaround warned

- **WHEN** the agent runs `robot -P lib tests/x.robot`
- **THEN** the run proceeds and a warning recommends importing the library by path relative to the suite
