"""VS Code (Copilot): reads Claude-format plugins (``chat.plugins.enabled``) and Claude-format hooks
(``chat.useHooks``) from ``.claude/``. Files mode shares the Claude Code layout (the manifest tracks shared files);
plugin mode writes the workspace recommendation (project scope) and prints the user settings.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..homes import vscode_claude_home
from ._base import MARKETPLACE_REPO, Options, Plan, marketplace_ops
from .claude_code import ClaudeCodeAdapter

USER_SETTINGS = {
    "chat.plugins.enabled": True,
    "chat.useHooks": True,
    "chat.plugins.marketplaces": [MARKETPLACE_REPO],
}


class VSCodeAdapter(ClaudeCodeAdapter):
    name = "vscode"
    pretty = "VS Code (Copilot)"
    cli = "code"

    def config_roots(self) -> list[Path]:
        home = Path.home()
        return [home / ".config" / "Code", home / "Library" / "Application Support" / "Code",
                home / "AppData" / "Roaming" / "Code", home / ".vscode"]

    def root(self, opts: Options) -> Path:
        if opts.scope == "project":
            return opts.project / ".claude"
        return vscode_claude_home()

    def plugin_plan(self, opts: Options) -> Plan:
        ops = marketplace_ops(self.settings(opts), opts) if opts.scope == "project" else []
        return Plan(agent=self.name, mode="plugin", ops=ops, notes=self.post_notes(opts, "plugin"),
                    stops=[self.root(opts), opts.project, Path.home()])

    def post_notes(self, opts: Options, mode: str) -> list[str]:
        settings = json.dumps(USER_SETTINGS, indent=2)
        if mode == "files":
            return ["VS Code runs these hooks once `chat.useHooks` is enabled in your user settings:\n"
                    + json.dumps({"chat.useHooks": True}, indent=2)]
        notes = ["Add to your VS Code user settings (Preferences: Open User Settings (JSON)):\n" + settings]
        if opts.scope == "project":
            notes.append(f"{self.settings(opts)} makes VS Code recommend the plugin in this workspace.")
        return notes

    def probe_payload(self, project: Path) -> tuple[str, dict[str, Any]]:
        return "UserPromptSubmit", {"hook_event_name": "UserPromptSubmit", "session_id": "rf-harness-doctor",
                                    "cwd": str(project), "prompt": "rf-harness doctor probe",
                                    "timestamp": "2026-01-01T00:00:00.000Z"}
