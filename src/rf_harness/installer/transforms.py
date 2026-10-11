"""Pure-ish transforms and config-file edits used by the adapters (stdlib only).

* ``${CLAUDE_PLUGIN_ROOT}`` substitution and launcher-argument injection for hook definitions;
* JSON merges that touch only the keys / hook groups rf-harness owns, preserving every other entry;
* text edits of Codex's ``config.toml`` trust store (``[hooks.state."<key>"] trusted_hash``) without a TOML writer;
* ``.gitignore`` line edits.

Adapted from robotframework-agentskills' ``installer/src/rf_agentskills/transforms.py`` (same author, Apache-2.0); the
TOML and YAML writers were replaced by targeted text edits so the installer keeps zero dependencies.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys
from pathlib import Path, PureWindowsPath
from typing import Any

PLUGIN_ROOT_TOKEN = "${CLAUDE_PLUGIN_ROOT}"
LAUNCHER_MARK = "rfh-launch"


# ------------------------------------------------------------------------------------------------ paths / hashing
def native_path(path: Path) -> str:
    """Absolute path for embedding in JSON/TOML/shell commands (forward slashes on Windows, no escaping needed)."""
    if sys.platform == "win32":
        return PureWindowsPath(path).as_posix()
    return str(path)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def json_digest(value: Any) -> str:
    return sha256_bytes(json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8"))


def substitute_plugin_root(text: str, root: str) -> str:
    return text.replace(PLUGIN_ROOT_TOKEN, root)


# ------------------------------------------------------------------------------------------------ hook definitions
def _command_keys(entry: dict[str, Any]) -> list[str]:
    return [k for k in ("command", "bash", "powershell") if isinstance(entry.get(k), str)]


def inject_launcher_args(hooks: Any, extra: list[str]) -> Any:
    """Append ``extra`` (e.g. ``--set RFH_STATIC=runtime-only``) to every launcher command in a hooks structure."""
    if not extra:
        return hooks
    suffix = " " + " ".join(extra)

    def walk(node: Any) -> Any:
        if isinstance(node, dict):
            out = {k: walk(v) for k, v in node.items()}
            for key in _command_keys(out):
                if LAUNCHER_MARK in out[key] and suffix not in out[key]:
                    out[key] = out[key] + suffix
            return out
        if isinstance(node, list):
            return [walk(v) for v in node]
        return node

    return walk(hooks)


def windows_python_prefix() -> str:
    """How files-mode hooks start the launcher on Windows, where ``python3`` usually does not exist."""
    import shutil

    if shutil.which("py"):
        return "py -3 -S"
    found = shutil.which("python")
    if found and "windowsapps" not in found.lower():     # skip the Microsoft Store alias stub
        return f'"{native_path(Path(found))}" -S'
    base = getattr(sys, "_base_executable", None) or sys.executable
    return f'"{native_path(Path(base))}" -S'


def windowsify(hooks: Any, prefix: str) -> Any:
    """Replace the leading ``python3 -S`` of launcher commands (not the PowerShell ``.cmd`` variant)."""

    def walk(node: Any) -> Any:
        if isinstance(node, dict):
            out = {k: walk(v) for k, v in node.items()}
            for key in ("command", "bash"):
                value = out.get(key)
                if isinstance(value, str) and value.startswith("python3 -S ") and LAUNCHER_MARK in value:
                    out[key] = prefix + value[len("python3 -S"):]
            return out
        if isinstance(node, list):
            return [walk(v) for v in node]
        return node

    return walk(hooks)


def render_hooks_file(text: str, support_dir: Path, extra: list[str], windows: bool | None = None) -> dict[str, Any]:
    """Load a plugin hooks file with ``${CLAUDE_PLUGIN_ROOT}`` pointing at ``support_dir`` and extra launcher args."""
    data = inject_launcher_args(json.loads(substitute_plugin_root(text, native_path(support_dir))), extra)
    if sys.platform == "win32" if windows is None else windows:
        data = windowsify(data, windows_python_prefix())
    return data


# ------------------------------------------------------------------------------------------------ JSON documents
def load_json_object(path: Path) -> tuple[dict[str, Any], int]:
    """(object, indent) of a JSON file; ``({}, 2)`` when missing. Raises ValueError for invalid JSON."""
    if not path.is_file():
        return {}, 2
    text = path.read_text(encoding="utf-8")
    if not text.strip():
        return {}, 2
    data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError(f"{path} does not contain a JSON object")
    match = re.search(r"^\{\s*\n([ \t]+)\"", text)
    indent = len(match.group(1).expandtabs(4)) if match else 2
    return data, indent or 2


def dump_json(data: Any, indent: int = 2) -> str:
    return json.dumps(data, indent=indent, ensure_ascii=False) + "\n"


def write_text_if_changed(path: Path, text: str) -> bool:
    if path.is_file() and path.read_text(encoding="utf-8") == text:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".rfh.tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)
    return True


def _walk(data: dict[str, Any], key_path: list[str], create: bool) -> dict[str, Any] | None:
    cursor = data
    for key in key_path:
        nxt = cursor.get(key)
        if not isinstance(nxt, dict):
            if not create:
                return None
            nxt = {}
            cursor[key] = nxt
        cursor = nxt
    return cursor


def get_json_value(path: Path, key_path: list[str], key: str) -> Any:
    try:
        data, _ = load_json_object(path)
    except (OSError, ValueError):
        return None
    parent = _walk(data, key_path, create=False)
    return None if parent is None else parent.get(key)


def merge_json_keys(path: Path, key_path: list[str], values: dict[str, Any]) -> tuple[list[str], bool]:
    """Set ``values`` in the object at ``key_path``; return (newly added keys, file changed)."""
    data, indent = load_json_object(path)
    parent = _walk(data, key_path, create=True)
    assert parent is not None
    added = [k for k in values if k not in parent]
    parent.update(values)
    return added, write_text_if_changed(path, dump_json(data, indent))


def remove_json_keys(path: Path, key_path: list[str], keys: list[str]) -> bool:
    """Delete ``keys`` at ``key_path``; prune emptied parents; delete the file when it ends up ``{}``."""
    if not path.is_file():
        return False
    data, indent = load_json_object(path)
    parent = _walk(data, key_path, create=False)
    if parent is None:
        return False
    changed = False
    for key in keys:
        if key in parent:
            del parent[key]
            changed = True
    for depth in range(len(key_path), 0, -1):
        holder = _walk(data, key_path[: depth - 1], create=False)
        if holder is not None and holder.get(key_path[depth - 1]) == {}:
            del holder[key_path[depth - 1]]
    if not changed:
        return False
    if data:
        write_text_if_changed(path, dump_json(data, indent))
    else:
        path.unlink()
    return True


# ------------------------------------------------------------------------------------------------ hook blocks
def group_owned(group: Any, marker: str) -> bool:
    """A hook matcher-group belongs to rf-harness when one of its commands contains the install-dir marker."""
    if not isinstance(group, dict) or not marker:
        return False
    for hook in group.get("hooks") or []:
        if isinstance(hook, dict) and any(marker in str(hook.get(k, "")) for k in _command_keys(hook)):
            return True
    return False


def merge_hook_groups(path: Path, events: dict[str, list[Any]], marker: str, top_key: str = "hooks") -> bool:
    """Replace rf-harness' groups (by ``marker``) per event, keep everyone else's; return whether the file changed."""
    data, indent = load_json_object(path)
    block = data.get(top_key)
    if not isinstance(block, dict):
        block = {}
    for event, groups in events.items():
        current = block.get(event)
        existing: list[Any] = current if isinstance(current, list) else []
        block[event] = [g for g in existing if not group_owned(g, marker)] + list(groups)
    data[top_key] = block
    return write_text_if_changed(path, dump_json(data, indent))


def owned_hook_groups(path: Path, marker: str, top_key: str = "hooks") -> dict[str, list[Any]]:
    try:
        data, _ = load_json_object(path)
    except (OSError, ValueError):
        return {}
    block = data.get(top_key)
    if not isinstance(block, dict):
        return {}
    out: dict[str, list[Any]] = {}
    for event, groups in block.items():
        mine = [g for g in groups if group_owned(g, marker)] if isinstance(groups, list) else []
        if mine:
            out[event] = mine
    return out


def remove_hook_groups(path: Path, marker: str, events: list[str] | None = None, top_key: str = "hooks") -> bool:
    """Drop rf-harness' groups; prune emptied events / block; delete the file when it ends up ``{}``."""
    if not path.is_file():
        return False
    data, indent = load_json_object(path)
    block = data.get(top_key)
    if not isinstance(block, dict):
        return False
    changed = False
    for event in list(block) if events is None else events:
        groups = block.get(event)
        if not isinstance(groups, list):
            continue
        kept = [g for g in groups if not group_owned(g, marker)]
        if len(kept) != len(groups):
            changed = True
            if kept:
                block[event] = kept
            else:
                del block[event]
    if not changed:
        return False
    if not block:
        del data[top_key]
    if data:
        write_text_if_changed(path, dump_json(data, indent))
    else:
        path.unlink()
    return True


# ------------------------------------------------------------------------------------------------ Codex trust store
_TABLE_HEADER = re.compile(r"^\s*\[(?P<name>[^\[\]]+)\]\s*(#.*)?$")


def toml_basic_string(value: str) -> str:
    out = ['"']
    for ch in value:
        if ch == "\\":
            out.append("\\\\")
        elif ch == '"':
            out.append('\\"')
        elif ord(ch) < 0x20:
            out.append(f"\\u{ord(ch):04x}")
        else:
            out.append(ch)
    out.append('"')
    return "".join(out)


def _unquote_toml_key(text: str) -> str | None:
    text = text.strip()
    if text.startswith('"') and text.endswith('"') and len(text) >= 2:
        try:
            value = json.loads(text)
        except ValueError:
            return None
        return value if isinstance(value, str) else None
    if text.startswith("'") and text.endswith("'") and len(text) >= 2:
        return text[1:-1]
    return text


def _trust_table_key(header: str) -> str | None:
    """The hook key of a ``hooks.state."<key>"`` table header, else None."""
    match = re.match(r"^\s*hooks\s*\.\s*state\s*\.\s*(?P<key>\".*\"|'.*')\s*$", header)
    return _unquote_toml_key(match.group("key")) if match else None


def read_codex_trust(path: Path) -> dict[str, str]:
    """``{hook key: trusted_hash}`` from the ``[hooks.state."<key>"]`` tables of a Codex config.toml."""
    if not path.is_file():
        return {}
    current: str | None = None
    found: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        header = _TABLE_HEADER.match(line)
        if header and not line.lstrip().startswith("[["):
            current = _trust_table_key(header.group("name"))
            continue
        if line.lstrip().startswith("[["):
            current = None
            continue
        if current is not None:
            match = re.match(r'^\s*trusted_hash\s*=\s*"(?P<v>[^"]*)"', line)
            if match:
                found[current] = match.group("v")
    return found


def set_codex_trust(path: Path, entries: dict[str, str]) -> bool:
    """Write ``trusted_hash`` for each hook key (update in place or append a table); return whether it changed."""
    if not entries:
        return False
    text = path.read_text(encoding="utf-8") if path.is_file() else ""
    lines = text.splitlines()
    pending = dict(entries)
    current: str | None = None
    for index, line in enumerate(lines):
        header = _TABLE_HEADER.match(line)
        if header and not line.lstrip().startswith("[["):
            current = _trust_table_key(header.group("name"))
            continue
        if line.lstrip().startswith("[["):
            current = None
            continue
        if current in pending and re.match(r"^\s*trusted_hash\s*=", line):
            lines[index] = f"trusted_hash = {toml_basic_string(pending.pop(current))}"
    for index in range(len(lines) - 1, -1, -1):     # tables present but without trusted_hash
        header = _TABLE_HEADER.match(lines[index])
        if header and not lines[index].lstrip().startswith("[["):
            key = _trust_table_key(header.group("name"))
            if key in pending:
                lines.insert(index + 1, f"trusted_hash = {toml_basic_string(pending.pop(key))}")
    out = "\n".join(lines)
    for key, value in pending.items():
        out = out.rstrip("\n") + ("\n\n" if out.strip() else "")
        out += f"[hooks.state.{toml_basic_string(key)}]\ntrusted_hash = {toml_basic_string(value)}\n"
    if not out.endswith("\n"):
        out += "\n"
    if out == text:
        return False
    _validate_toml(out)
    write_text_if_changed(path, out)
    return True


def remove_codex_trust(path: Path, keys: list[str]) -> bool:
    """Remove the ``[hooks.state."<key>"]`` tables (only their ``trusted_hash``; other keys keep the table)."""
    if not path.is_file() or not keys:
        return False
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    wanted = set(keys)
    out: list[str] = []
    index = 0
    changed = False
    while index < len(lines):
        line = lines[index]
        header = _TABLE_HEADER.match(line)
        key = _trust_table_key(header.group("name")) if header and not line.lstrip().startswith("[[") else None
        if key not in wanted:
            out.append(line)
            index += 1
            continue
        body: list[str] = []
        index += 1
        while index < len(lines) and not lines[index].lstrip().startswith("["):
            body.append(lines[index])
            index += 1
        rest = [b for b in body if not re.match(r"^\s*trusted_hash\s*=", b)]
        changed = True
        if any(b.strip() and not b.strip().startswith("#") for b in rest):
            out.append(line)
            out.extend(rest)
        else:
            while out and not out[-1].strip():
                out.pop()
            if rest and index < len(lines):
                out.append("")
    if not changed:
        return False
    result = "\n".join(out).strip("\n")
    result = result + "\n" if result else ""
    _validate_toml(result)
    if result:
        write_text_if_changed(path, result)
    else:
        path.unlink()
    return True


def _validate_toml(text: str) -> None:
    """Refuse to write a config.toml that no longer parses (Python 3.11+, where tomllib exists)."""
    try:
        import tomllib  # type: ignore[import-not-found]
    except ImportError:  # pragma: no cover - Python 3.10
        return
    tomllib.loads(text)


def codex_project_trusted(config: Path, project: Path) -> bool:
    """Whether ``[projects."<project>"] trust_level = "trusted"`` is set in a Codex config.toml."""
    if not config.is_file():
        return False
    text = config.read_text(encoding="utf-8")
    try:
        import tomllib  # type: ignore[import-not-found]

        data = tomllib.loads(text)
        projects = data.get("projects") if isinstance(data, dict) else None
        if isinstance(projects, dict):
            for path in (str(project), native_path(project)):
                entry = projects.get(path)
                if isinstance(entry, dict) and entry.get("trust_level") == "trusted":
                    return True
        return False
    except ImportError:  # pragma: no cover - Python 3.10
        pass
    except ValueError:
        return False
    pattern = r"^\s*\[projects\.(?:" + "|".join(
        re.escape(toml_basic_string(p)) for p in {str(project), native_path(project)}) + r")\]\s*$"
    match = re.search(pattern + r"(.*?)(?=^\s*\[|\Z)", text, re.M | re.S)
    return bool(match and re.search(r'^\s*trust_level\s*=\s*"trusted"', match.group(1), re.M))


# ------------------------------------------------------------------------------------------------ text files
def ensure_line(path: Path, line: str) -> bool:
    """Append ``line`` to a text file (e.g. .gitignore) unless an equivalent line exists; return whether added."""
    text = path.read_text(encoding="utf-8") if path.is_file() else ""
    wanted = {line.strip(), line.strip().rstrip("/"), "/" + line.strip(), "/" + line.strip().rstrip("/")}
    if any(existing.strip() in wanted for existing in text.splitlines()):
        return False
    prefix = "" if not text or text.endswith("\n") else "\n"
    write_text_if_changed(path, text + prefix + line + "\n")
    return True


def remove_line(path: Path, line: str) -> bool:
    if not path.is_file():
        return False
    lines = path.read_text(encoding="utf-8").splitlines()
    kept = [x for x in lines if x.strip() != line.strip()]
    if len(kept) == len(lines):
        return False
    if any(x.strip() for x in kept):
        write_text_if_changed(path, "\n".join(kept) + "\n")
    else:
        path.unlink()
    return True


def remove_marked_blocks(text: str, begin: str, end: str) -> tuple[str, int]:
    """Remove every ``begin ... end`` block (regexes matching whole lines); return (text, removed count)."""
    pattern = re.compile(r"\n?^[^\n]*" + begin + r"[^\n]*$.*?^[^\n]*" + end + r"[^\n]*$\n?", re.M | re.S)
    result, count = pattern.subn("\n", text)
    if count:
        result = re.sub(r"\n{3,}", "\n\n", result).strip("\n")
        result = result + "\n" if result else ""
    return result, count
