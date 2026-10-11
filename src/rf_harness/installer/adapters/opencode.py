"""OpenCode: no plugin marketplace, so always files mode: the skill, the JS hook plugin
(``plugins/rf-harness.js``, port of the prototype plugin incl. the Stop/noReply workaround) and the launcher it
calls, under ``.opencode/`` (project) or ``~/.config/opencode/`` (user).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .. import _assets
from ..homes import opencode_home
from ._base import SUPPORT_DIR_NAME, Adapter, FileTarget, Options, Plan, skill_targets, support_targets

LAUNCH_ARGS_TOKEN = "[/*rf-harness:launch-args*/]"


class OpenCodeAdapter(Adapter):
    name = "opencode"
    pretty = "OpenCode"
    cli = "opencode"
    supports_plugin = False

    def config_roots(self) -> list[Path]:
        return [opencode_home()]

    def root(self, opts: Options) -> Path:
        if opts.scope == "project":
            return opts.project / ".opencode"
        return opencode_home()

    def plugin_file(self, opts: Options) -> Path:
        return self.root(opts) / "plugins" / "rf-harness.js"

    def support_dir(self, opts: Options) -> Path | None:
        return self.root(opts) / SUPPORT_DIR_NAME

    def hook_files(self, opts: Options) -> list[Path]:
        return [self.plugin_file(opts)]

    def files_plan(self, opts: Options) -> Plan:
        assets = _assets.plugin_root()
        root = self.root(opts)
        js = (assets / "variants" / "opencode" / "plugins" / "rf-harness.js").read_text(encoding="utf-8")
        if opts.launcher_args:
            js = js.replace(LAUNCH_ARGS_TOKEN, json.dumps(opts.launcher_args))
        return Plan(
            agent=self.name, mode="files",
            targets=skill_targets(assets, root / "skills") + support_targets(assets, root / SUPPORT_DIR_NAME)
            + [FileTarget(self.plugin_file(opts), js.encode("utf-8"))],
            notes=self.post_notes(opts, "files"),
            stops=[root, opts.project, Path.home()],
        )

    def post_notes(self, opts: Options, mode: str) -> list[str]:
        return ["OpenCode loads plugins/rf-harness.js and the rf-harness skill at the next start (needs python3 on "
                "PATH to run the launcher; set RF_HARNESS_LAUNCHER_PYTHON to use another interpreter)."]

    def probe_payload(self, project: Path) -> tuple[str, dict[str, Any]]:
        return "UserPromptSubmit", {"hook_event_name": "UserPromptSubmit", "cwd": str(project),
                                    "session_id": "rf-harness-doctor", "ts": 1767225600000}
