## Purpose

Lets users install and update the Robot Framework agent harness through the plugin systems their coding agents already have, at user or project scope, with every release pinnable by tag.

## ADDED Requirements

### Requirement: The repository is a plugin marketplace with one harness plugin

The repository SHALL contain a plugin marketplace definition at `.claude-plugin/marketplace.json`, listing one plugin,
`rf-harness`, whose source lives in the repository. The plugin SHALL contain:
- the Robot Framework Agent Skill with its references;
- the hook definitions;
- a stdlib-only hook launcher;
- per-agent variants where an agent needs a different format.

Its manifest version MUST equal the release version. The marketplace MUST validate with each supported agent's own
validation command where one exists.

#### Scenario: marketplace validates

- **WHEN** the release pipeline runs `claude plugin validate` (and the equivalent for other agents that offer one) on the repository
- **THEN** validation passes and reports the plugin `rf-harness` with the release version

### Requirement: Plugin installation works in each marketplace-capable agent

Users SHALL be able to add the marketplace by its repository name and install `rf-harness` with the agent's own plugin
commands in Claude Code, GitHub Copilot CLI, VS Code (Copilot) and OpenAI Codex. After installation:
- the skill SHALL be available to the agent;
- the hooks SHALL run in that agent, after any one-time trust step the agent requires. The documentation and the
  installer output MUST name that step.

#### Scenario: Claude Code plugin install

- **WHEN** a user runs `claude plugin marketplace add manykarim/robotframework-ai-engineering` and `claude plugin install rf-harness@robotframework-ai-engineering`
- **THEN** a new Claude Code session in a Robot Framework project receives the harness session context, and editing a test file returns live execution feedback

#### Scenario: Codex requires hook trust once

- **WHEN** a user installs the plugin in Codex and has not trusted its hooks yet
- **THEN** the hooks do not run, and the installer output and documentation tell the user to trust them once with `/hooks`; after trusting, live feedback arrives

### Requirement: Project scope is a committed settings file

For agents that support committed plugin settings, a project SHALL be able to enable the plugin for everyone through
a committed settings file that names the marketplace and plugin, optionally pinned to a release tag. Project
enablement MUST NOT require copying harness files into the repository.

#### Scenario: team enables the harness

- **WHEN** a repository commits `.claude/settings.json` with the marketplace (pinned to `v1.0.0`) and `rf-harness` enabled
- **THEN** Claude Code and Copilot CLI sessions opened in that repository load harness version 1.0.0

### Requirement: Releases are tagged and pinnable

Each release SHALL be tagged `v<version>` and SHALL move a `stable` reference to the latest release. Installing with a
tag MUST install exactly that version. Installing without a reference follows the default branch.

#### Scenario: pinned install stays put

- **WHEN** a project pins `v1.0.0` and version 1.1.0 is released
- **THEN** that project keeps loading 1.0.0 until the pin is changed
