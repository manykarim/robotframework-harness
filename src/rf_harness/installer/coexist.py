"""Detect other Robot Framework agent tooling next to rf-harness (design D7, task 4.4).

* rf-agentskills: its hooks (``rf-agentskills-files`` / ``validate_robot.mjs`` commands, the enabled plugin, the
  OpenCode plugin). Reported, never modified; with ``--coexist keep`` rf-harness sets ``RFH_STATIC=runtime-only``
  so only rf-agentskills reports static errors.
* rf-mcp: MCP server entries (``rf-mcp`` / ``robotmcp``). Reported only (both routes work; agents may mix them).
* research prototypes (``rfharness``, ``rfharness2/3/31/32``): hook groups, Codex config blocks, OpenCode plugins,
  Copilot plugin dirs, pointer blocks in CLAUDE.md / AGENTS.md. Reported, and removable (they are superseded).
"""

from __future__ import annotations

import json
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from . import transforms as _x
from .homes import claude_global_config, claude_home, codex_home, copilot_home, opencode_config_files, opencode_home

PROTOTYPE = re.compile(r"rfharness(?:2|3|31|32)?(?![\w-])|rfharness\d+")
AGENTSKILLS = re.compile(r"rf-agentskills|validate_robot\.mjs")
RF_MCP = re.compile(r"rf-mcp|robotmcp|robotframework-mcp", re.I)


@dataclass
class Finding:
    tool: str              # rf-agentskills | rf-mcp | prototype
    path: Path
    detail: str
    kind: str = "report"   # report | hooks | toml_block | file | dir | md_block
    data: dict[str, Any] = field(default_factory=dict)

    def describe(self) -> str:
        return f"{self.tool}: {self.detail} ({self.path})"


@dataclass
class Coexistence:
    findings: list[Finding] = field(default_factory=list)

    def of(self, tool: str) -> list[Finding]:
        return [f for f in self.findings if f.tool == tool]

    @property
    def agentskills(self) -> bool:
        return bool(self.of("rf-agentskills"))


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _json(path: Path) -> dict[str, Any]:
    try:
        data, _ = _x.load_json_object(path)
        return data
    except (OSError, ValueError):
        return {}


def _commands(groups: Any) -> list[str]:
    out: list[str] = []
    for group in groups if isinstance(groups, list) else []:
        if not isinstance(group, dict):
            continue
        inner = group.get("hooks")
        hooks: list[Any] = inner if isinstance(inner, list) else [group]
        for hook in hooks:
            if isinstance(hook, dict):
                out += [str(hook.get(k)) for k in ("command", "bash", "powershell") if hook.get(k)]
    return out


def _scan_settings(path: Path, findings: list[Finding]) -> None:
    data = _json(path)
    hooks = _dict(data.get("hooks"))
    agentskills_events = sorted(ev for ev, g in hooks.items() if any(AGENTSKILLS.search(c) for c in _commands(g)))
    if agentskills_events:
        findings.append(Finding("rf-agentskills", path, "hooks on " + ", ".join(agentskills_events)))
    proto_events = sorted(ev for ev, g in hooks.items() if any(PROTOTYPE.search(c) for c in _commands(g)))
    if proto_events:
        markers = sorted({m.group(0) for g in hooks.values() for c in _commands(g) for m in PROTOTYPE.finditer(c)})
        findings.append(Finding("prototype", path, f"{'/'.join(markers)} hooks on " + ", ".join(proto_events),
                                kind="hooks", data={"markers": markers}))
    enabled = _dict(data.get("enabledPlugins"))
    for plugin_id, on in enabled.items():
        if on and plugin_id.startswith("rf-agentskills@"):
            findings.append(Finding("rf-agentskills", path, f"plugin {plugin_id} enabled"))
    _scan_servers(path, _dict(data.get("mcpServers")), findings)


def _scan_servers(path: Path, servers: Any, findings: list[Finding]) -> None:
    if not isinstance(servers, dict):
        return
    for name, spec in servers.items():
        if RF_MCP.search(name) or RF_MCP.search(json.dumps(spec)):
            findings.append(Finding("rf-mcp", path, f"MCP server '{name}'"))


def _scan_text_markers(path: Path, findings: list[Finding], kind: str) -> None:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return
    if kind == "toml_block":
        markers = sorted(set(re.findall(r"#\s*(rfharness\d*):begin", text)))
        if markers:
            findings.append(Finding("prototype", path, f"{'/'.join(markers)} hook block", kind="toml_block",
                                    data={"markers": markers}))
        if AGENTSKILLS.search(text):
            findings.append(Finding("rf-agentskills", path, "hooks"))
        for name in re.findall(r"^\s*\[mcp_servers\.\"?([^\]\"]+)\"?\]", text, re.M):
            if RF_MCP.search(name) or RF_MCP.search(text):
                findings.append(Finding("rf-mcp", path, f"MCP server '{name}'"))
                break
    elif kind == "md_block":
        markers = sorted(set(re.findall(r"<!--\s*(rfharness\d*):begin\s*-->", text)))
        if markers:
            findings.append(Finding("prototype", path, f"{'/'.join(markers)} pointer block", kind="md_block",
                                    data={"markers": markers}))


def scan(project: Path) -> Coexistence:
    """Scan the project and the user's agent configuration (read only)."""
    findings: list[Finding] = []
    for settings in (project / ".claude" / "settings.json", project / ".claude" / "settings.local.json",
                     claude_home() / "settings.json", project / ".github" / "copilot" / "settings.json",
                     copilot_home() / "settings.json", project / ".codex" / "hooks.json",
                     codex_home() / "hooks.json"):
        if settings.is_file():
            _scan_settings(settings, findings)
    for hooks_dir in (project / ".github" / "hooks", copilot_home() / "hooks"):
        for path in sorted(hooks_dir.glob("*.json")) if hooks_dir.is_dir() else []:
            _scan_settings(path, findings)
    for mcp in (project / ".mcp.json", claude_global_config(), copilot_home() / "mcp-config.json"):
        data = _json(mcp)
        _scan_servers(mcp, data.get("mcpServers"), findings)
        for proj in _dict(data.get("projects")).values():
            _scan_servers(mcp, _dict(proj).get("mcpServers"), findings)
    vscode_mcp = project / ".vscode" / "mcp.json"
    _scan_servers(vscode_mcp, _json(vscode_mcp).get("servers"), findings)
    for oc in (project / "opencode.json", *opencode_config_files()):
        _scan_servers(oc, _json(oc).get("mcp"), findings)
    for toml in (project / ".codex" / "config.toml", codex_home() / "config.toml"):
        if toml.is_file():
            _scan_text_markers(toml, findings, "toml_block")
    for md in (project / "CLAUDE.md", project / "AGENTS.md"):
        if md.is_file():
            _scan_text_markers(md, findings, "md_block")
    for plugins in (project / ".opencode" / "plugins", opencode_home() / "plugins"):
        for js in sorted(plugins.glob("*.js")) if plugins.is_dir() else []:
            if PROTOTYPE.search(js.name):
                findings.append(Finding("prototype", js, "OpenCode plugin", kind="file"))
            elif js.name.startswith("rf-agentskills"):
                findings.append(Finding("rf-agentskills", js, "OpenCode plugin"))
    copilot = copilot_home()
    for plugin_dir in sorted(copilot.glob("rfharness*-plugin")) if copilot.is_dir() else []:
        findings.append(Finding("prototype", plugin_dir, "Copilot plugin directory", kind="dir"))
    unique: dict[tuple[str, str, str], Finding] = {}
    for f in findings:
        unique.setdefault((f.tool, str(f.path), f.detail), f)
    return Coexistence(list(unique.values()))


def remove_prototype(finding: Finding) -> bool:
    """Remove one research-prototype install item; never touches anything else in the file."""
    path = finding.path
    if finding.tool != "prototype" or not path.exists():
        return False
    if finding.kind == "hooks":
        data, indent = _x.load_json_object(path)
        hooks = _dict(data.get("hooks"))
        changed = False
        for event in list(hooks):
            groups = hooks[event] if isinstance(hooks[event], list) else []
            kept = [g for g in groups if not any(PROTOTYPE.search(c) for c in _commands([g]))]
            if len(kept) != len(groups):
                changed = True
                if kept:
                    hooks[event] = kept
                else:
                    del hooks[event]
        if changed:
            if not hooks:
                data.pop("hooks", None)
            _x.write_text_if_changed(path, _x.dump_json(data, indent))
        return changed
    if finding.kind in ("toml_block", "md_block"):
        text = path.read_text(encoding="utf-8")
        total = 0
        for marker in finding.data.get("markers", []):
            if finding.kind == "toml_block":
                begin, end = r"#\s*" + re.escape(marker) + r":begin", r"#\s*" + re.escape(marker) + r":end"
            else:
                begin, end = r"<!--\s*" + re.escape(marker) + r":begin\s*-->", r"<!--\s*" + re.escape(marker) + \
                    r":end\s*-->"
            text, count = _x.remove_marked_blocks(text, begin, end)
            total += count
        if total:
            _x.write_text_if_changed(path, text if text.strip() else "")
        return bool(total)
    if finding.kind == "file":
        path.unlink()
        return True
    if finding.kind == "dir":
        shutil.rmtree(path)
        return True
    return False
