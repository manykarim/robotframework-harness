## Why

On Windows, `uvx robotframework-harness install` in a folder without a project environment fails after the agent
selection with `error: …\WindowsApps\python3.EXE did not start`.

A spike on GitHub's Windows runners (`spike/` in this change) reproduced this exactly on `windows-2025`:
- With no project environment, the installer falls back to `python3` on PATH. On Windows that is the Microsoft Store
  placeholder, an App Execution Alias. Run with arguments, it exits 9009 with "Python was not found; …".
- The installer discards that message and offers no recovery, although it runs on a working uv-managed Python, with uv
  available through the `UV` variable.

The spike also found a silent variant on every platform. When no placeholder is present, the same fallback picks
`uvx`'s own throwaway tool environment, which `uvx` puts first on PATH. The runtime would then be installed into a cache
that uv may delete, and the hooks would point there.

## What Changes

- **Probe interpreters before using them.**
  - The installer and `doctor` run each candidate interpreter once, with arguments.
  - They classify it as usable, as the Microsoft Store placeholder (exit 9009 or its message), as too old (< 3.10) or
    as broken.
  - Unusable candidates are skipped, with a recorded reason, and discovery continues.
- **Never use the installer's own environment.** Candidates inside `uvx`'s tool environment (`sys.prefix`) or uv's
  cache are excluded on all platforms.
- **Recover with uv.**
  - When no usable project environment exists and uv is available (the `UV` variable first, then PATH), the installer
    offers to create `<project>/.venv` with `uv venv --python 3.12`. It probes the new interpreter, then installs the
    runtime there.
  - Interactive runs ask first; `--yes` creates it; `--no-input` without `--yes` prints the command and exits 1.
  - A failing `uv venv` (for example a uv-managed Python in a redirected AppData folder) is reported with uv's own
    message and the `--python` alternative.
- **Errors that explain.** Instead of "did not start", the message names the cause, for example "is the Microsoft Store
  placeholder (App Execution Alias), not a Python installation". It then gives the fixes: let uv create the project
  environment, pass `--python <path>`, or turn off the alias under Settings → Apps → Advanced app settings → App
  execution aliases.
- **Launcher last resort.** The hook launcher's PATH fallback skips App Execution Alias placeholders. It uses a
  reparse-tag check, so no extra process starts per hook.
- **Plugin mode on Windows.** The spike showed the marketplace hook command (`python3 -S …`) fails on Windows images
  with and without the placeholder. So on Windows the installer defaults to files mode, which uses `py -3` or the
  absolute interpreter path. If plugin mode is requested explicitly, it warns. A proper plugin-mode bootstrap for
  Windows is a separate follow-up.
- **Windows regression test in CI** on `windows-2025`, where the placeholder exists natively. It covers: the
  placeholder is skipped, the clear message appears, `--yes` creates `.venv` with uv, and the runtime lands in
  `.venv`.

## Capabilities

### New Capabilities

- `interpreter-discovery`: how the installer, `doctor` and the hook launcher find, validate and (with consent) create
  the project's Python environment. Covers probe-before-use, the placeholder classification, excluding the installer's
  own environment, uv-based recovery, actionable errors, the Windows install-mode default, and the Windows CI check.

### Modified Capabilities

None. The installer's discovery order is specified in `installer-cli` of change `bootstrap-ai-engineering-harness`,
which is complete but not archived. This change adds a separate capability rather than modifying a spec that is not in
`openspec/specs/` yet.

## Impact

- **Code:**
  - `src/rf_harness/installer/envfind.py`: probe, classification, own-environment exclusion, uv recovery;
  - `cli.py`: messages, consent, the Windows mode default;
  - `doctor.py`;
  - `plugins/rf-harness/bin/rfh_launch.py`: the PATH fallback skips placeholders.
- **Tests:** unit tests with a synthetic placeholder (exit 9009); a Windows CI job on `windows-2025` with the real
  placeholder.
- **Docs:** Windows troubleshooting, the quick start note for Windows, the agent matrix.
- **No new dependencies.** uv is used only when available; the `UV` variable is set by `uvx`.
