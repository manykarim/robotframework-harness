"""Manifest of everything ``rf-harness install`` wrote, for idempotent re-install, upgrade and safe uninstall.

Location: ``<project>/.rf-harness/manifest.json`` (project scope) or ``~/.rf-harness/manifest.json`` (user scope).

* Each written file is recorded with its sha256. Uninstall and upgrade remove a file only while its hash still
  matches; files the user modified are kept and reported.
* Each config entry (a JSON key, the rf-harness hook groups of a settings file, a Codex trust table) is recorded
  with a sha256 of the value written, so a value the user changed afterwards is kept too.
* Files and entries recorded by several installations (Claude Code and VS Code share ``.claude/``) are removed only
  with the last of them.

Adapted from robotframework-agentskills' ``installer/src/rf_agentskills/manifest.py`` (same author, Apache-2.0).
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from .transforms import sha256_file

MANIFEST_VERSION = 1
MANIFEST_DIR = ".rf-harness"
MANIFEST_NAME = "manifest.json"


def manifest_path(scope: str, project: Path) -> Path:
    base = project if scope == "project" else Path.home()
    return base / MANIFEST_DIR / MANIFEST_NAME


@dataclass
class FileEntry:
    path: str
    sha256: str
    category: str = "other"


@dataclass
class ConfigEntry:
    """A config entry rf-harness owns.

    kind ``json_keys``: keys under ``key_path`` of a JSON file; ``values`` maps key -> sha256 of the value written.
    kind ``json_hooks``: the hook groups whose commands contain ``marker`` in the ``key_path[0]`` block;
    ``values`` maps event -> sha256 of rf-harness' groups.
    kind ``codex_trust``: ``[hooks.state."<key>"]`` tables of a Codex config.toml; ``values`` maps key -> hash.
    kind ``text_line``: lines of a text file (``.gitignore``); ``values`` maps line -> "".
    """

    path: str
    kind: str
    key_path: list[str] = field(default_factory=list)
    values: dict[str, str] = field(default_factory=dict)
    marker: str = ""

    def ident(self) -> tuple[str, str, tuple[str, ...]]:
        return (self.path, self.kind, tuple(self.key_path))


@dataclass
class Installation:
    agent: str
    scope: str
    mode: str
    installed_at: str
    bundle_version: str
    files: list[FileEntry] = field(default_factory=list)
    entries: list[ConfigEntry] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def file_paths(self) -> set[str]:
        return {f.path for f in self.files}


@dataclass
class Manifest:
    path: Path
    installations: list[Installation] = field(default_factory=list)
    project: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def load(cls, path: Path) -> Manifest:
        manifest = cls(path=path)
        if not path.is_file():
            return manifest
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return manifest
        if not isinstance(data, dict) or data.get("version") != MANIFEST_VERSION:
            return manifest
        for raw in data.get("installations", []):
            manifest.installations.append(Installation(
                agent=raw["agent"], scope=raw.get("scope", "project"), mode=raw.get("mode", "files"),
                installed_at=raw.get("installed_at", ""), bundle_version=raw.get("bundle_version", "unknown"),
                files=[FileEntry(**f) for f in raw.get("files", [])],
                entries=[ConfigEntry(**e) for e in raw.get("entries", [])],
                notes=list(raw.get("notes", [])),
            ))
        project = data.get("project")
        manifest.project = project if isinstance(project, dict) else {}
        return manifest

    def to_text(self) -> str:
        payload = {
            "version": MANIFEST_VERSION,
            "written_by": "rf-harness",
            "installations": [asdict(i) for i in sorted(self.installations, key=lambda i: (i.agent, i.scope))],
            "project": self.project,
        }
        return json.dumps(payload, indent=2, sort_keys=False) + "\n"

    def save(self) -> None:
        if not self.installations and not self.project:
            if self.path.is_file():
                self.path.unlink()
            try:
                self.path.parent.rmdir()
            except OSError:
                pass
            return
        text = self.to_text()
        if self.path.is_file() and self.path.read_text(encoding="utf-8") == text:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_name(self.path.name + ".tmp")
        tmp.write_text(text, encoding="utf-8")
        os.replace(tmp, self.path)

    def find(self, agent: str, scope: str) -> Installation | None:
        for ins in self.installations:
            if ins.agent == agent and ins.scope == scope:
                return ins
        return None

    def upsert(self, installation: Installation) -> None:
        self.installations = [i for i in self.installations
                              if not (i.agent == installation.agent and i.scope == installation.scope)]
        self.installations.append(installation)

    def remove(self, agent: str, scope: str) -> Installation | None:
        found = self.find(agent, scope)
        if found is not None:
            self.installations.remove(found)
        return found

    def others(self, agent: str, scope: str) -> list[Installation]:
        return [i for i in self.installations if not (i.agent == agent and i.scope == scope)]

    def file_shared(self, path: str, agent: str, scope: str) -> bool:
        return any(path in i.file_paths() for i in self.others(agent, scope))

    def entry_shared(self, entry: ConfigEntry, key: str, agent: str, scope: str) -> bool:
        for other in self.others(agent, scope):
            for e in other.entries:
                if e.ident() == entry.ident() and key in e.values:
                    return True
        return False


def now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def category_for(path: Path) -> str:
    parts = path.parts
    if "skills" in parts:
        return "skill"
    if "bin" in parts or ".claude-plugin" in parts:
        return "launcher"
    if path.suffix == ".js" or "hooks" in parts:
        return "hooks"
    return "other"


def file_entry(path: Path, sha256: str | None = None) -> FileEntry:
    return FileEntry(path=str(path), sha256=sha256 or sha256_file(path), category=category_for(path))


def is_modified(entry: FileEntry) -> bool:
    path = Path(entry.path)
    return path.is_file() and sha256_file(path) != entry.sha256


def prune_empty_parents(path: Path, stops: set[Path]) -> None:
    """Remove empty parent directories of ``path`` up to (excluding) the first stop directory or non-empty dir."""
    stop_set = {s.resolve() for s in stops}
    parent = path.parent
    for _ in range(32):
        try:
            resolved = parent.resolve()
        except OSError:
            return
        if resolved in stop_set or resolved == resolved.parent:
            return
        try:
            parent.rmdir()
        except OSError:
            return
        parent = parent.parent
