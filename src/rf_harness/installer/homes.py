"""User-level config locations of the supported agents, honouring each agent's own home override.

* Claude Code: ``CLAUDE_CONFIG_DIR`` (default ``~/.claude``); its global config is ``<dir>/.claude.json`` when the
  override is set, else ``~/.claude.json``.
* Codex: ``CODEX_HOME`` (default ``~/.codex``).
* Copilot CLI: ``COPILOT_HOME`` (default ``~/.copilot``).
* OpenCode: ``$XDG_CONFIG_HOME/opencode`` (default ``~/.config/opencode``); ``OPENCODE_CONFIG`` names an extra
  config file.
* VS Code (Copilot) reads Claude-format files from ``~/.claude`` and has no override.

Every lookup in the installer (adapters, detection, coexistence scan, doctor, uninstall) goes through here, so an
isolated agent home (e.g. an evaluation cell with ``COPILOT_HOME`` set) never reads or writes the real one.
"""

from __future__ import annotations

import os
from pathlib import Path


def _env_dir(var: str, default: Path) -> Path:
    value = os.environ.get(var)
    return Path(value).expanduser() if value else default


def claude_home() -> Path:
    return _env_dir("CLAUDE_CONFIG_DIR", Path.home() / ".claude")


def claude_global_config() -> Path:
    if os.environ.get("CLAUDE_CONFIG_DIR"):
        return claude_home() / ".claude.json"
    return Path.home() / ".claude.json"


def codex_home() -> Path:
    return _env_dir("CODEX_HOME", Path.home() / ".codex")


def copilot_home() -> Path:
    return _env_dir("COPILOT_HOME", Path.home() / ".copilot")


def opencode_home() -> Path:
    xdg = os.environ.get("XDG_CONFIG_HOME")
    return (Path(xdg).expanduser() if xdg else Path.home() / ".config") / "opencode"


def opencode_config_files() -> list[Path]:
    files = [opencode_home() / "opencode.json"]
    if os.environ.get("OPENCODE_CONFIG"):
        files.append(Path(os.environ["OPENCODE_CONFIG"]).expanduser())
    return files


def vscode_claude_home() -> Path:
    return Path.home() / ".claude"


def user_agents_skills() -> Path:
    """The cross-vendor user skills folder Codex reads (``~/.agents/skills``)."""
    return Path.home() / ".agents" / "skills"
