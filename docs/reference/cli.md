# CLI reference

Generated from the installer's argument parser (`scripts/gen_reference.py`); do not edit by hand.

Run with zero install as `uvx robotframework-harness <command>`; installed, the commands are
`rf-harness` and `robotframework-harness`.

| command | purpose |
|---|---|
| [`targets`](#targets) | list supported agents with detection result and version |
| [`install`](#install) | install the harness for one or more agents and the runtime |
| [`uninstall`](#uninstall) | remove what install recorded (modified files are kept) |
| [`list`](#list) | show recorded installations (project and user) |
| [`doctor`](#doctor) | check that the harness works; exits non-zero on any failure |
| [`version`](#version) | print the installer and plugin versions |

## `targets`

list supported agents with detection result and version.

No options.

## `install`

install the harness for one or more agents and the runtime.

| option | value | default | meaning |
|---|---|---|---|
| `--agents` | `SEL` |  | all / detected / comma-separated agents: claude-code, codex, copilot-cli, vscode, opencode |
| `--agent` | `AGENT` |  | a single agent (claude-code, codex, copilot-cli, vscode, opencode) |
| `--mode` | `plugin` / `files` |  | plugin (default; files on Windows): point the agent at the marketplace; files: copy skill, hooks and launcher (OpenCode always uses files) |
| `--scope` | `project` / `user` | `project` | project: the project directory (default); user: your home directory |
| `--project` | `DIR` |  | project directory (default: current directory) |
| `--python` | `PATH` |  | interpreter (or environment directory) of the project |
| `--venv-python` | `X.Y` | `3.12` | Python version of the project environment that uv creates when none is usable |
| `--runtime-only` | (flag) |  | only provision the runtime into the project environment |
| `--no-runtime` | (flag) |  | do not provision the runtime |
| `--runtime-source` | `PATH` |  | install the runtime from a local source checkout instead of PyPI (testing before a release) |
| `--ref` | `TAG` |  | plugin mode: pin the marketplace to a tag, e.g. v1.0.0 |
| `--coexist` | `keep` / `replace` | `keep` | keep (default): keep other RF agent tools and let rf-agentskills report static errors (RFH_STATIC=runtime-only); replace: rf-harness runs its full static checks and research prototype installs are removed (other tools' entries are never modified) |
| `--dry-run` | (flag) |  | print every planned change without writing anything |
| `--yes`, `-y` | (flag) |  | accept the defaults without prompting (runs the Codex plugin commands and installs the runtime) |
| `--no-input` | (flag) |  | never prompt |

## `uninstall`

remove what install recorded (modified files are kept).

| option | value | default | meaning |
|---|---|---|---|
| `--agents` | `SEL` |  | all / detected / comma-separated agents: claude-code, codex, copilot-cli, vscode, opencode |
| `--agent` | `AGENT` |  | a single agent (claude-code, codex, copilot-cli, vscode, opencode) |
| `--scope` | `project` / `user` | `project` | project: the project directory (default); user: your home directory |
| `--project` | `DIR` |  | project directory (default: current directory) |
| `--dry-run` | (flag) |  | print what would be removed |
| `--yes`, `-y` | (flag) |  | do not ask for confirmation |
| `--no-input` | (flag) |  | never prompt |

## `list`

show recorded installations (project and user).

| option | value | default | meaning |
|---|---|---|---|
| `--project` | `DIR` |  | project directory (default: current directory) |

## `doctor`

check that the harness works; exits non-zero on any failure.

| option | value | default | meaning |
|---|---|---|---|
| `--agents` | `SEL` |  | all / detected / comma-separated agents: claude-code, codex, copilot-cli, vscode, opencode |
| `--agent` | `AGENT` |  | a single agent (claude-code, codex, copilot-cli, vscode, opencode) |
| `--scope` | `project` / `user` |  | check only this scope (default: both) |
| `--project` | `DIR` |  | project directory (default: current directory) |
| `--python` | `PATH` |  | interpreter of the project (default: .rf/harness.json) |
| `--no-live` | (flag) |  | skip the live smoke step |

## `version`

print the installer and plugin versions.

No options.
