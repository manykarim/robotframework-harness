"""GitHub Copilot CLI: plugin mode writes the marketplace entries Copilot reads (``.claude/settings.json`` and
``.github/copilot/settings.json`` in a project, ``~/.copilot/settings.json`` for the user); files mode installs the
skill and a Copilot-format hooks file (camelCase events; sessionEnd is not used because Copilot fires it after every
run): ``.github/hooks/rf-harness.json`` (runs only in trusted folders) or ``$COPILOT_HOME/hooks/rf-harness.json``.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .. import _assets
from ..homes import copilot_home
from ._base import (
    MARKETPLACE_NAME,
    PLUGIN_ID,
    SUPPORT_DIR_NAME,
    Adapter,
    FileTarget,
    Options,
    Plan,
    hooks_from,
    marketplace_ops,
    skill_targets,
    support_targets,
)


class CopilotCliAdapter(Adapter):
    name = "copilot-cli"
    pretty = "GitHub Copilot CLI"
    cli = "copilot"

    def config_roots(self) -> list[Path]:
        return [copilot_home()]

    def base(self, opts: Options) -> Path:
        return opts.project / ".github" if opts.scope == "project" else copilot_home()

    def hooks_file(self, opts: Options) -> Path:
        return self.base(opts) / "hooks" / "rf-harness.json"

    def support_dir(self, opts: Options) -> Path | None:
        return self.base(opts) / "hooks" / SUPPORT_DIR_NAME

    def hook_files(self, opts: Options) -> list[Path]:
        return [self.hooks_file(opts)]

    def files_plan(self, opts: Options) -> Plan:
        assets = _assets.plugin_root()
        base = self.base(opts)
        support = base / "hooks" / SUPPORT_DIR_NAME
        hooks = hooks_from(assets, "variants/copilot/hooks.json", support, opts)
        payload = (json.dumps(hooks, indent=2) + "\n").encode("utf-8")
        return Plan(
            agent=self.name, mode="files",
            targets=skill_targets(assets, base / "skills") + support_targets(assets, support)
            + [FileTarget(self.hooks_file(opts), payload)],
            notes=self.post_notes(opts, "files"),
            stops=[base, opts.project, Path.home()],
        )

    def plugin_plan(self, opts: Options) -> Plan:
        if opts.scope == "project":
            files = [opts.project / ".claude" / "settings.json", opts.project / ".github" / "copilot" / "settings.json"]
        else:
            files = [copilot_home() / "settings.json"]
        ops = [op for f in files for op in marketplace_ops(f, opts)]
        return Plan(agent=self.name, mode="plugin", ops=ops, notes=self.post_notes(opts, "plugin"),
                    stops=[opts.project / ".github", opts.project / ".claude", copilot_home(), opts.project,
                           Path.home()])

    def post_notes(self, opts: Options, mode: str) -> list[str]:
        if mode == "files":
            if opts.scope == "project":
                return ["Copilot CLI runs repository hooks (.github/hooks) only in trusted folders: trust this folder "
                        "when Copilot asks, or add it to trustedFolders in ~/.copilot/config.json."]
            return ["Copilot CLI loads the rf-harness skill and hooks at the next start."]
        where = ".claude/settings.json and .github/copilot/settings.json" if opts.scope == "project" else \
            str(copilot_home() / "settings.json")
        return [f"{where}: marketplace {MARKETPLACE_NAME} registered and {PLUGIN_ID} enabled; Copilot CLI loads the "
                "plugin in a trusted folder.",
                "Copilot CLI passes only decision/reason hook output to the model (no additionalContext); see the "
                "agent matrix in the docs."]

    def probe_payload(self, project: Path) -> tuple[str, dict[str, Any]]:
        return "userPromptSubmitted", {"cwd": str(project), "prompt": "rf-harness doctor probe",
                                       "sessionId": "rf-harness-doctor", "timestamp": 1767225600000}
