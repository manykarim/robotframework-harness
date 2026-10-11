# Files and directories

## In your project

| path | written by | content | commit? |
|---|---|---|---|
| `.claude/settings.json` | installer (plugin mode, Claude Code / Copilot / VS Code) | marketplace + `enabledPlugins` entries; files mode: hook entries | yes (team setup) |
| `.claude/skills/rf-harness/` | installer (files mode, Claude Code) | the skill | optional |
| `.github/copilot/settings.json` | installer (plugin mode, Copilot CLI, project scope) | marketplace entries | yes |
| `.codex/` | installer (files mode, Codex) | `hooks.json`, skill under `.agents/skills/` | optional |
| `.opencode/skills/rf-harness/`, `.opencode/plugins/rf-harness.js` | installer (OpenCode) | skill and JS plugin | optional |
| `.rf-harness/manifest.json` | installer | every file and config entry it wrote, with sha256 (for upgrade/uninstall) | no |
| `.rf/harness.json` | installer | chosen interpreter, runtime version, optional `env` defaults (e.g. `RFH_STATIC`) | no |
| `.rf/state/latest/` | live session | `page.txt`, `controls.txt`, `aria.yaml`, `source.html`, `screenshot.jpg` | no |
| `.rf/state/step-NNN-<keyword>/` | live session | earlier captures | no |
| `.rf/docs/` | docs helper | `<Library>.md`, `<Library>.full.md`, `kw/<Library>.<Keyword>.md` | no |
| `.rf/exec/` | live session | socket, pid, `timeouts.json` (learned live timeouts) | no |
| `.rf/lint/` | static checks | caches | no |
| `.rf/hook/` | hooks | `session.json` (per-session state), `hooks.jsonl` (one line per hook event) | no |
| `.rf/out/` | REPL/debugger | outputs of REPL calls | no |

The installer adds `.rf/` (and `.rf-harness/`) to `.gitignore`.

## In your home directory (user scope)

| path | content |
|---|---|
| `~/.rf-harness/manifest.json` | user-scope install manifest |
| `~/.claude/…`, `$CODEX_HOME` (`~/.codex`), `$COPILOT_HOME` (`~/.copilot`), `~/.config/opencode/` | agent configuration written at user scope (agent home overrides are honoured) |
| `~/.cache/rf-harness/` | caches (compiled launcher, keyword-name cache) |
