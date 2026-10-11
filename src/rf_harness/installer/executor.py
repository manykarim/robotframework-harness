"""Apply, render and revert adapter plans with manifest bookkeeping (tasks 4.2, 4.5).

* install: write targets (skipping unchanged ones), merge config entries, provision Codex trust, remove files and
  entries the previous install recorded but the new plan no longer ships (unless the user modified them), record it.
* re-install with nothing new: no file, entry or manifest byte changes.
* uninstall: remove only recorded items whose content still matches; keep and list modified ones; keep items another
  installation in the same manifest still records.

Adapted from robotframework-agentskills' ``cli.py`` plan execution (same author, Apache-2.0).
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .. import __version__
from . import codex_trust
from . import manifest as _m
from . import transforms as _x
from .adapters import Adapter, ConfigOp, Plan

TRUST_FAILED = "codex hook trust not provisioned"


@dataclass
class Outcome:
    agent: str
    written: list[str] = field(default_factory=list)
    unchanged: int = 0
    merged: list[str] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)
    kept: list[str] = field(default_factory=list)       # user-modified items left in place
    skipped: list[str] = field(default_factory=list)    # foreign files not overwritten
    warnings: list[str] = field(default_factory=list)
    failed: bool = False

    @property
    def changed(self) -> bool:
        return bool(self.written or self.merged or self.removed)


# ------------------------------------------------------------------------------------------------ helpers
def _write_target(dst: Path, payload: bytes, executable: bool) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    tmp = dst.with_name(dst.name + ".rfh.tmp")
    tmp.write_bytes(payload)
    os.replace(tmp, dst)
    if executable and os.name != "nt":
        os.chmod(dst, 0o755)


def _stops(plan_stops: list[Path]) -> set[Path]:
    return {Path(s) for s in plan_stops} | {Path.home()}


def _entry_for_keys(op: ConfigOp, owned: list[str]) -> _m.ConfigEntry:
    values = {k: _x.json_digest(_x.get_json_value(op.path, list(op.key_path), k)) for k in owned}
    return _m.ConfigEntry(str(op.path), "json_keys", list(op.key_path), values)


def _entry_for_hooks(op: ConfigOp) -> _m.ConfigEntry:
    groups = _x.owned_hook_groups(op.path, op.marker, op.key_path[0] if op.key_path else "hooks")
    values = {event: _x.json_digest(groups.get(event, [])) for event in op.values}
    return _m.ConfigEntry(str(op.path), "json_hooks", list(op.key_path), values, op.marker)


def _previous_entry(previous: _m.Installation | None, ident: tuple[str, str, tuple[str, ...]]) -> _m.ConfigEntry | None:
    for entry in previous.entries if previous else []:
        if entry.ident() == ident:
            return entry
    return None


# ------------------------------------------------------------------------------------------------ install
def apply_plan(adapter: Adapter, plan: Plan, scope: str, manifest: _m.Manifest,
               trust_runner: Any = codex_trust.provision) -> Outcome:
    out = Outcome(adapter.name)
    previous = manifest.find(adapter.name, scope)
    prev_files = {f.path: f for f in previous.files} if previous else {}
    files: list[_m.FileEntry] = []

    for target in plan.targets:
        dst = target.dst
        key = str(dst)
        new_hash = _x.sha256_bytes(target.payload)
        if dst.is_file():
            current = _x.sha256_file(dst)
            if current == new_hash:
                out.unchanged += 1
                files.append(_m.file_entry(dst, new_hash))
                if target.executable and os.name != "nt" and not os.access(dst, os.X_OK):
                    os.chmod(dst, 0o755)
                continue
            owner = prev_files.get(key)
            shared = [i for i in manifest.others(adapter.name, scope) if key in i.file_paths()]
            recorded = owner or next((f for i in shared for f in i.files if f.path == key), None)
            if recorded is None:
                out.skipped.append(key)
                out.failed = True
                continue
            if current != recorded.sha256:
                out.kept.append(key)
                files.append(_m.FileEntry(key, recorded.sha256, recorded.category))
                continue
        _write_target(dst, target.payload, target.executable)
        out.written.append(key)
        files.append(_m.file_entry(dst, new_hash))

    entries: list[_m.ConfigEntry] = []
    for op in plan.ops:
        ident = (str(op.path), op.kind, tuple(op.key_path))
        prev_entry = _previous_entry(previous, ident)
        try:
            if op.kind == "json_keys":
                added, changed = _x.merge_json_keys(op.path, list(op.key_path), op.values)
                # ours: keys added now, keys recorded before, keys another installation shares (Claude Code + VS Code)
                shared_keys = {k for other in manifest.others(adapter.name, scope) for e in other.entries
                               if e.ident() == ident for k in e.values}
                previous_keys = set(prev_entry.values) if prev_entry else set()
                owned = sorted(set(added) | ((previous_keys | shared_keys) & set(op.values)))
                if changed:
                    out.merged.append(op.description)
                if owned:
                    entries.append(_entry_for_keys(op, owned))
            elif op.kind == "json_hooks":
                if _x.merge_hook_groups(op.path, op.values, op.marker, op.key_path[0] if op.key_path else "hooks"):
                    out.merged.append(op.description)
                entries.append(_entry_for_hooks(op))
            elif op.kind == "codex_trust":
                trust_entry = _apply_trust(op, prev_entry, out, trust_runner)
                if trust_entry is not None:
                    entries.append(trust_entry)
        except (OSError, ValueError) as exc:
            out.warnings.append(f"{op.path}: {exc}")
            out.failed = True

    # Upgrade: what the previous install wrote and this plan no longer ships.
    new_paths = {f.path for f in files}
    for key, file_rec in prev_files.items():
        if key in new_paths:
            continue
        path = Path(key)
        if not path.is_file() or manifest.file_shared(key, adapter.name, scope):
            continue
        if _m.is_modified(file_rec):
            out.kept.append(key)
            continue
        path.unlink()
        _m.prune_empty_parents(path, _stops(plan.stops))
        out.removed.append(key)
    redone = {e.ident() for e in entries}
    for old in previous.entries if previous else []:
        if old.ident() not in redone:
            removed, kept = revert_entry(old, manifest, adapter.name, scope)
            out.removed += removed
            out.kept += kept

    record = _m.Installation(adapter.name, scope, plan.mode, _m.now_iso(), __version__, files, entries, plan.notes)
    if previous is not None and not out.changed and _same_record(previous, record):
        return out
    manifest.upsert(record)
    return out


def _same_record(old: _m.Installation, new: _m.Installation) -> bool:
    return (old.mode, old.bundle_version, [vars(f) for f in old.files], [vars(e) for e in old.entries], old.notes) == \
        (new.mode, new.bundle_version, [vars(f) for f in new.files], [vars(e) for e in new.entries], new.notes)


def _apply_trust(op: ConfigOp, prev_entry: _m.ConfigEntry | None, out: Outcome,
                 trust_runner: Any) -> _m.ConfigEntry | None:
    values = op.values
    result = trust_runner(Path(values["project"]), values["scope"], marker=op.marker,
                          plugin_id=values.get("plugin_id", ""))
    if not result.ok:
        out.warnings.append(f"{TRUST_FAILED}: {result.message}; {codex_trust.HOOKS_STEP}")
        return prev_entry
    stale = [k for k in (prev_entry.values if prev_entry else {}) if k not in result.entries]
    if stale:
        _x.remove_codex_trust(op.path, stale)
    before = dict(prev_entry.values) if prev_entry else {}
    if before != result.entries:
        out.merged.append(op.description)
    if not result.project_trusted:
        out.warnings.append("Codex has not trusted this project yet; the rf-harness hooks are pre-trusted and run "
                            "once you accept Codex's trust prompt for the folder")
    return _m.ConfigEntry(str(op.path), "codex_trust", [], dict(sorted(result.entries.items())))


# ------------------------------------------------------------------------------------------------ revert / uninstall
def revert_entry(entry: _m.ConfigEntry, manifest: _m.Manifest, agent: str, scope: str) -> tuple[list[str], list[str]]:
    """Remove one recorded config entry where it still matches; return (removed, kept-as-modified) descriptions."""
    path = Path(entry.path)
    removed: list[str] = []
    kept: list[str] = []
    if not path.is_file():
        return removed, kept
    try:
        if entry.kind == "json_keys":
            drop = []
            for key, digest in entry.values.items():
                if manifest.entry_shared(entry, key, agent, scope):
                    continue
                current = _x.get_json_value(path, entry.key_path, key)
                if current is None:
                    continue
                if _x.json_digest(current) == digest:
                    drop.append(key)
                else:
                    kept.append(f"{path} [{'.'.join(entry.key_path + [key])}]")
            if drop and _x.remove_json_keys(path, entry.key_path, drop):
                removed.append(f"{path} [{', '.join('.'.join(entry.key_path + [k]) for k in drop)}]")
        elif entry.kind == "json_hooks":
            if any(manifest.entry_shared(entry, ev, agent, scope) for ev in entry.values):
                return removed, kept
            top = entry.key_path[0] if entry.key_path else "hooks"
            groups = _x.owned_hook_groups(path, entry.marker, top)
            modified = [ev for ev, digest in entry.values.items() if ev in groups and
                        _x.json_digest(groups[ev]) != digest]
            if modified:
                kept.append(f"{path} [hooks: {', '.join(modified)} modified]")
            drop = [ev for ev in entry.values if ev not in modified]
            if drop and _x.remove_hook_groups(path, entry.marker, drop, top):
                removed.append(f"{path} [rf-harness hooks]")
        elif entry.kind == "codex_trust":
            stored = _x.read_codex_trust(path)
            drop = [k for k, v in entry.values.items() if stored.get(k) == v]
            kept += [f"{path} [hooks.state {k}]" for k, v in entry.values.items() if k in stored and stored[k] != v]
            if drop and _x.remove_codex_trust(path, drop):
                removed.append(f"{path} [{len(drop)} hook trust entries]")
        elif entry.kind == "text_line":
            for line in entry.values:
                if _x.remove_line(path, line):
                    removed.append(f"{path} [{line}]")
    except (OSError, ValueError) as exc:
        kept.append(f"{path} ({exc})")
    return removed, kept


def uninstall(installation: _m.Installation, manifest: _m.Manifest, stops: set[Path], dry_run: bool = False) -> Outcome:
    out = Outcome(installation.agent)
    for entry in installation.files:
        path = Path(entry.path)
        if not path.is_file():
            continue
        if manifest.file_shared(entry.path, installation.agent, installation.scope):
            continue
        if _m.is_modified(entry):
            out.kept.append(entry.path)
            continue
        out.removed.append(entry.path)
        if not dry_run:
            path.unlink()
            _m.prune_empty_parents(path, stops)
    if not dry_run:
        for config in installation.entries:
            removed, kept = revert_entry(config, manifest, installation.agent, installation.scope)
            out.removed += removed
            out.kept += kept
        manifest.remove(installation.agent, installation.scope)
    else:
        out.removed += [f"{e.path} [{e.kind}]" for e in installation.entries]
    return out


# ------------------------------------------------------------------------------------------------ dry run
def render_plan(adapter: Adapter, plan: Plan, scope: str, manifest: _m.Manifest) -> list[str]:
    lines = [f"[dry-run] {adapter.pretty} ({adapter.name}, {plan.mode} mode, {scope} scope)"]
    previous = manifest.find(adapter.name, scope)
    for target in plan.targets:
        state = "unchanged" if target.dst.is_file() and _x.sha256_file(target.dst) == _x.sha256_bytes(
            target.payload) else ("update" if target.dst.exists() else "write")
        lines.append(f"  {state:9} {target.dst} ({len(target.payload)} bytes{', +x' if target.executable else ''})")
    for op in plan.ops:
        lines.append(f"  {'merge':9} {op.path}: {op.description}")
    for cmd in plan.commands:
        lines.append(f"  {'run':9} {' '.join(cmd)} (with --yes)")
    new_paths = {str(t.dst) for t in plan.targets}
    for entry in previous.files if previous else []:
        if entry.path not in new_paths and Path(entry.path).is_file():
            verb = "keep" if _m.is_modified(entry) else "remove"
            lines.append(f"  {verb:9} {entry.path} (no longer shipped{'; modified by you' if verb == 'keep' else ''})")
    for note in plan.notes:
        lines.append(f"  {'note':9} {note}")
    return lines
