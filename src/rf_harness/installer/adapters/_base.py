"""Adapter protocol shared by the per-agent installers.

An adapter turns install options into a :class:`Plan` (files to write, config entries to merge, commands to run,
notes). Planning does no I/O on the targets, so ``--dry-run`` renders the plan and tests assert on it; the CLI's
executor applies plans and records them in the manifest.

Adapted from robotframework-agentskills' ``installer/src/rf_agentskills/adapters/_base.py`` (same author,
Apache-2.0).
"""

from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .. import _assets
from .. import transforms as _x

PLUGIN_NAME = "rf-harness"
MARKETPLACE_NAME = "robotframework-ai-engineering"
MARKETPLACE_REPO = "manykarim/robotframework-ai-engineering"
PLUGIN_ID = f"{PLUGIN_NAME}@{MARKETPLACE_NAME}"
SKILL_NAME = "rf-harness"
SUPPORT_DIR_NAME = "rf-harness"
#: Test / local-development hook: use a local checkout as the marketplace instead of GitHub.
MARKETPLACE_DIR_ENV = "RF_HARNESS_MARKETPLACE_DIR"


@dataclass(frozen=True)
class Options:
    scope: str = "project"                       # project | user
    project: Path = field(default_factory=Path.cwd)
    mode: str = "plugin"                         # plugin | files
    ref: str | None = None                       # plugin mode: pin the marketplace to a tag
    coexist_env: tuple[tuple[str, str], ...] = ()  # e.g. (("RFH_STATIC", "runtime-only"),)

    @property
    def launcher_args(self) -> list[str]:
        args: list[str] = []
        for key, value in self.coexist_env:
            args += ["--set", f"{key}={value}"]
        return args


@dataclass(frozen=True)
class FileTarget:
    dst: Path
    payload: bytes
    executable: bool = False


@dataclass(frozen=True)
class ConfigOp:
    """One config edit. ``kind``: json_keys | json_hooks | codex_trust (see manifest.ConfigEntry)."""

    kind: str
    path: Path
    description: str
    key_path: tuple[str, ...] = ()
    values: dict[str, Any] = field(default_factory=dict)
    marker: str = ""


@dataclass
class Plan:
    agent: str
    mode: str
    targets: list[FileTarget] = field(default_factory=list)
    ops: list[ConfigOp] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    commands: list[list[str]] = field(default_factory=list)   # plugin mode: run with --yes, printed otherwise
    stops: list[Path] = field(default_factory=list)          # never pruned when removing files


class Adapter:
    """Base class: detection, version, plan selection, shared target builders."""

    name = "?"
    pretty = "?"
    cli = ""
    supports_plugin = True

    # ---------------------------------------------------------------- detection
    def config_roots(self) -> list[Path]:
        """User config directories that indicate the agent (honouring its home override)."""
        return []

    def detect(self) -> bool:
        if self.cli and shutil.which(self.cli):
            return True
        return any(d.is_dir() for d in self.config_roots())

    def version(self, timeout: float = 8.0) -> str | None:
        exe = shutil.which(self.cli) if self.cli else None
        if not exe:
            return None
        try:
            proc = subprocess.run([exe, "--version"], capture_output=True, text=True, timeout=timeout,
                                  stdin=subprocess.DEVNULL)
        except (OSError, subprocess.SubprocessError):
            return None
        text = (proc.stdout or proc.stderr or "").strip().splitlines()
        return text[0].strip() if text else None

    # ---------------------------------------------------------------- planning
    def plan(self, opts: Options) -> Plan:
        if opts.mode == "plugin" and self.supports_plugin:
            return self.plugin_plan(opts)
        return self.files_plan(opts)

    def files_plan(self, opts: Options) -> Plan:  # pragma: no cover - abstract
        raise NotImplementedError

    def plugin_plan(self, opts: Options) -> Plan:
        return self.files_plan(opts)

    def support_dir(self, opts: Options) -> Path | None:
        """Where files mode installs the launcher (``<dir>/bin/rfh-launch``); None in plugin mode."""
        return None

    def hook_files(self, opts: Options) -> list[Path]:
        """Config files that carry rf-harness hooks in files mode (doctor / coexistence)."""
        return []

    def probe_payload(self, project: Path) -> tuple[str, dict[str, Any]]:
        """A synthetic UserPromptSubmit event in this agent's payload format."""
        return "UserPromptSubmit", {"hook_event_name": "UserPromptSubmit", "session_id": "rf-harness-doctor",
                                    "cwd": str(project), "prompt": "rf-harness doctor probe",
                                    "transcript_path": "", "permission_mode": "default"}

    def post_notes(self, opts: Options, mode: str) -> list[str]:
        return []


# -------------------------------------------------------------------- shared target builders
def skill_targets(assets: Path, skills_root: Path) -> list[FileTarget]:
    src = assets / "skills" / SKILL_NAME
    return [FileTarget(skills_root / SKILL_NAME / f.relative_to(src), f.read_bytes()) for f in _assets.iter_files(src)]


def support_targets(assets: Path, support_dir: Path) -> list[FileTarget]:
    """The launcher (bin/) plus the plugin manifest (version) under ``support_dir``."""
    targets = [FileTarget(support_dir / "bin" / f.name, f.read_bytes(), executable=f.name == "rfh-launch")
               for f in _assets.iter_files(assets / "bin")]
    manifest = assets / ".claude-plugin" / "plugin.json"
    targets.append(FileTarget(support_dir / ".claude-plugin" / "plugin.json", manifest.read_bytes()))
    return targets


def hooks_from(assets: Path, rel: str, support_dir: Path, opts: Options) -> dict[str, Any]:
    text = (assets / rel).read_text(encoding="utf-8")
    return _x.render_hooks_file(text, support_dir, opts.launcher_args)


def hook_marker(support_dir: Path) -> str:
    """Ownership marker of rf-harness hook groups: the installed launcher path."""
    return _x.native_path(support_dir / "bin" / "rfh-launch")


def marketplace_source(ref: str | None) -> dict[str, Any]:
    local = os.environ.get(MARKETPLACE_DIR_ENV)
    if local:
        return {"source": "directory", "path": _x.native_path(Path(local).expanduser().resolve())}
    source: dict[str, Any] = {"source": "github", "repo": MARKETPLACE_REPO}
    if ref:
        source["ref"] = ref
    return source


def marketplace_ops(settings: Path, opts: Options) -> list[ConfigOp]:
    """``extraKnownMarketplaces`` + ``enabledPlugins`` (Claude Code, Copilot CLI and VS Code read this shape)."""
    ops = [
        ConfigOp("json_keys", settings, f"register marketplace {MARKETPLACE_NAME}", ("extraKnownMarketplaces",),
                 {MARKETPLACE_NAME: {"source": marketplace_source(opts.ref)}}),
        ConfigOp("json_keys", settings, f"enable plugin {PLUGIN_ID}", ("enabledPlugins",), {PLUGIN_ID: True}),
    ]
    return ops


def plugin_env_op(settings: Path, opts: Options) -> list[ConfigOp]:
    """Settings ``env`` for the coexistence switches in plugin mode (the plugin's hook commands are fixed)."""
    if not opts.coexist_env:
        return []
    return [ConfigOp("json_keys", settings, "set " + ", ".join(f"{k}={v}" for k, v in opts.coexist_env), ("env",),
                     dict(opts.coexist_env))]
