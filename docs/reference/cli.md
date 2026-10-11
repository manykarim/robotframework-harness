# CLI reference

Generated from the installer's argument parser (`scripts/gen_reference.py`); do not edit by hand.

Run with zero install as `uvx robotframework-harness <command>`; installed, the commands are
`rf-harness` and `robotframework-harness`.

```text
usage: rf-harness [-h] [--version] COMMAND ...

Set up the Robot Framework agent harness for coding agents.

positional arguments:
  COMMAND
    targets    list supported agents with detection result and version
    install    install the harness for one or more agents and the runtime
    uninstall  remove what install recorded (modified files are kept)
    list       show recorded installations (project and user)
    doctor     check that the harness works; exits non-zero on any failure
    version    print the installer and plugin versions

options:
  -h, --help   show this help message and exit
  --version    show program's version number and exit
```

## `targets`

```text
usage: rf-harness targets [-h]

options:
  -h, --help  show this help message and exit
```

## `install`

```text
usage: rf-harness install [-h] [--agents SEL | --agent AGENT]
                          [--mode {plugin,files}] [--scope {project,user}]
                          [--project DIR] [--python PATH] [--runtime-only |
                          --no-runtime] [--runtime-source PATH] [--ref TAG]
                          [--coexist {keep,replace}] [--dry-run] [--yes]
                          [--no-input]

options:
  -h, --help            show this help message and exit
  --agents SEL          all | detected | comma-separated agents: claude-code,
                        codex, copilot-cli, vscode, opencode
  --agent AGENT         a single agent (claude-code, codex, copilot-cli,
                        vscode, opencode)
  --mode {plugin,files}
                        plugin (default): point the agent at the marketplace;
                        files: copy skill, hooks and launcher (OpenCode always
                        uses files)
  --scope {project,user}
                        project: the project directory (default); user: your
                        home directory
  --project DIR         project directory (default: current directory)
  --python PATH         interpreter (or environment directory) of the project
  --runtime-only        only provision the runtime into the project
                        environment
  --no-runtime          do not provision the runtime
  --runtime-source PATH
                        install the runtime from a local source checkout
                        instead of PyPI (testing before a release)
  --ref TAG             plugin mode: pin the marketplace to a tag, e.g. v1.0.0
  --coexist {keep,replace}
                        keep (default): keep other RF agent tools and let rf-
                        agentskills report static errors (RFH_STATIC=runtime-
                        only); replace: rf-harness runs its full static checks
                        and research prototype installs are removed (other
                        tools' entries are never modified)
  --dry-run             print every planned change without writing anything
  --yes, -y             accept the defaults without prompting (runs the Codex
                        plugin commands and installs the runtime)
  --no-input            never prompt
```

## `uninstall`

```text
usage: rf-harness uninstall [-h] [--agents SEL | --agent AGENT]
                            [--scope {project,user}] [--project DIR]
                            [--dry-run] [--yes] [--no-input]

options:
  -h, --help            show this help message and exit
  --agents SEL          all | detected | comma-separated agents: claude-code,
                        codex, copilot-cli, vscode, opencode
  --agent AGENT         a single agent (claude-code, codex, copilot-cli,
                        vscode, opencode)
  --scope {project,user}
                        project: the project directory (default); user: your
                        home directory
  --project DIR         project directory (default: current directory)
  --dry-run             print what would be removed
  --yes, -y             do not ask for confirmation
  --no-input            never prompt
```

## `list`

```text
usage: rf-harness list [-h] [--project DIR]

options:
  -h, --help     show this help message and exit
  --project DIR  project directory (default: current directory)
```

## `doctor`

```text
usage: rf-harness doctor [-h] [--agents SEL | --agent AGENT]
                         [--scope {project,user}] [--project DIR]
                         [--python PATH] [--no-live]

options:
  -h, --help            show this help message and exit
  --agents SEL          all | detected | comma-separated agents: claude-code,
                        codex, copilot-cli, vscode, opencode
  --agent AGENT         a single agent (claude-code, codex, copilot-cli,
                        vscode, opencode)
  --scope {project,user}
                        check only this scope (default: both)
  --project DIR         project directory (default: current directory)
  --python PATH         interpreter of the project (default: .rf/harness.json)
  --no-live             skip the live smoke step
```

## `version`

```text
usage: rf-harness version [-h]

options:
  -h, --help  show this help message and exit
```
