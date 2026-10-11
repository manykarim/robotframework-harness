## Purpose

Gets a user from nothing to a working agent harness with one command: it detects their coding agents, installs the skill, hooks and runtime in the right places, proves that everything fires, and can remove it all again safely.

## ADDED Requirements

### Requirement: Zero-install interactive setup with detected agents preselected

The installer SHALL run without prior installation (`uvx robotframework-harness install`). On an interactive terminal without an
explicit selection, it SHALL show a multi-select of the supported agents: Claude Code, Codex, GitHub Copilot CLI,
VS Code (Copilot) and OpenCode. The agents detected on the machine SHALL be preselected. It SHALL also be fully
scriptable:
- `--agents all|detected|<list>`;
- `--yes`;
- non-TTY input means no prompts.

A `targets` command SHALL list each agent with its detection result and version.

#### Scenario: first run on a machine with Claude Code and Codex

- **WHEN** a user runs `uvx robotframework-harness install` in a Robot Framework project on a machine where Claude Code and Codex are installed
- **THEN** the multi-select shows all supported agents with Claude Code and Codex preselected, and confirming installs the harness for both

#### Scenario: headless install

- **WHEN** CI runs `rf-harness install --agents detected --yes` without a TTY
- **THEN** the installer runs without prompting and exits non-zero if any selected agent could not be set up

### Requirement: Plugin and files modes at project or user scope

The installer SHALL support two modes:
- `--mode plugin`: writes marketplace settings for marketplace-capable agents;
- `--mode files`: copies native skill and hook files.

It SHALL support `--scope project` (the default, the current directory or `--project DIR`) and `--scope user`. Agents
without a marketplace (OpenCode) SHALL fall back to files mode and say so. `--dry-run` SHALL print every file and
configuration change without writing anything.

#### Scenario: OpenCode falls back to files

- **WHEN** a user installs for OpenCode with `--mode plugin`
- **THEN** the installer writes the OpenCode skill and plugin files, reports that OpenCode has no marketplace, and the hooks deliver live feedback in an OpenCode session

#### Scenario: dry run

- **WHEN** a user adds `--dry-run`
- **THEN** the output lists each planned file and settings change, and no file on disk changes

### Requirement: The runtime is provisioned into the project's Python environment

The harness runtime executes Robot Framework in-process. So the installer SHALL locate the project's Python
environment in this order:
1. an explicit `--python`;
2. an active virtual environment;
3. a project `.venv`;
4. a uv- or poetry-managed environment;
5. the interpreter on PATH.

It SHALL show the environment it chose and, with the user's consent (or `--yes`), install the runtime there. It SHALL
then verify that Robot Framework, the robotcode runtime and the runtime package import. It MUST NOT install test
libraries or browser binaries unless asked. Instead it SHALL report missing ones that the project's suites import,
with the exact install command.

#### Scenario: runtime added to the project venv

- **WHEN** a project has `.venv` with Robot Framework and Browser, and the user accepts
- **THEN** the runtime is installed into `.venv`, the import check passes, and no other package is changed

#### Scenario: missing browser binaries are reported

- **WHEN** the project imports `Browser` and its browser binaries are not initialized
- **THEN** the installer reports this with `rfbrowser init chromium` (or the uv equivalent) and does not run it

### Requirement: Hook trust and coexistence are handled explicitly

The installer SHALL provision Codex hook trust for exactly the hooks it installed, or print the one-time trust step
when it cannot. It SHALL detect other Robot Framework agent tooling in the selected agents (rf-agentskills hooks, an
rf-mcp server entry) and explain the overlap:
- duplicate edit-validation hooks;
- competing skill guidance.

It SHALL offer a coexistence choice, default "keep both, disable duplicate validation in rf-harness". It MUST NOT
modify the other tools' entries.

#### Scenario: rf-agentskills already installed

- **WHEN** the project already has rf-agentskills hooks in `.claude/settings.json`
- **THEN** the installer reports the overlap, applies the chosen coexistence option, and leaves the rf-agentskills entries unchanged

### Requirement: Manifest-based upgrade and uninstall

The installer SHALL record every written file and configuration entry with a content hash. Running install again
SHALL be idempotent. Upgrading SHALL remove files that the previous version wrote and the new one no longer ships.
Uninstall SHALL remove only recorded entries whose content still matches. Files the user modified SHALL be kept and
listed. The user's and other tools' configuration entries MUST be preserved.

#### Scenario: upgrade removes obsolete files

- **WHEN** version 1.1 no longer ships a reference file that 1.0 installed, and the user upgrades
- **THEN** the obsolete file is removed, unless the user modified it, in which case it is kept and reported

#### Scenario: clean uninstall

- **WHEN** a user runs `rf-harness uninstall` after an install
- **THEN** all unmodified installed files and entries are removed, and the user's own entries remain

### Requirement: Doctor proves the harness works

`rf-harness doctor` SHALL report the following, each with a pass/fail line and the fix:
- per selected agent: whether the plugin or files are installed, whether hooks are trusted where needed, and whether a
  probe hook event reaches the harness;
- for the project: the chosen Python environment, its Robot Framework, robotcode and runtime versions, and the
  libraries the suites import;
- live readiness: a 10-second live smoke step against a bundled local page.

It SHALL exit non-zero when any check fails.

#### Scenario: doctor finds untrusted Codex hooks

- **WHEN** the Codex hooks were installed but not trusted
- **THEN** doctor fails that check and prints the `/hooks` trust step, and the exit code is non-zero
