## Purpose

Makes the agent harness understandable and adoptable: a quick start that works in minutes for each agent, an explanation of every component and why it exists, a complete reference, and help when something goes wrong.

## ADDED Requirements

### Requirement: Per-agent quick starts reach a green test in under five minutes

The documentation SHALL provide one quick start per supported agent: Claude Code, Codex, Copilot CLI, VS Code
(Copilot), OpenCode. Each SHALL go from a machine with the agent and Python installed to a first live-executed,
plain-`robot`-green test against a bundled demo page. It SHALL use only copy-pasteable commands and give the expected
output after each step. Each quick start MUST be executed in CI or in a documented release check, and its measured
duration recorded.

#### Scenario: Claude Code quick start

- **WHEN** a new user follows the Claude Code quick start
- **THEN** after at most five commands they see live feedback for an edited test and a green `robot` run, and the page shows what that output should look like

### Requirement: Every harness component has a concept page

The documentation SHALL contain a concept page for each component. Each page explains what the component does, why
(with a link to the evidence), how it behaves per agent, and how to configure or disable it. The components are:
- architecture overview;
- hook lifecycle per agent (events, payloads, limits);
- live session and edit-driven execution;
- live timeouts;
- plain-run reproduction;
- failure verdicts;
- page-state files;
- keyword knowledge;
- output profiles;
- static quality checks and refusal policy;
- the stop gate;
- REPL and debugger format enforcement;
- desktop safety;
- helper lifecycle and cleanup;
- the evaluation method.

#### Scenario: a verdict is explained

- **WHEN** a user looks up the COVERED verdict
- **THEN** the page explains its cause, the evidence it is based on, the suggested click targets, why waits and `force=True` do not help, and links to the experiment where the verdict was introduced

### Requirement: The reference is complete and generated where possible

The reference SHALL document:
- every installer command and flag;
- every environment variable with its default;
- every file and directory the harness writes;
- every hook event per agent;
- the support matrix per agent and version.

The CLI and environment-variable reference SHALL be generated from the code, and a check MUST fail the docs build
when a flag or variable is undocumented.

#### Scenario: undocumented variable fails the build

- **WHEN** a developer adds a new environment variable to the runtime without documenting it
- **THEN** the docs build fails and names the variable

### Requirement: Troubleshooting, comparison and evidence pages

The documentation SHALL include:
- a troubleshooting guide for the known failure modes: hooks not firing per agent, untrusted Codex hooks, wrong
  Python environment, missing browser binaries, orphaned processes, sandboxed agents, Windows specifics;
- a page comparing the harness with rf-mcp and rf-agentskills, including when to use which;
- an evidence summary that presents the A/B results with confidence intervals, links each claim to the archive, and
  states the known limits (sample sizes, live-site variance, grader artifacts).

#### Scenario: hooks do not fire

- **WHEN** a user reports that no live feedback appears in Copilot CLI
- **THEN** the troubleshooting guide gives the checks in order (plugin installed, trusted folder or plugin hooks, `rf-harness doctor` output) and their fixes

### Requirement: Documentation builds and links are checked in CI

The documentation SHALL build as a static site in CI. Internal links and links into the evidence archive SHALL be
checked, and a broken link MUST fail the build.

#### Scenario: broken evidence link

- **WHEN** an evidence file is renamed without updating the page that links to it
- **THEN** the docs build fails and names the broken link
