# Round 2 — robotcode via Python API: embedded local helper (2026-10-01)

Source: python_api subagent report (saved by the coordinating session). Spike package `rfmcp_local/`, results `results/*.json`, logs `logs/`, `scripts/isolated_display.sh`. Installed editable into the worktree venv as `rfmcp-local-spike` (`uv pip install -e experiments/robotcode-remote/round2/python_api`; pyproject not edited — uninstall when done).

## Recommendation
Embed robotcode's REPL engine in a per-project helper daemon: faster than stock repl-server, clean shutdown, and rf-mcp logic can run before/after each keyword in the live RF context.

## Architecture (spike 1,526 lines; minimal core ≈ 860)
- `daemon.py`: `run_repl()` on the main thread with `HelperInterpreter(BaseInterpreter)` overriding `run_input` to pull requests from a queue filled by a stdlib socket-server thread.
- Interpreter start/end keyword hooks track depth → one compact record per top-level item `{kw, owner, args, assign, status, msg, failed_in, ret, ms, logs, hints, probe}`; `ret` = real return value; `Log To Console` returned in `console`.
- Journal JSONL (0600) → `build` emits a `.robot` suite. State in `.rf/` (0700): unix socket 0600 + uid check (SO_PEERCRED), or `--tcp` with 128-bit token.
- Edited resource files re-imported automatically (round 1 couldn't). `step --timeout` → `{pending,id}`, `result <id>` later. Concurrent calls serialized; `interrupt` works.
- Clients: `fast.py` (os/sys/socket only), copied into `.rf/` (`python3 -S .rf/fast.py step '<cell>'`); `cli.py` start/stop/cleanup/build/batch.

## Measured (RF 7.5, Browser 20.5, Get Title n=30, each step a separate process)
| | rfmcp_local | stock repl-server |
|---|---|---|
| Startup→ready | 0.50–0.82 s (1.7 s under xvfb-run) | 0.79 s to listen |
| Per step median/p90 | fast client **36/45 ms**; full CLI 70/79; `uv run` 99/110; `robotcode rfmcp step` 928 | R1: python 81/92, bash 24/25; robotcode jsonrpc2 client 120/129 |
| Time inside helper | Get Title 8.8 ms, Log 2.4 ms | – |
| Requests flow (3×14 steps) | all pass; median 3 ms, p90 113 ms (network) | – |
| Stop with Browser | **0.3–0.5 s, 0 orphans** (graceful Browser close 108 ms) | 5.5 s + TimeoutError traceback |
| SIGTERM idle | 487 ms clean exit, 0 orphans | ignored |
| SIGTERM during keyword | keyword interrupted, reply delivered, exit 305 ms | – |
| kill -9 helper | node + 6 chromium orphaned; next `start`/`cleanup` kills node via env token, chromium follows | orphaned node |
| kill -9 with `--pdeathsig` | 0 orphans after 2 s | – |

Why stock shutdown is slow / signals ignored: Browser closes Playwright only via `atexit`; robotcode's patched `_StopSignalMonitor.__call__` drops signals when no keyword runs (the helper replaces that handler).

## Plugin subcommand — works
Entry point `[project.entry-points.robotcode] rfmcp = "rfmcp_local.plugin"` registers `rfmcp` (client, not wrappable) and `rfmcp-serve` (`@wrappable`); `start` spawns `robotcode <-c/-p/-r/--wrapper> rfmcp-serve` (split needed: wrapping `start` itself would kill Xvfb when `start` returns). Verified robot.toml `python-path`, `variables`, `env`, `-p` profiles; profile `wrapper` and `--wrapper "xvfb-run -a"` (DISPLAY set, Xvfb removed on stop); from `.venv/bin/robotcode` and `uv run --no-sync`. robotcode CLI ~0.9 s start → use only for start/stop; harmless `[ WARN ] Ignoring --wrapper` for the starter.

## Python client for stock repl-server
`JsonRPCProtocol` works as client in ~15 lines (`create_unix_connection` + `send_request_async("executeCell")`), 120 ms/step (module import 65 ms). Stock problems remain, plus: crashes with `AF_UNIX path too long` on deep project paths (helper falls back to `$XDG_RUNTIME_DIR`); still needs `-d` to exist.

Future-proofing: both routes use undocumented internals; robotcode sub-packages pinned `==2.7.0`. Embedded route surface: `BaseInterpreter` (`run_input`, `run_keyword`, `log_message`/`message`, start/end keyword hooks, `get_test_body_from_string`), `run_repl` kwargs, `Application.config`. `executeCell` is notebook-shaped. → one adapter module, pin `robotcode>=2.7,<2.8`, CI against latest robotcode; fallback: reimplement `run_repl` (~40 lines). RF internals move too (`IMPORTER` in `robot.running.namespace` on 7.3 vs `robot.running.importer` on 7.5).

## Single-shot batch — works
`run_cells([...])` / `python -m rfmcp_local batch FILE` in-process, no daemon: Requests 14 steps 1.72 s total; Browser 15 steps 2.5 s incl. graceful close; repeatable in one process (3× ~2.0 s, 0 leftover children; requires unregistering the logger between runs). `run_repl` chdirs to the detected project root → absolute paths.

## rf-mcp logic inside the helper — feasible
- Owner resolution via live namespace (same as rf-mcp today).
- Redaction learns secrets from named args and assigned variable names, scrubs args/messages/returns/vars/console; over-redacts (hid `username` in `${auth}`).
- Browser guard probes via the library instance before acting: missing element NOT_FOUND in 1.1 s vs 3 s timeout; bad selector INVALID_SELECTOR; overhead ≤ 3 ms (unmeasurable); can shorten per-step timeout via `set_browser_timeout`.
- `robotmcp.utils.hints.generate_hints` works unchanged but returned `[]` until the owner was passed as `session_search_order`; wording points to server tools (`get_session_state`) → needs local phrasing.
- PlatynUI safety guard: stdlib-only modules, but importing the `components.execution` package pulls the whole executor (511 ms) → load by file path. On the active Wayland/XWayland `:0` display it refused in 17 ms (no input sent); on a helper-owned Xvfb with isolation marker + X server PID it allowed the keyword; Xvfb removed at stop.
- Focus manager depends on `platynui_plugin.get_runtime` (200 ms import, no fastmcp) → plausible, not exercised.

## Windows (from code)
AF_UNIX, SO_PEERCRED, setsid, killpg, prctl, `/proc` are POSIX-only → `--tcp` (127.0.0.1 ephemeral port + token; wrong token rejected, tested on Linux). Windows: `DETACHED_PROCESS|CREATE_NEW_PROCESS_GROUP`; Job Object KILL_ON_JOB_CLOSE (replaces pdeathsig); stop = RPC then `TerminateProcess` (+ psutil tree); token file under `%LOCALAPPDATA%`. Named pipes possible (robotcode `start_serving_pipe`) but TCP+token simpler. robotcode `--wrapper` on Windows spawns a child instead of exec.

## Open questions
1. Ask upstream to make `BaseInterpreter`/`run_repl` public or ship a JSON client?
2. `--pdeathsig` monkeypatches `subprocess.Popen` (main thread only); libraries spawning from other threads are a risk.
3. Distribution: `rfmcp-local` wheel in the project venv vs file served as text; python3 on PATH (`py -S` on Windows).
4. Codex/Copilot sandboxes killing background daemons (not tested here).
5. Redaction + journal-secrets policy (journal keeps raw values in a 0600 file).
