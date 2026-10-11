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


def copilot_trusted_folders() -> list[str] | None:
    """`trusted_folders` from $COPILOT_HOME/config.json (Copilot CLI runs repository hooks only in these folders).
    None when the file is missing or unreadable. The file may contain // comments, so a regex fallback is used."""
    import json
    import re

    cfg = copilot_home() / "config.json"
    try:
        text = cfg.read_text(encoding="utf-8")
    except OSError:
        return None
    try:
        data = json.loads(text)
        folders = data.get("trusted_folders") if isinstance(data, dict) else None
        return [str(f) for f in folders] if isinstance(folders, list) else []
    except ValueError:
        m = re.search(r'"trusted_folders"\s*:\s*\[(.*?)\]', text, re.S)
        return re.findall(r'"((?:[^"\\]|\\.)*)"', m.group(1)) if m else []


def copilot_folder_trusted(project: Path) -> bool | None:
    """True when `project` or one of its parents is a Copilot trusted folder; None when Copilot's config is absent."""
    folders = copilot_trusted_folders()
    if folders is None:
        return None
    try:
        resolved = Path(project).resolve()
    except OSError:
        resolved = Path(project)
    for f in folders:
        try:
            root = Path(f).expanduser().resolve()
        except OSError:
            continue
        if resolved == root or root in resolved.parents:
            return True
    return False

