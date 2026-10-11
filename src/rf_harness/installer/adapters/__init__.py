"""Per-agent adapters for the v1 agents: Claude Code, Codex, GitHub Copilot CLI, VS Code (Copilot) and OpenCode.

Cursor, Goose and Gemini CLI are out of v1 until they are verified live (design, Resolved Decisions).
"""

from __future__ import annotations

from ._base import Adapter, ConfigOp, FileTarget, Options, Plan
from .claude_code import ClaudeCodeAdapter
from .codex import CodexAdapter
from .copilot_cli import CopilotCliAdapter
from .opencode import OpenCodeAdapter
from .vscode import VSCodeAdapter

ALL_ADAPTERS: tuple[type[Adapter], ...] = (
    ClaudeCodeAdapter,
    CodexAdapter,
    CopilotCliAdapter,
    VSCodeAdapter,
    OpenCodeAdapter,
)
ALIASES = {"claude": "claude-code", "copilot": "copilot-cli", "code": "vscode", "vs-code": "vscode"}


def all_names() -> tuple[str, ...]:
    return tuple(cls.name for cls in ALL_ADAPTERS)


def by_name(name: str) -> Adapter | None:
    name = ALIASES.get(name, name)
    for cls in ALL_ADAPTERS:
        if cls.name == name:
            return cls()
    return None


__all__ = ["ALL_ADAPTERS", "Adapter", "ConfigOp", "FileTarget", "Options", "Plan", "all_names", "by_name"]
