## Context

See proposal.md (Why). The evidence is in `spike/` (GitHub runners, 2026-10-14):

| finding | windows-2025 (App Installer 1.26.510) | windows-2022 (no App Installer) |
|---|---|---|
| `WindowsApps\python.exe`, `python3.exe` | present: reparse tag `0x8000001b`, `isfile` and `X_OK` true | absent |
| placeholder run with arguments | exit 9009 in 0.08–0.28 s, message on stderr (49 = 9009 mod 256 under Git Bash) | – |
| installer in an empty folder via uvx | `error: …\WindowsApps\python3.EXE did not start` (the user's bug) | picks **uvx's cache env** silently |
| inside a uvx-run process | `which("python3")` = placeholder, `which("python")` = uvx env, `VIRTUAL_ENV` unset, `UV` set | `which("python")` = uvx env |
| `uv python find` / `uv venv --python 3.12` | real Python / working venv (never the placeholder) | same |
| plugin hook command `python3 -S …` | 9009 under cmd, 49 under Git Bash | "not recognized" / 127 |
| `rfh-launch.cmd` | works through `py` | works through `py` |

Current code:
- `envfind.find_env()` falls back to `shutil.which("python3")`, then `which("python")` on Windows, without checking
  either.
- `cli._provision_runtime()` prints "did not start" when `inspect()` returns `None`.
- `transforms.windows_python_prefix()` already skips `windowsapps` for files-mode hooks.
- The launcher's `path_python()` has no such check.

## Goals / Non-Goals

**Goals:**
- Never select a placeholder, a too-old Python, or the installer's own environment as the project environment.
- Turn the most common Windows situation (uv installed, no project environment) into a working install with one
  confirmation.
- Messages that a user can act on without searching.
- A real-Windows regression test.

**Non-Goals:**
- A working plugin-mode (marketplace) hook bootstrap on Windows. The spike shows it needs a different command per
  agent shell. That is a follow-up change; this change only defaults Windows to files mode and warns.
- Installing Python itself without uv (python.org, winget). We only point to it.
- Changing the discovery order for existing environments (`--python`, active env, `.venv`, uv or poetry env).

## Decisions

### D1. One probe function, used everywhere a candidate is accepted

`envfind.probe(python, timeout=15) -> Probe(status, version, executable, detail)`:
- It runs `[python, "-c", <print version + executable>]`, with stdin closed.
- `usable`: exit 0, version ≥ 3.10.
- `store-placeholder`:
  - exit 9009 (Windows), exit 49 (MSYS truncation), or output containing "Microsoft Store" or "App execution
    aliases";
  - or, on Windows, a file in `…\Microsoft\WindowsApps` with reparse tag `0x8000001b` that fails the probe.
- `too-old`: a version below 3.10.
- `broken`: anything else, with the exit code and the first output line.

`find_env()` returns the first usable candidate and records every skipped one in `EnvChoice.skipped`. `inspect()`
(the full module report) runs only on the chosen interpreter.

- Alternative considered: path-only detection (anything under WindowsApps is a placeholder). Rejected, because Python
  installed from the Microsoft Store also lives behind aliases in WindowsApps, and those work.

### D2. Exclude the installer's own environment

- A candidate is excluded when its resolved path lies under the running installer's `sys.prefix` or
  `sys.base_prefix`'s **uv cache**, recognized by:
  - an `archive-v0` path segment;
  - `UV_CACHE_DIR`, or uv's default cache dir;
  - `UV_TOOL_DIR`.
- This covers `uvx` (an ephemeral archive env) and `uv tool install` environments, on every platform.
- The excluded candidate appears in the skip list as "the installer's own environment".

### D3. Recovery: `uv venv` with consent

- The uv binary comes from the `UV` variable first (set by `uvx`, verified on Windows in the spike), then
  `shutil.which("uv")`.
- The command is `uv venv --python <X.Y> <project>/.venv`, with a default of `3.12`: the version used in rounds 7–8 and
  safe for Browser wheels. New flag `--venv-python X.Y`.
- Consent:
  - interactive: a prompt (default yes);
  - `--yes`: proceed;
  - `--no-input` without `--yes`: print the command and exit 1.
- After creation: probe `<project>/.venv/Scripts/python.exe` (or `bin/python`). On failure, print uv's stderr tail and
  `--python <path>`, then exit 1.
- Then the usual runtime install into `.venv`, and `.rf/harness.json` is written. No `pyproject.toml` is created or
  changed.
- Alternatives considered:
  - **Install into a global interpreter:** pollution and permission problems.
  - **Install into the installer's interpreter:** an ephemeral cache.
  - **`uv init`:** too invasive.

### D4. Message format

```
Python environment: none usable in C:\work\demo
  skipped  python3 on PATH  C:\Users\me\AppData\Local\Microsoft\WindowsApps\python3.exe
           -> the Microsoft Store placeholder (App Execution Alias), not a Python installation
  skipped  python on PATH   D:\...\uv\cache\archive-v0\...\Scripts\python.exe -> the installer's own (uvx) environment
Create a project environment with uv?  uv venv --python 3.12 C:\work\demo\.venv  [Y/n]
```

Without uv:
- "Install uv (https://docs.astral.sh/uv/) and rerun, or pass --python <path>";
- for the placeholder, add the alias tip.

`doctor`'s environment check uses the same probe and wording.

### D5. Launcher fallback: metadata check only

`path_python()` skips a file when, on Windows, `os.lstat(p).st_reparse_tag == 0x8000001B` and its parent folder is
named `WindowsApps`. There is no subprocess, so the hook stays within its latency budget. Store-installed real Pythons
are also skipped there. That is acceptable for a last resort, because installs write `.rf/harness.json`, which the
launcher checks first.

### D6. Windows defaults to files mode

- `install` on Windows defaults `--mode` to `files`.
- An explicit `--mode plugin` on Windows prints a warning, citing that the marketplace hooks cannot start Python there.
- Docs: the quick starts note "Windows: files mode is the default; plugin-mode hooks are not supported on Windows yet".

### D7. Tests

- **Unit tests (all platforms):** a synthetic placeholder executable that exits 9009 with the Store message, written as
  a Python script launched through a wrapper (POSIX `sh` script, Windows `.cmd`). Covered: the probe classification;
  `find_env` skipping the placeholder and the installer's own environment; uv recovery with a fake `uv`; the message
  content; and `--no-input` exiting 1.
- **CI job `windows-install` on `windows-2025`** (real placeholder, real uv): a clean PATH with WindowsApps plus uv;
  `python -m rf_harness.installer.cli install --agent claude-code --yes --runtime-source .` in an empty folder. It
  asserts that:
  - the output names the placeholder;
  - `.venv\Scripts\python.exe` exists;
  - the runtime imports there;
  - `.rf/harness.json` points to it.
- The spike workflow and script stay on their branch as evidence and are not merged.

## Risks / Trade-offs

- [A future placeholder changes exit code or wording] → Several signals (9009, 49, message keywords, reparse tag plus
  failure), and the real-runner CI job catches drift on new images.
- [`uv venv` downloads a Python (network) on machines without one] → That is uv's documented behaviour. The consent
  prompt shows the command. Offline machines get uv's error and the `--python` alternative.
- [A uv-managed Python fails on locked-down machines (os error 448, redirected AppData)] → The new interpreter is
  probed, the failure is reported with uv's message, and `--python <path>` is suggested.
- [Excluding the installer's environment hides a deliberate choice] → `--python` still accepts any path explicitly.
- [Defaulting Windows to files mode surprises plugin-mode users] → A warning plus docs. A plugin-mode bootstrap follows
  in its own change.

## Open Questions

- Should the follow-up plugin-mode Windows bootstrap use `rfh-launch.cmd` (works through `py`, per the spike) or a uv-based
  command? It does not affect this change.
