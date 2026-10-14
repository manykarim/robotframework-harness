## 1. Probe and classification

- [x] 1.1 Add `envfind.probe()` and the `Probe` result (`usable` / `store-placeholder` / `too-old` / `broken`, with
  version, executable and detail) per design D1, including the Windows reparse-tag hint. Verify with unit tests using a
  synthetic placeholder (exit 9009 with the Store message; a wrapper for POSIX and Windows), a too-old fake
  (`3.9`), a crashing fake, and the real interpreter.
- [x] 1.2 Make `find_env()` probe every candidate, skip unusable ones with reasons (`EnvChoice.skipped`), and exclude
  the installer's own environment and uv cache/tool directories (design D2). Verify with tests: the placeholder first on
  PATH is skipped; the uvx-like environment (`sys.prefix`, `archive-v0`, `UV_TOOL_DIR`) is excluded; existing sources
  (`--python`, active environment, `.venv`, uv/poetry environment) keep their order.

## 2. uv recovery and messages

- [x] 2.1 Implement the uv recovery (design D3): uv from `UV`, then PATH; `uv venv --python <X.Y> <project>/.venv` with
  the new `--venv-python` flag (default 3.12); consent rules (interactive / `--yes` / `--no-input`); probe the new
  interpreter; then the runtime install and `.rf/harness.json`. Verify with tests using a fake `uv` that creates a venv
  layout: `--yes` creates and installs; `--no-input` prints the command and exits 1; a failing fake `uv` prints its
  error and the `--python` alternative and installs nothing.
- [x] 2.2 Replace "did not start" with the message format from design D4 (skipped candidates with classification, the
  uv command, `--python`, the app-alias tip, the uv install hint when uv is missing). Verify with output assertions,
  including the no-uv / placeholder-only case.
- [x] 2.3 Use the same probe and wording in `doctor`'s environment check. Verify with a test: a placeholder-only
  environment fails with the placeholder wording.

## 3. Launcher and install mode

- [x] 3.1 Make the launcher's `path_python()` skip App Execution Alias placeholders by reparse tag in a `WindowsApps`
  folder (design D5), with no subprocess. Verify with a unit test (mocked `os.lstat` result with `st_reparse_tag
  0x8000001B`) and the launcher overhead test (still under 50 ms median).
- [x] 3.2 Default `install --mode` to `files` on Windows and warn on explicit `--mode plugin` there (design D6). Verify
  with tests that patch `os.name`/platform detection: the default mode and the warning text.

## 4. Real-Windows CI and docs

- [ ] 4.1 Add a CI job `windows-install` on `windows-2025` (real placeholder, real uv), per design D7: clean PATH,
  install with `--yes --runtime-source .` in an empty folder; assert the placeholder message, `.venv\Scripts\python.exe`,
  the runtime import there, and `.rf/harness.json`. Verify that the job passes on GitHub, and that it fails when the
  fix is disabled (run it once on a throwaway branch with the old `find_env`).
- [ ] 4.2 Update the docs:
  - troubleshooting: the Windows section, covering the placeholder, the uv recovery and the alias setting;
  - the quick starts: a Windows note on the files-mode default;
  - the agent matrix: plugin mode on Windows not yet supported;
  - the CLI reference: regenerate for `--venv-python`.

  Verify that the strict docs build, `gen_reference --check` and the docs link check pass.
- [ ] 4.3 Run the full suite on all CI platforms and record the spike evidence link in the release notes for the next
  version. Verify that CI is green on ubuntu, macOS and windows.
