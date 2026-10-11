"""Claude Code: plugin mode registers the marketplace in settings.json; files mode copies the skill and launcher into
``.claude/`` (or ``~/.claude``) and merges the hook groups into ``settings.json``.

VS Code (Copilot) reads the same ``.claude/`` layout, which is why the shared hook commands use ``--agent auto``.
Adapted from robotframework-agentskills' ``adapters/claude_code.py`` (same author, Apache-2.0).
"""

from __future__ import annotations

from pathlib import Path

from .. import _assets
from ..homes import claude_home
from ._base import (
    MARKETPLACE_NAME,
    PLUGIN_ID,
    SUPPORT_DIR_NAME,
    Adapter,
    ConfigOp,
    Options,
    Plan,
    hook_marker,
    hooks_from,
    marketplace_ops,
    plugin_env_op,
    skill_targets,
    support_targets,
)


class ClaudeCodeAdapter(Adapter):
    name = "claude-code"
    pretty = "Claude Code"
    cli = "claude"

    def config_roots(self) -> list[Path]:
        return [claude_home()]

    def root(self, opts: Options) -> Path:
        if opts.scope == "project":
            return opts.project / ".claude"
        return claude_home()

    def settings(self, opts: Options) -> Path:
        return self.root(opts) / "settings.json"

    def support_dir(self, opts: Options) -> Path | None:
        return self.root(opts) / SUPPORT_DIR_NAME

    def hook_files(self, opts: Options) -> list[Path]:
        return [self.settings(opts)]

    def files_plan(self, opts: Options) -> Plan:
        assets = _assets.plugin_root()
        root = self.root(opts)
        support = root / SUPPORT_DIR_NAME
        hooks = hooks_from(assets, "hooks/hooks.json", support, opts)["hooks"]
        settings = self.settings(opts)
        return Plan(
            agent=self.name, mode="files",
            targets=skill_targets(assets, root / "skills") + support_targets(assets, support),
            ops=[ConfigOp("json_hooks", settings, f"merge rf-harness hooks into {settings}", ("hooks",), hooks,
                          hook_marker(support))],
            notes=self.post_notes(opts, "files"),
            stops=[root, opts.project, Path.home()],
        )

    def plugin_plan(self, opts: Options) -> Plan:
        settings = self.settings(opts)
        ops = marketplace_ops(settings, opts)
        if opts.scope == "user":
            ops += plugin_env_op(settings, opts)
        return Plan(agent=self.name, mode="plugin", ops=ops, notes=self.post_notes(opts, "plugin"),
                    stops=[self.root(opts), opts.project, Path.home()])

    def post_notes(self, opts: Options, mode: str) -> list[str]:
        if mode == "files":
            return ["Claude Code loads the rf-harness skill and hooks at the next session start."]
        scope = "project" if opts.scope == "project" else "user"
        notes = [
            f"{self.settings(opts)} registers the {MARKETPLACE_NAME} marketplace and enables {PLUGIN_ID}.",
            f"Claude Code installs it when you trust the marketplace, or now: claude plugin install {PLUGIN_ID} "
            f"--scope {scope}",
        ]
        if scope == "project":
            notes.append("Commit .claude/settings.json so every collaborator gets the plugin (Copilot CLI and VS Code "
                         "read it too).")
        return notes
