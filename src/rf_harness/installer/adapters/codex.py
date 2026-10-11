"""OpenAI Codex: plugin mode prints (or with ``--yes`` runs) ``codex plugin marketplace add`` + ``codex plugin add``;
files mode installs the skill under ``.agents/skills`` and Claude-format hooks in ``.codex/hooks.json``
(``$CODEX_HOME/hooks.json`` for the user). Both then trust exactly the rf-harness hooks (``codex_trust``), or print
the one-time ``/hooks`` step when that is impossible.

Adapted from robotframework-agentskills' ``adapters/codex.py`` (same author, Apache-2.0).
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from .. import _assets
from .. import transforms as _x
from ..codex_trust import HOOKS_STEP
from ..homes import codex_home, user_agents_skills
from ._base import (
    MARKETPLACE_DIR_ENV,
    MARKETPLACE_REPO,
    PLUGIN_ID,
    SUPPORT_DIR_NAME,
    Adapter,
    ConfigOp,
    Options,
    Plan,
    hook_marker,
    hooks_from,
    skill_targets,
    support_targets,
)


class CodexAdapter(Adapter):
    name = "codex"
    pretty = "OpenAI Codex"
    cli = "codex"

    def config_roots(self) -> list[Path]:
        return [codex_home()]

    def config_dir(self, opts: Options) -> Path:
        return opts.project / ".codex" if opts.scope == "project" else codex_home()

    def skills_root(self, opts: Options) -> Path:
        return opts.project / ".agents" / "skills" if opts.scope == "project" else user_agents_skills()

    def hooks_file(self, opts: Options) -> Path:
        return self.config_dir(opts) / "hooks.json"

    def support_dir(self, opts: Options) -> Path | None:
        return self.config_dir(opts) / SUPPORT_DIR_NAME

    def hook_files(self, opts: Options) -> list[Path]:
        return [self.hooks_file(opts)]

    def trust_op(self, opts: Options, marker: str = "", plugin_id: str = "") -> ConfigOp:
        return ConfigOp("codex_trust", codex_home() / "config.toml", "trust the rf-harness hooks in Codex",
                        values={"project": str(opts.project), "scope": opts.scope, "plugin_id": plugin_id},
                        marker=marker)

    def files_plan(self, opts: Options) -> Plan:
        assets = _assets.plugin_root()
        support = self.config_dir(opts) / SUPPORT_DIR_NAME
        hooks = hooks_from(assets, "variants/codex/hooks.json", support, opts)["hooks"]
        marker = hook_marker(support)
        hooks_file = self.hooks_file(opts)
        return Plan(
            agent=self.name, mode="files",
            targets=skill_targets(assets, self.skills_root(opts)) + support_targets(assets, support),
            ops=[ConfigOp("json_hooks", hooks_file, f"merge rf-harness hooks into {hooks_file}", ("hooks",), hooks,
                          marker),
                 self.trust_op(opts, marker=marker)],
            notes=self.post_notes(opts, "files"),
            stops=[self.config_dir(opts), self.skills_root(opts).parent, opts.project, Path.home()],
        )

    def plugin_commands(self, opts: Options) -> list[list[str]]:
        local = os.environ.get(MARKETPLACE_DIR_ENV)
        add = ["codex", "plugin", "marketplace", "add", _x.native_path(Path(local).resolve()) if local else
               MARKETPLACE_REPO]
        if opts.ref and not local:
            add += ["--ref", opts.ref]
        return [add, ["codex", "plugin", "add", PLUGIN_ID]]

    def plugin_plan(self, opts: Options) -> Plan:
        return Plan(agent=self.name, mode="plugin", ops=[self.trust_op(opts, plugin_id=PLUGIN_ID)],
                    commands=self.plugin_commands(opts), notes=self.post_notes(opts, "plugin"),
                    stops=[codex_home(), opts.project, Path.home()])

    def post_notes(self, opts: Options, mode: str) -> list[str]:
        notes: list[str] = []
        if mode == "plugin":
            commands = "\n".join("    " + " ".join(c) for c in self.plugin_commands(opts))
            notes.append("Codex installs plugins per user (no committed project settings): every user runs once "
                         "(rf-harness runs them with --yes):\n" + commands)
        elif opts.scope == "project":
            notes.append(f"Codex loads {self.config_dir(opts)} only in trusted projects: accept the trust prompt the "
                         "first time you start codex there.")
        notes.append(f"If Codex reports untrusted hooks: {HOOKS_STEP}.")
        return notes

    def probe_payload(self, project: Path) -> tuple[str, dict[str, Any]]:
        return "UserPromptSubmit", {"hook_event_name": "UserPromptSubmit", "session_id": "rf-harness-doctor",
                                    "turn_id": "rf-harness-doctor", "cwd": str(project), "model": "gpt-5",
                                    "prompt": "rf-harness doctor probe", "transcript_path": None,
                                    "permission_mode": "default"}
