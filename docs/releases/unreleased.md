# Unreleased

Changes on `main` since 1.0.0. The version number is set at release time.

## Windows: the Microsoft Store placeholder no longer breaks the install

On Windows, `uvx robotframework-harness install` in a folder without a project environment stopped after the agent
selection with `error: …\WindowsApps\python3.EXE did not start`. The installer had fallen back to `python3` on PATH,
which on Windows is the Microsoft Store placeholder (an App Execution Alias), not Python.

- **Interpreters are probed before use.** The installer and `doctor` run every candidate once and skip the Store
  placeholder, Pythons older than 3.10 and interpreters that do not start. Each skipped candidate is printed with its
  reason.
- **The installer's own environment is never used.** On every platform the PATH fallback could pick the throwaway
  environment that `uvx` puts first on PATH, so the runtime would land in uv's cache. Interpreters inside uv's cache
  and tool directories, and the installer's own environment on PATH, are now excluded.
- **Recovery with uv.** With no usable environment, the installer offers to create `<project>/.venv` with
  `uv venv --python 3.12` (new flag `--venv-python`), using the uv that runs `uvx`. `--yes` creates it,
  `--no-input` prints the command and exits 1. A failing `uv venv` is reported with uv's own message and the
  `--python` alternative.
- **Messages that explain.** Instead of "did not start", the installer names the cause and the fixes: let uv create the
  environment, pass `--python <path>`, or turn off the alias under Settings → Apps → Advanced app settings → App
  execution aliases.
- **Files mode by default on Windows.** The marketplace hooks call `python3`, which cannot start Python on Windows.
  `install` now defaults to files mode there and warns on an explicit `--mode plugin`.
- **The hook launcher** skips App Execution Alias placeholders in its PATH fallback, from file metadata, without
  starting a process.

Known limitation, unchanged: the hook runtime is POSIX-only so far (`fcntl`, Unix sockets). On Windows the install
and the runtime provisioning work, but the runtime stops at import when a hook starts it; the launcher fails open, so
agents run without harness feedback. A Windows transport is planned.

Evidence: a spike on GitHub's `windows-2025` and `windows-2022` runners reproduced the bug and measured the placeholder
(exit 9009, reparse tag `0x8000001b`), uv inside `uvx`, and the hook commands
([spike results](https://github.com/manykarim/robotframework-harness/tree/7441981dfe0cdbba0c294fa2528bf85a210b4a6c/openspec/changes/fix-windows-python-detection/spike)).
The new CI job `windows-install` repeats the original scenario on `windows-2025` for every change. See
[Troubleshooting: Windows](../troubleshooting.md#windows).
