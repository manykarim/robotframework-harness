# Deep research: remote MCP + robotcode (2026-10-01)

Source: research subagent report (web + local robotcode 2.7.0 source). Saved verbatim-in-substance by the coordinating session.

## Summary

1. **A remote MCP server cannot make the client execute anything or write files.** Current spec 2026-07-28: servers offer resources/prompts/tools; clients offer only elicitation; roots, sampling, logging are deprecated (https://modelcontextprotocol.io/specification/2026-07-28/deprecated). Server-to-client requests are limited to elicitation/sampling/roots via MRTR (https://modelcontextprotocol.io/specification/2026-07-28/basic/patterns/mrtr). MCP Apps are sandboxed iframes. The only path to local robotcode execution is tool text persuading the agent's model to act under the host's own permissions (the same channel prompt injection uses). None of Claude Code, Codex, VS Code/Copilot CLI, Cursor, OpenCode lets a server write files; all configure remote HTTP servers.
2. **MCP went stateless on 2026-07-28**: `initialize` and `Mcp-Session-Id` removed; state = "explicit, server-minted handles passed as ordinary tool arguments" (https://modelcontextprotocol.io/specification/2026-07-28/changelog). Auth still OPTIONAL; if used, OAuth 2.1 + PRM + RFC 8707 + CIMD (DCR deprecated). FastMCP 4.0 (GA 2026-08-31, now 4.0.10) supports both eras, adds `SessionId`/`UserSession` (Redis-backed; "unauthenticated session is a bearer handle"), MRTR tools, `stateless_http` for legacy clients (https://gofastmcp.com/servers/sessions). rf-mcp is on fastmcp 3.4.4 / mcp 1.28.1.
3. **robotcode**: latest release 2.7.0 (2026-07-14, Apache-2.0). `main` has 123 unreleased commits incl. `robotcode doc` (live libdoc alternative, 09-30), REPL exit status on failure, RF 7.5 support. Verified on 2.7.0: piped `robotcode repl` exits 0 on `Fail`/unknown keyword and continues. The official agent skill (robotcodedev/robotframework-agent-plugins) already documents the unreleased `doc` + exit-code behaviour. Maintainer issue #500 "RobotCode MCP Server" (2025-09-03) is open, unimplemented; upstream chose skill + agent auto-detection; the skill says not to "detour into ... an MCP probe". https://robotcode.io/03_reference/ai-agents
4. **repl-server** = JSON-RPC with LSP framing over stdio/tcp (default 127.0.0.1:6601)/socket/pipe; methods `executeCell`, `interrupt`, `shutdown`, `exit`; backend of the VS Code notebook kernel (`notebook.ts` spawns `repl-server --pipe`); **no auth** (keep on loopback/unix socket). It is the only released way to keep RF state across separate agent shell calls — Claude Code's Bash cannot write stdin, while Codex (`write_stdin` PTY) and VS Code (`send_to_terminal`) can drive `robotcode repl` interactively.
5. **Third parties can add `robotcode <cmd>` subcommands** via pluggy entry-point group `robotcode`, hook `register_cli_commands` — verified locally (scratch plugin appeared in `robotcode --help`, honoured `--format json`). Undocumented/internal; sub-packages pinned `==2.7.0`.
6. **Skills over MCP (`io.modelcontextprotocol/skills`) is Final** (SEP-2640, 2026-09-13), client support thin (ChatGPT/fast-agent partial; none listed for Claude Code, Codex, VS Code, Cursor) — https://modelcontextprotocol.io/extensions/client-matrix. FastMCP `SkillsDirectoryProvider` serves `skill://` resources.
7. **Advisor-pattern cost**: ask server → run shell → forward output → read diagnosis = 2–3 model round-trips per step; forwarding output makes the model re-emit it as tool-call arguments = output tokens (5× input price on current Claude models; https://platform.claude.com/docs/en/about-claude/pricing). Measured: `results summary` 217 B, `results log` ~10 KB. Protocol should accept digests only.
8. **Privacy**: RequestsLibrary logs request/response headers+bodies at INFO (up to 10k chars) (https://github.com/MarketSquare/robotframework-requests/blob/master/src/RequestsLibrary/log.py); verified `robotcode results log` echoes them. Redact on the client, RF 7.4 `Secret`, ARIA/structural digests instead of DOM/screenshots.
9. **Internal evidence** (`rf-mcp/experiments/bundle-agent-skills-eval/report_hard2x2.md`, `report_conf.md`): live local rf-mcp +0.38 on hard tasks; skill substitutes (≤0 stacked). A pure-advisor remote rf-mcp gives up the live execution that produced the gain → becomes "a skill over HTTP" competing with robotcode's own skill.

## 1. robotcode

### 1.1 Versions
PyPI/GitHub (https://pypi.org/pypi/robotcode/json, https://github.com/robotcodedev/robotcode/blob/main/CHANGELOG.md): 2.7.0 (2026-07-14), 2.6.2 (06-15), 2.6.1, 2.6.0 (06-09). 2.7.0: test-run `wrapper` (profile/`--wrapper`/`ROBOTCODE_WRAPPER`; applies to run/debug/repl/repl-server/notebook kernel; https://robotcode.io/03_reference/wrapper), trustworthy analysis cache, compact JSON fix, `supportsParseInclude` in discover JSON. 2.6.x: `analyze code --code/--severity/--output-format` (json/sarif/github/gitlab), AI docs ranking debugger before REPL.
Unreleased on main (https://github.com/robotcodedev/robotcode/compare/v2.7.0...main, 123 commits): `robotcode doc` (keywords/keyword/lib/browse, `--format json`, 09-30); REPL unhandled failures fail the exit code (09-28) + input-error reporting; REPL profile/`--source` fixes; RF 7.5; selection by metadata; library-load timeout fixes; skill synced into the VS Code extension.

### 1.2 Commands (https://robotcode.io/03_reference/cli)
| Command | Purpose | Output |
|---|---|---|
| `discover` (all/tests/suites/tags/tasks/files/info) | inventory | `--format json` |
| `libdoc` (2.7.0), `doc` (main only) | keyword docs | JSON (`doc`) |
| `analyze code` | static checks; bitmask exit 0/1/2/4/8 | json/sarif/github/gitlab |
| `robot`/`run` | run suites | output.xml |
| `results` summary/show/log/stats/diff | read runs; `log --extract` artefacts | `-f json/toml` |
| `repl`/`shell` | interactive; `.vars .imports .kw .doc .save .exit` + debugger cmds | text |
| `robot-debug`/`run-debug` | `(rdb)` prompt; breaks on first uncaught failure by default | text |
| `repl-server` | JSON-RPC for external clients | JSON |
| `debug`/`debug-launch` | DAP server ("requires a DAP client, such as VS Code") | DAP |
| `language-server` | LSP | LSP |
Extras: skill minimum `robotcode[runner,analyze,repl]`; `replserver`, `debugger` separate.

### 1.3 repl-server (local source)
`ReplServerProtocol`: `initialize` ("yeah initialized …"), `executeCell(source, language_id)`, `interrupt`, `shutdown`, `exit`; LSP `Content-Length` framing; modes `--stdio` (default), `--tcp` (6601, bind 127.0.0.1), `--socket`, `--pipe`, `--pipe-server`; no auth. Output MIME `x-application/robotframework-repl-log` (JSON keyword tree) and `application/vnd.code.notebook.stderr`. Used by the VS Code notebook kernel (https://github.com/robotcodedev/robotcode/blob/main/vscode-client/extension/notebook.ts). Skill: "use it only when such an integration is explicitly needed."

### 1.4 AI-agent guidance and skill
https://robotcode.io/03_reference/ai-agents: discover, doc/libdoc, robot-debug (primary), repl (only when no test exists), results, analyze, robot; AGENTS.md; no MCP mention. Skill: https://github.com/robotcodedev/robotframework-agent-plugins (2026-05-29, Apache-2.0, Open Plugins format https://open-plugins.com/). Install: Claude Code `claude plugin marketplace add robotcodedev/robotframework-agent-plugins` + `claude plugin install robotcode@robotframework-agent-plugins`; Copilot CLI same with `copilot`; Codex `.codex-plugin`; VS Code bundled (`robotcode.ai.enableChatPlugins`); evals dir with 10 cases. SKILL.md ~34 KB + references (repl, debugging, results, analyze, config, install, authoring, large-projects, workflows): forbids `uvx`/`pipx` (must use project venv); REPL/robot-debug are "interactive terminal session[s] you drive line by line", piping is the fallback; `robotcode doc` first; https://robotcode.io/llms-full.txt; "don't detour into external tools / an MCP probe". Agent detection (`plugin/_agent_detection.py`): CLAUDECODE, CLAUDE_CODE, CURSOR_AGENT, CODEX_CI, CODEX_THREAD_ID, COPILOT_AGENT, VSCODE_AGENT, OPENCODE, GEMINI_CLI, AI_AGENT, AGENT…; overrides `ROBOTCODE_FORCE_AI_AGENT` / `ROBOTCODE_NO_AI_AGENT`; detected → no colour, no pager, plain REPL backend.

### 1.5 MCP plans
https://github.com/robotcodedev/robotcode/issues/500 (maintainer d-biehl, 2025-09-03): "We need an MCP Server… suites/tests/tags, execute tests, analyse project, analyse output". Open, one community comment, no PR; no MCP code in 2.7.0.

### 1.6 Plugins
`pluggy.PluginManager("robotcode")` + `load_setuptools_entrypoints("robotcode")`; hooks `register_cli_commands() -> List[click.Command]`, `register_tool_config_classes()`. Built-ins register the same way (`[robotcode] repl_server = robotcode.repl_server.hooks`). Verified: scratch dist-info `[robotcode] rfmcp_probe = rfmcp_probe.hooks` → `robotcode mcp-probe`, `app.print_data` → JSON under `--format json`. `@pass_application` gives config/profiles; `@wrappable` opts into wrapper re-exec. Not publicly documented; sub-packages pinned `==2.7.0`.

### 1.7 License
Apache-2.0 (all 12 robotcode dists + agent-plugins repo); rf-mcp Apache-2.0.

### 1.8 Driving the REPL per agent
| Agent | Interactive? | Mechanism |
|---|---|---|
| Codex | yes | `unified_exec` PTY + `write_stdin` |
| VS Code Copilot | yes | `send_to_terminal` (https://code.visualstudio.com/updates/v1_115) |
| Claude Code | no | no stdin/TTY (https://github.com/anthropics/claude-code/issues/41722) → pipe, repl-server + one-shot client, or tmux |
Verified 2.7.0: `printf 'Log hello\nFail boom\nLog after\n' | robotcode repl` → `[ FAIL ] boom`, continues, exit 0.

## 2. MCP constraints
### 2.1 Spec timeline
- 2025-06-18: structured output, elicitation, resource links, resource-server OAuth + RFC 8707, `MCP-Protocol-Version`, batching removed.
- 2025-11-25: URL-mode elicitation, experimental tasks, tool use in sampling, icons, CIMD, OIDC discovery.
- 2026-07-28 (https://blog.modelcontextprotocol.io/posts/2026-07-28/): `initialize` removed, per-request `_meta`, mandatory `server/discover`; `Mcp-Session-Id` removed, handles (SEP-2567); MRTR (`InputRequiredResult`, opaque `requestState`); `subscriptions/listen`; no resumable streams; `Mcp-Method`/`Mcp-Name` + `x-mcp-header`; `ttlMs`/`cacheScope`; tasks → extension; roots/sampling/logging deprecated (removal ≥ 2027-07-28); DCR → CIMD; extensions framework.

### 2.2 Client-side execution: not possible
MRTR only allows Elicit/CreateMessage/ListRoots on tools/call, resources/read, prompts/get. "Hosts must obtain explicit user consent before invoking any tool". MCP Apps sandboxed (https://modelcontextprotocol.io/docs/extensions/apps). Skills extension: "Host-side code execution… require explicit per-skill user approval" (https://modelcontextprotocol.io/extensions/skills/overview).

### 2.3 Useful features for a remote rf-mcp
Tools+`outputSchema`: yes (knowledge, plans, digest diagnosis). Resources: yes (cacheable cookbooks; `@server:uri` in Claude Code). Prompts: yes (slash commands). Elicitation: asks the user, never the machine. Roots/sampling/logging: deprecated. Tasks: server-side work only. MCP Apps: viewers in Claude web/Desktop, VS Code, Cursor — not Claude Code. Skills extension: thin. Server `instructions`: used by Claude Code with tool search.

### 2.4 Stateless HTTP
One POST per request → JSON or request-scoped SSE; no `Last-Event-ID`; closing cancels; MUST validate `Origin` (https://modelcontextprotocol.io/specification/2026-07-28/basic/transports/streamable-http). Legacy clients still use sessions. Design rule: no per-user RF state on the server; client journals or authenticated handles.

### 2.5 Auth
Optional; if used OAuth 2.1, RFC 9728, RFC 8707, PKCE, CIMD, RFC 9207, no token passthrough (https://modelcontextprotocol.io/specification/2026-07-28/basic/authorization).

### 2.6 Clients
| Client | Remote config | Notes |
|---|---|---|
| Claude Code | `claude mcp add --transport http <name> <url> [--header]`; `.mcp.json` `{"type":"http","url"}` | OAuth via `/mcp`; `headersHelper`; v2 runtime negotiates 2026-07-28 (v2.1.232+); form+url elicitation; tool result warn 10k / cap 25k tokens (`MAX_MCP_OUTPUT_TOKENS`); tool search default on (https://code.claude.com/docs/en/mcp) |
| Codex | `config.toml` `[mcp_servers.x] url`, `bearer_token_env_var`, `http_headers` | `codex mcp login`; `tool_timeout_sec` 60 |
| VS Code | `.vscode/mcp.json` `{"servers":{"x":{"type":"http","url"}}}` | |
| Copilot CLI | `copilot mcp add --transport http …` | |
| Cursor | `mcpServers.x.url/headers` | roots, elicitation, Apps |
| OpenCode | `"mcp":{"x":{"type":"remote","url"}}` | |
None lets a server write files.

## 3. Patterns
1. Knowledge-only remote (AWS Knowledge MCP, anonymous, rate-limited).
2. Advisor returns command the agent runs (shadcn `get_add_command_for_items`, https://www.shadcn.io/mcp/tools).
3. Local MCP driving remote infra + tunnel (BrowserStack MCP + BrowserStack Local).
4. Local bridges/tunnels (AWS AgentCore MCP bridge; Claude Code Remote Control outbound polling). Tunnel risks: https://nhimg.org/faq/why-do-reverse-tunnels-change-mcp-security-risk/
5. Remote MCP exposed as local CLI (https://github.com/mcpshim/mcpshim).
6. Code execution with MCP — keep intermediate data out of the model; 98.7% token reduction in one workflow (https://www.anthropic.com/engineering/code-execution-with-mcp).

Skills vs MCP (https://www.anthropic.com/engineering/equipping-agents-for-the-real-world-with-agent-skills, https://speakeasy.com/blog/skills-vs-mcp): remote MCP wins for fresh/central knowledge (one fix vs stale `>>`/`>>>` skill bug), real computation (fuzzy keyword matching, error classification, suite linting), one artefact for all agents. Skill wins when the job is mostly using a local CLI correctly (robotcode's position), offline/private, zero infra. Tool search cuts MCP context overhead ~85%. Convergence via Skills-over-MCP + FastMCP `SkillsDirectoryProvider`.

Advisor loop cost: 2–3 model round-trips vs 1 for local `execute_step`; forwarded output = output tokens at 5× (Opus 5.5 $4/$20, Sonnet 5.5 $2/$10 per MTok). Sizes: `results summary` 217 B text / 372 B JSON; `results show` 310/744 B; `results log` 9,986/13,593 B. Mitigations: batch plans + error→fix tables interpreted locally; rules as cached resource/skill; digest locally (`hints.py` is ~1,500 lines pure stdlib — could run on the client).

## 4. Security / privacy
RequestsLibrary INFO logging of headers/bodies (verified via `results log`); DOM/screenshots contain SUT PII; OWASP MCP01 (https://owasp.org/www-project-mcp-top-10/2025/MCP01-2025-Token-Mismanagement-and-Secret-Exposure), OWASP MCP cheat sheet. Mitigations: digest-only schemas with caps; client-side redaction (Authorization, Cookie, token, password, JWT, email, card); RF 7.4 `Secret`, `Set Log Level NONE`, `--removekeywords`; ARIA/structural digests, no screenshots by default; server: no payload persistence/logging, OTel without args, privacy statement; repl-server on unix socket/loopback, never tunnelled.

## 5. FastMCP
4.0.10 (2026-09-25); 4.0.0 (2026-08-31) on MCP SDK v2 (mcp 2.2.0), full 2026-07-28 + per-connection negotiation. `mcp.run(transport="http")` / `mcp.http_app()`; `stateless_http=True` / `FASTMCP_STATELESS_HTTP=true`; `@mcp.custom_route("/health")`; nginx `proxy_buffering off`. State: `ctx.set_state` request-scoped; `UserSession`/`SessionId` + `SessionProvider` (memory/Redis, `TTLClampWrapper`); MRTR needs shared `RequestStateSecurity` key across replicas. Deploy: Cloud Run (streamable HTTP, IAM default, `gcloud run services proxy`), Prefect Horizon (`*.fastmcp.app/mcp`, OAuth, free personal tier). rf-mcp's process-global RF context can't scale across replicas as-is; 3→4 upgrade mostly drop-in.

## 6. Architecture options
| # | Option | Pros | Cons | Risks |
|---|---|---|---|---|
| A | Pure-advisor remote MCP; robotcode via agent shell | zero local footprint, central updates, every client, stateless/cheap | loses live execution + DOM inspection (rf-mcp's proven value); 2–3 round-trips/step; output-token cost; overlaps robotcode skill; Claude Code limited to piped batches | agents skip it (skill says avoid MCP probes); users paste secrets; permission policies block advisor-driven execution; 2.7.0 quirks |
| B | Remote MCP + thin local helper (robotcode plugin `rfmcp step/digest/hints/save` or RF listener) | persistent stepwise even on Claude Code (repl-server client); redacted compact digests; reuses robot.toml/profiles/wrapper; offline-capable | local install (into the venv robotcode already needs); internal plugin API pinned `==2.7.0`; two artefacts to version | upstream churn; duplicating `doc`/skill; coordinate with #500 |
| C | Remote MCP + local bridge/tunnel | server keeps control; 1 call/step | a local server with more hops; latency/NAT | RCE into dev machines; enterprise blocker; highest ops burden |
| D | Skill only + robotcode | no infra; offline/private; aligned with upstream; standalone skill value +0.33 | static; reinstall to fix; no computation; per-agent packaging; Claude Code REPL gap | stale guidance silently harms (the `>>>` bug) |
| E | Keep local stdio | best measured correctness (+0.38); 1 call/step; no egress | big local server (~9,150-line server.py, 40+ tools); fails "not on user's machine"; one project/process | continued engine maintenance |

Research agent's suggested prototype: **"A + optional B"** — stateless anonymous remote knowledge/computation server with digest inputs + resources/prompts/skills; optional pip plugin (`robotcode rfmcp step|digest|hints|save`) for stepwise state and local redaction; fallback piped REPL batches + `results summary -f json` digests. Next: benchmark A/B/E on hard 2×2 fixtures with Claude Code and Codex; pick 2.7.0-quirks vs next release; coordinate with upstream #500; define digest schema + redaction rules.
