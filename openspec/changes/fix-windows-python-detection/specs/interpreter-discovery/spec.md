## Purpose

Makes the installer, doctor and hook launcher choose a real, durable Python environment for the harness runtime on every platform — never a Microsoft Store placeholder or the installer's own throwaway environment — and recover with uv when the project has none.

## ADDED Requirements

### Requirement: Candidate interpreters are probed before use

The installer and `doctor` SHALL run every candidate interpreter once, with arguments, before using it. A candidate is
`usable` only when the probe succeeds and reports Python 3.10 or newer. Otherwise it is classified as:
- `store-placeholder`: exit code 9009, or the "Python was not found … Microsoft Store" message;
- `too-old`;
- `broken`, with the exit code and the first line of its error output.

Unusable candidates SHALL be skipped and discovery SHALL continue with the next source. The skip and its reason MUST
appear in the installer's output.

#### Scenario: Store placeholder on PATH is skipped

- **WHEN** no project environment exists and `python3` on PATH is the Microsoft Store App Execution Alias
- **THEN** the installer reports that this file is the Microsoft Store placeholder and not a Python installation, does not use it, and continues discovery

#### Scenario: probing does not open the Store

- **WHEN** the placeholder is probed
- **THEN** it is invoked with arguments, so it only prints its message and exits; no Store window opens

### Requirement: The installer's own environment is never the project environment

Discovery MUST exclude every interpreter that belongs to the installer's own process environment (`sys.prefix` of the
running installer) or that lives inside uv's cache or tool directories. This holds on every platform, including when
`uvx` has put that environment first on PATH. An installer that runs from the project's own environment (the active
environment or `<project>/.venv`) is the exception: that environment is the project environment and stays allowed.

#### Scenario: harness installed into the project environment

- **WHEN** the installer runs from `<project>/.venv`, into which the user installed `robotframework-harness`
- **THEN** `<project>/.venv` is chosen as the project environment

#### Scenario: uvx tool environment is excluded

- **WHEN** the installer runs via `uvx` in a folder without a project environment and PATH resolves `python` to the uvx tool environment
- **THEN** that interpreter is not offered as the project environment, and the runtime is never installed into it

### Requirement: Missing project environments are created with uv on consent

When no usable project environment is found and uv is available (from the `UV` environment variable set by `uvx`,
otherwise PATH), the installer SHALL offer to create `<project>/.venv` with `uv venv --python 3.12`. A different version
SHALL be selectable. The installer SHALL:
- ask in interactive mode (default yes);
- create it without asking with `--yes`;
- print the exact command and exit with status 1 with `--no-input` and no `--yes`.

After creation it SHALL probe the new interpreter and install the runtime there. When `uv venv` fails or the new
interpreter is unusable, the installer SHALL show uv's message and suggest `--python <path>`. It MUST NOT fall back to an
unusable or excluded interpreter, and it MUST NOT replace an existing `<project>/.venv`.

#### Scenario: Windows without a project environment

- **WHEN** a user runs `uvx robotframework-harness install --yes` in an empty folder on Windows with the Store placeholder on PATH
- **THEN** the installer creates `.venv` with uv, installs the runtime into `.venv\Scripts\python.exe`, records it in `.rf/harness.json`, and exits 0

#### Scenario: uv cannot create the environment

- **WHEN** `uv venv` fails (for example uv's managed Python is on an untrusted mount point)
- **THEN** the installer prints uv's error and the `--python <path>` alternative, exits 1, and has not installed anything

### Requirement: Discovery failures explain the cause and the fixes

When the installer cannot find or create a usable environment, its message SHALL:
- name every skipped candidate with its classification;
- list the fixes: let uv create the project environment (with the command), pass `--python <path>`, and, for the Store
  placeholder, turn off the alias under Settings → Apps → Advanced app settings → App execution aliases.

The message "did not start" without a cause MUST NOT appear. `doctor` SHALL report the same classification for its
environment check.

#### Scenario: no uv and only the placeholder

- **WHEN** uv is not available and the only `python3` on PATH is the Store placeholder
- **THEN** the installer exits 1 with a message that names the placeholder and lists the `--python` and app-alias fixes plus how to get uv

### Requirement: The launcher's last resort skips placeholders without extra processes

The hook launcher's PATH fallback SHALL skip App Execution Alias placeholders, detected from file metadata (the
reparse tag), without starting a process. The earlier discovery steps (`RFH_PYTHON`, `.rf/harness.json`, the active
and project environments) are unchanged.

#### Scenario: hook in a project without harness.json

- **WHEN** a hook fires on Windows in a project without `.rf/harness.json` and the only PATH Python is the placeholder
- **THEN** the launcher treats the runtime as missing and emits its one-line setup hint at session start, instead of running the placeholder

### Requirement: Windows installs default to files mode

On Windows, `install` SHALL default to files mode, because the marketplace hook command cannot start Python there.
When plugin mode is requested explicitly on Windows, the installer SHALL warn that plugin-mode hooks do not run on
Windows yet, and recommend `--mode files`.

#### Scenario: explicit plugin mode on Windows

- **WHEN** a Windows user runs `install --mode plugin --agent claude-code`
- **THEN** the installer writes the plugin settings and prints a warning that the marketplace hooks cannot start Python on Windows, recommending `--mode files`

### Requirement: Windows behaviour is tested on a real Windows runner

CI SHALL run an installer check on a Windows image that ships the Store placeholder (`windows-2025`). The check covers:
the placeholder on PATH is reported and skipped; `--yes` creates `.venv` with uv; the runtime is installed into that
`.venv`; the uvx tool environment is never selected.

#### Scenario: regression on Windows

- **WHEN** a change reintroduces the PATH fallback to the placeholder
- **THEN** the Windows CI job fails
