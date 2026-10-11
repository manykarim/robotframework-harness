# Persistent stepwise RF sessions across separate agent shell calls — findings (2026-10-01)

Source: stepwise subagent report (saved by the coordinating session; the harness blocks subagent report files). Evidence: `logs/` (24 logs), `out/`, scripts in this folder.

## Verdict: approach A — `robotcode repl-server` in the background + a one-shot client per step
Only approach with structured JSON per keyword; keeps all in-process state (browser, Requests sessions, `${resp}` objects, variables); no FIFO/sentinel tricks. A client-side journal reproduces `build_test_suite` as a pure function of the journal: both journal-built suites passed under `robotcode robot` (saucedemo 15 steps → `out/A_browser/recorded.robot`; restful-booker 12 steps → `out/A_requests/recorded.robot`).

## Latency (each step a separate process; `Get Title` on a logged-in page, n=30; C n=10)
| Approach | Setup | Median / p90 per step |
|---|---|---|
| A repl-server + Python client (`rfstep.py`, stdlib, 236 lines) | 0.85–1.09 s to listen | 81 / 92 ms |
| A repl-server + bash `/dev/tcp` client (`rfstep.sh`, 12 lines) | same | 24 / 25 ms |
| B `repl --plain` fed by FIFO + sentinel | ~1.0 s | 71 / 77 ms |
| C fresh `repl` per step, Browser reattach | node started once | 1290 / 1321 ms (bare REPL start ~1.0 s) |
| D `robot-debug` paused at `(rdb)` | 2.7 s | 54.5 / 58 ms |

- B: text only; "`[ FAIL ]` in output" heuristic wrongly marked 2/31 steps failed (caught TRY/EXCEPT, `Run Keyword And Ignore Error`); `.save` keeps sentinel lines and failed steps.
- C: Browser only via an undocumented hook — the node process keys state by gRPC peer, so a new process sees an empty catalog; `Call Method` on `PlaywrightState.set_peer_id()` fixes it. Requests: only JSON-able variables survive via `-V state.json`.
- D: one line at a time; FOR/IF blocks fail at `(rdb)`.

## repl-server behaviour verified
- Separate connections share one interpreter (own protocol object each) → state persists across calls.
- Concurrent calls serialize (second client waited for first one's `Sleep`).
- Client disconnect doesn't break the session (cell completes; result lost to that client only).
- `interrupt` works: running keyword fails with `Execution interrupted`, session survives.
- Two servers in parallel have separate state. Unix-socket mode (`--pipe-server`) works.
- Whole cell = one string: multi-line FOR/IF/TRY/VAR work; a failed keyword stops the rest of the cell.
- No robotcode client exists; protocol is shaped for the VS Code notebook.

## Protocol notes
- Start: `robotcode repl-server --tcp [ADDR:]PORT | --pipe-server PATH | --stdio [-d OUT] [-o output.xml -l log.html] [-v/-V/-P]` (defaults stdio, port 6601, bind 127.0.0.1).
- Framing: `Content-Length: N\r\n\r\n` + UTF-8 JSON-RPC 2.0; params as dict with Python arg names.
- Methods: `initialize{message}` → "yeah initialized …" (optional); `executeCell{source, language_id}` → `{success: true|false|null, items:[{mime:"x-application/robotframework-repl-log", data:"<JSON string>"}, {mime:"application/vnd.code.notebook.stderr", data}?]}`; `interrupt` (SIGINT inside server); `shutdown` (suite end → log files → exit); `exit` not useful.
- `data` is double-encoded; root `{node_type:"root", items}`. Keyword nodes: `name, owner, args, assign, type (KEYWORD/FOR/ITERATION/IF/TRY/…), status, message, start_time, end_time, elapsed_time, items`. Message nodes: `{message, level TRACE…FAIL, html, timestamp}` — all levels, so `Return: <repr>` gives every return value. Browser failure screenshots arrive as `html:true` message with `browser/screenshot/fail-screenshot-N.png`.
- `success` = status of the last ended node (correct for caught failures); `null` when nothing ran ("Test cannot be empty." in stderr).

## Problems / risks
- Idle server ignores SIGTERM/SIGINT; only `shutdown` RPC ends it: 0.27 s without Browser, 5.5–22 s with Browser, ending in a `TimeoutError` traceback.
- Killing only the server PID orphans the Playwright node process; start with `setsid` and kill the process group (0 orphans; chromium exits with node).
- Edited resource files are not reloaded (re-`Import Resource` is a no-op).
- `Log To Console` output goes to the server's log, not the response.
- Missing `-d` breaks Browser unless created first.
- No authentication; `Evaluate` = arbitrary Python → unix socket in a private directory.
- RequestsLibrary credentials in plain text in JSON and journal.
- Find the server PID by port, not `pgrep -f` (matched the agent's own shell once).

## Recommended layout
- Remote MCP stays stateless. A `session_bootstrap` tool returns start commands + the text of the client (`rfstep.py` or `rfstep.sh`), which the agent writes to disk.
- Step: `python3 .rf/rfstep.py run --pipe .rf/rs.sock --journal .rf/journal.jsonl '<cell>'`.
- `build_test_suite(journal)` keeps passing cells and hoists `Import …` lines into `*** Settings ***`.
- Teardown: `shutdown` RPC, wait ≤ ~25 s, then `kill -KILL -- -PGID`.

## Open questions
1. `executeCell` is undocumented → pin robotcode or ask upstream for a CLI client.
2. Report shutdown/signal behaviour upstream?
3. Do Codex / CI sandboxes kill background processes when a shell call ends? (would force approach C). Only Claude Code's Bash verified.
4. Iterating on user keywords given the resource-reload issue.
5. Windows (named pipes, group cleanup) untested.
6. Steps longer than the client timeout: no polling/async path.

## Files
`rfstep.py` (stdlib client: `run --json/--journal`, `build`, `stop`), `rfstep.sh` (bash-only), `fifo_repl.sh` (B), `oneshot_step2.sh` (C Browser `set_peer_id`), `oneshot_req.sh` (C Requests), `debug_fifo.sh` (D), `latency_bench.sh`, `out/A_*/recorded.robot`.
