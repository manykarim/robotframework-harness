# Round 2 — stock `robotcode repl` instead of repl-server (2026-10-01)

Source: repl-only subagent report (saved by the coordinating session). Evidence: `proj/rfmcp_listener.py` (listener), `rfrepl.py` (stdlib client: start/step/wait/status/stop/build), `rfrepl_step.sh` (20-line bash+jq client), `feeder.py`, `scenario_*.sh`, `lifecycle*.sh`, `logs/` (latency.jsonl, results_summary.json, scenario/lifecycle logs), `run/*/steps.jsonl`.

## Verdict
repl-server is **not needed**. Stock `robotcode repl --plain` fed from a named pipe + a small locally installed listener writing JSONL gives per-step structured results across separate shell calls; rebuilt suites pass; shutdown is far cleaner (0.4 s with Browser vs 5.5–22 s + traceback). Costs: two plain-REPL quirks the client must handle, a listener hook relying on private APIs, POSIX-only pipe transport.

## Comparison with round 1 (n=30, each step a separate process; machine had other Browser jobs → slightly noisy)
| | repl-server (R1) | stock repl + pipe + listener (R2) |
|---|---|---|
| Start→ready | 0.85–1.09 s | 0.78–1.03 s |
| Browser `Get Title` py client | 81/92 ms | 66/71 ms |
| Browser `Get Title` bash client | 24/25 ms | 38/44 ms (tail+grep poll, jq) |
| Requests local assert py/sh | – | 73/92, 31/34 ms |
| `Get Text` assert / network GET (py) | – | 79/84, 170/192 ms |
| Structure | full tree, all log levels | per-step tree: name, owner, raw args, assign, status, message, INFO+ messages, assigned values, top-level return value, screenshot paths |
| Caught failures | correct | correct: TRY root / `Run Keyword And Ignore Error` PASS, inner failures as `caught_failures` |
| Failure stops rest of cell | yes | not by default (line-by-line); hook skips remaining lines (`skipped_after_failure`) |
| Shutdown with Browser | 5.5–22 s + TimeoutError | `.exit` 0.40–0.45 s; output.xml written with `-o`; 0 orphans |
| Protocol | undocumented `executeCell` | stock CLI + public listener v3 API (hook optional) |
| Code on host | 236-line py / 12-line bash client | listener 367 lines (~200 without hook) + 473-line py or 20-line bash client |

## How the plain REPL reads input
`input()` per line; after each line re-parses the buffer and runs as soon as it parses cleanly. Open FOR/IF/TRY keeps reading until `END`. Blank line inside an open block forces execution (broken block → "FOR loop must have closing END." instead of hanging); blank line at a fresh prompt does nothing. Lines starting with `.` at a fresh prompt are dot-commands. EOF/`.exit`/Ctrl-D → graceful exit (suite ends, outputs written, Browser closes). `#` comment lines do nothing and aren't kept by `.save`.

## Listener findings
- All three loading ways work: robot.toml profile `listeners = { "rfmcp_listener" = [] }` + `python-path` (`robotcode -p listen repl`); `ROBOT_OPTIONS="--listener /abs/rfmcp_listener.py"`; first cell `Import Library  /abs/rfmcp_listener.py` (GLOBAL library listener).
- The REPL runs inside robotcode's logger callback for the `Repl` marker keyword; listeners are called after that callback → listeners never see `Repl` start, top-level REPL items arrive with an empty stack → "stack empty at end" reliably = step finished. `Repl` only appears at exit (client filters it).
- Assigned variables read from context at `end_keyword` (assignment happens before the event). Return values without assignment need `log-level TRACE` (`Return:` message) or the hook.
- Hook (private: `LOGGER._other_loggers`, `interpreter.read_line`/`set_last_result`): `# rfmcp-step: ID` / `# rfmcp-end: ID` comment lines → begin/end records; exact consumed source recorded; top-level return values captured; rest of cell skipped after failure.
- Public-API-only fallback: `Comment  rfmcp-done  ID` sentinel (shows up in `.save` and output.xml).

## Recipes
- Start: `mkfifo .rf/in.fifo; RFMCP_JSONL=.rf/steps.jsonl setsid -f bash -c 'echo $$ >.rf/repl.pid; exec robotcode -p listen repl --plain --no-history -d out -o output.xml <>.rf/in.fifo >.rf/repl.log 2>&1'`, wait for first `{"t":"idle"}`. `<>` (read-write open) means the REPL holds its own write end → no keeper process.
- Step: `flock`, write `# rfmcp-step: ID\n<cell>\n\n# rfmcp-end: ID\n`, poll JSONL for `{"t":"end","id":ID}`. Client strips blank lines from the cell and folds `...` continuation lines.
- Long steps: `rfrepl.py step --timeout` → TIMEOUT; `rfrepl.py wait ID` later.
- Stop: `printf '\n.exit\n' > fifo`, wait a few s, then `kill -KILL -- -PGID`.
- Recovery: `start -- -i replay.txt` (passing step sources) → replays then reads the pipe (13 steps in 1.84 s).
- Build: passing steps from JSONL, imports hoisted to Settings; `browser_recorded.robot` and `requests_recorded.robot` PASS under `robotcode robot`; REPL `.save` output FAILS (keeps the failed assertion).

## Failure modes
- `...` continuation lines run as separate statements (`${d}  Create Dictionary` ran empty, `k1=v1` treated as a keyword) → client must fold.
- Multi-statement cell continues after a failure unless hooked; blank line inside a block ends it early.
- SIGINT/SIGTERM while idle ignored (same as repl-server); SIGINT during a keyword → "Execution interrupted", session survives.
- Killing only the REPL PID orphans node + 6 chromium; chromium has its own process group but exits when node dies → kill the REPL's group.
- Node inherits the pipe as stdin → a dead REPL can look like it has a reader → client checks PID before writing and every 200 ms while waiting (`.exit` inside a cell reported DEAD within 0.4 s).
- Keeper mode: keeper death → EOF → REPL exits cleanly in 0.43 s (output written, no orphans).
- Lock serialises 5 parallel clients; raw writes < PIPE_BUF (4096) stay intact even without the lock (results filtered by ID).
- A keyword reading stdin (`Evaluate  input()`) would swallow marker lines.
- `Log To Console` only in `repl.log`. Credentials in plain text in `values`.

## Codex PTY / VS Code `send_to_terminal`
Terminal driving gives text only (robotcode switches to plain mode when an agent is detected). Because the listener is loaded via robot.toml or `ROBOT_OPTIONS`, the same JSONL is written however input arrives → a terminal-driven agent can type `# rfmcp-step:` markers and read results via `cat`/`jq`. Hook wrapping the prompt_toolkit backend's `read_line` untested; `ROBOTCODE_REPL_PLAIN=1` is the safe default.

## Open questions
1. Hook on private RF/robotcode APIs → ask upstream for a supported "idle/input-consumed" event or plain-mode `--cell-delimiter`?
2. Windows: no `mkfifo`; inbox-file feeder (`--mode inbox`, 20-line `feeder.py`) 61 ms/step on Linux; Windows + cleanup (Job objects / `taskkill /T`) untested.
3. Codex/Copilot sandboxes keeping background processes alive.
4. Resource reload after edits (inherited from R1, not re-tested).
5. Secret redaction in the JSONL.
