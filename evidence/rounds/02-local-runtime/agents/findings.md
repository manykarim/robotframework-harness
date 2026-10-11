# Round 2 — local helper channel across coding agents (2026-10-01)

Source: agents subagent report (saved by the coordinating session). Evidence: `orchestrate.py` (runner), `analyze.py` (tool-call extractor), `common/{daemon.py,client.py,echo_mcp_server.py}`, `results_summary.json`, `logs/toolcalls_all.txt`, `logs/codex_s5_rollout_toolcalls.txt`, `logs/sandbox_probe.log`, `runs/<agent>/<scenario>/{agent_stdout.log,result.json,toolcalls.json}`.

## Short answer
Yes in all four runnable CLI agents, **if the helper self-detaches with setsid**. 34 headless sessions: claude-haiku-4-5, codex gpt-5.6-luna@low, opencode MiniMax-M2.7, copilot gpt-4.1 (gpt-5-mini and claude-haiku-4.5 "model not supported" on this Copilot account). Daemon observed from outside (pid, heartbeat, signal log).
Limits: sandboxes untested — Codex ran with `--dangerously-bypass-approvals-and-sandbox` because bwrap can't start on this host (Ubuntu 24.04 AppArmor `apparmor_restrict_unprivileged_userns=1`); Claude's sandbox can't run here (no socat, userns blocked). Copilot VS Code from docs only.

## Matrix
| | Claude Code 2.1.286 | Codex 0.153.4 (no sandbox) | OpenCode 1.15.12 | Copilot CLI 1.0.54 | Copilot VS Code (docs) |
|---|---|---|---|---|---|
| Self-detached daemon (double fork+setsid / `setsid -f`): survives between calls + after session end | yes | yes | yes | yes | expected |
| Plain `nohup cmd &` | survives | **killed when the call ends** | survives | survives (SIGHUP at call end, nohup saved it) | ? |
| Agent's own background mode | `run_in_background`: works in-session; **SIGTERM ~5 s after `-p` ends**; 30-min limit | `exec_command` tty: works in-session; **SIGKILL when codex exits** | none | `bash mode=async detach=true`: **survives session end** | `run_in_terminal mode=async` |
| Unix socket / TCP 127.0.0.1 | ok/ok | ok/ok | ok/ok | ok/ok | – |
| curl saucedemo / headless chromium via robotcode | ok/ok | ok/ok | ok/ok | ok/ok | – |
| Writes `~/.cache`, `/tmp` | ok | ok | ok | ok | – |
| Write to a running process's stdin | **no** | **yes** (`exec_command` + `write_stdin`, PTY) | **no** | **yes** (`write_bash`/`read_bash`) | `send_to_terminal` (1.115+) |
| `sleep 70` without timeout | finished (default 120 s, max 600 s, then auto-backgrounds) | **returned after 10 s** (max yield 30 s/call); keeps running, poll via `write_stdin`; luna gave up | finished (default 120000 ms; `OPENCODE_EXPERIMENTAL_BASH_DEFAULT_TIMEOUT_MS`) | sync returns "still running" after 30 s; `read_bash` later got result | sync until timeout, then background + `get_terminal_output` |
| Remote HTTP MCP + bearer header | verified | verified | verified | verified | docs |

**Real stack end to end** in all four agents, four separate calls: `setsid -f robotcode repl-server --pipe-server .rf/rs.sock -d out` → `rfstep.py` open saucedemo → login + `Get Url` = inventory.html → `rfstep.py stop`. All passed (`runs/*/s8_replserver/`), no node/chromium left.

## Remote MCP config that worked (dummy FastMCP checking `Authorization: Bearer`)
- Claude: `claude mcp add -t http rfmcp URL -H "Authorization: Bearer $T"` or `{"mcpServers":{"rfmcp":{"type":"http","url":URL,"headers":{"Authorization":"Bearer …"}}}}` (`--mcp-config` / `.mcp.json`).
- Codex: `codex mcp add rfmcp --url URL --bearer-token-env-var RFMCP_TOKEN` → `[mcp_servers.rfmcp] url=… bearer_token_env_var="RFMCP_TOKEN"` (`http_headers`/`env_http_headers` also exist).
- OpenCode: `opencode.json` `"mcp":{"rfmcp":{"type":"remote","url":URL,"headers":{"Authorization":"Bearer {env:RFMCP_TOKEN}"},"oauth":false}}`.
- Copilot CLI: `copilot mcp add --transport http --header "Authorization: Bearer $T" rfmcp URL` or `--additional-mcp-config @f.json` (`{"mcpServers":{"rfmcp":{"type":"http","url":URL,"headers":{…},"tools":["*"]}}}`); also reads workspace `.mcp.json`.
- VS Code: `.vscode/mcp.json` `{"servers":{"rfmcp":{"type":"http","url":URL,"headers":{"Authorization":"Bearer ${input:rfmcp-token}"}}},"inputs":[{"type":"promptString","id":"rfmcp-token","password":true}]}`.

## Gotchas (with evidence)
1. Unix socket path limit: 111-byte absolute path → `AF_UNIX path too long` (108 Linux / 104 macOS); every agent fell back to TCP in the first run (`runs/*/s1_detach_v0_longpath/`). Relative path after `chdir` fixes it.
2. Codex kills `&` children at call return; only setsid escapes (`runs/codex/s3_naive` vs `s7_setsid`).
3. Copilot runs tool calls in parallel: gpt-4.1 issued 6 commands at once, `stop` before `ping` (`runs/copilot/s2_cross_env`).
4. robotcode resolves relative `-d out` against its project root (nearest pyproject/robot.toml), not cwd → 48 s of Browser failures (`selftest/repl_probe.log`). Absolute `-d` or a project `robot.toml` fixes it.
5. Codex default sandbox (per linux-sandbox README; untestable here): bwrap `--unshare-pid` (+ `--unshare-net` when network off) → daemon dies with the call's PID namespace even with setsid; TCP localhost not reachable from next call; outbound network off by default; AF_UNIX allowed except managed-proxy mode.
6. Claude sandbox (opt-in): optional seccomp filter blocks unix sockets unless `allowAllUnixSockets`; `allowUnixSockets`/`allowLocalBinding` macOS-only; `excludedCommands` escape hatch.
7. VS Code sandbox `chat.agent.sandbox.enabled` (off by default; Linux needs bwrap + socat); tool has `requestUnsandboxedExecution`.
8. Claude `run_in_background` sends SIGTERM at exit; idle repl-server ignores SIGTERM → orphan risk.

## Recommendations for the local helper
- Self-daemonize: `helper start` = double fork + setsid, stdio → log, pid file, one JSON ready line within ~2 s, idempotent (ping first).
- `stop` = shutdown RPC then kill the process group; idle auto-exit (30–60 min) because agents end sessions without stopping.
- Don't rely on agent background tools or interactive stdin.
- Transport: unix socket at a short path (relative `.rf/rs.sock` or `$XDG_RUNTIME_DIR/rfmcp/<hash>.sock`, dir 0700); fallback TCP 127.0.0.1 + token (Windows, AF_UNIX-blocking sandboxes).
- Sandboxed agents (Codex workspace-write, Claude sandbox): document user-run or approved-unsandboxed `start`; client then only needs a unix-socket connect.
- Client calls block ≤ ~25 s (Codex 30 s max yield, Copilot 30 s initial wait); long keywords return `{"status":"running","job":N}` + `wait N`.
- Serialize in the helper, number steps; agent guidance: one step per call, never parallel.
- Pin robotcode root (project `robot.toml` or absolute `-d`).

## Sources
VS Code: https://code.visualstudio.com/docs/agents/run/tools, https://code.visualstudio.com/docs/agents/run/approvals, https://code.visualstudio.com/docs/agents/run/agent-sandboxing, https://code.visualstudio.com/docs/agents/reference/mcp-configuration, https://code.visualstudio.com/updates/v1_115. Claude: https://code.claude.com/docs/en/headless, https://code.claude.com/docs/en/tools-reference, https://code.claude.com/docs/en/sandboxing. Codex: https://learn.chatgpt.com/docs/config-file/config-reference, openai/codex `codex-rs/linux-sandbox/README.md`. OpenCode: https://opencode.ai/docs/mcp-servers/.

## Housekeeping
Copied agent credentials and agent home dirs deleted; probe files in `~/.cache` and `/tmp` removed; all own processes gone. Not touched: ~10 Browser node + headless_shell processes from `~/workspace/rf-mcp/.venv`, 4+ days old, parented to systemd --user (possible OOM risk).
