"""Codex hook trust: Codex runs a hook only after it is trusted (``/hooks`` in the TUI).

Provisioning works like the round-4 ``codex_pretrust_hooks.py`` (verified on codex-cli 0.161 and 0.162): start
``codex app-server``, call ``hooks/list`` for the project, and for each rf-harness hook write
``[hooks.state."<key>"] trusted_hash = "<currentHash>"`` into ``$CODEX_HOME/config.toml``. Only hooks whose command
contains the rf-harness launcher marker (files mode) or that come from the rf-harness plugin (plugin mode) are
trusted. Codex lists ``<project>/.codex/`` hooks only for trusted projects; for an untrusted project the hashes are
read with a temporary CODEX_HOME that trusts the project, so the hooks are pre-trusted once the user trusts it.
"""

from __future__ import annotations

import json
import os
import queue
import shutil
import subprocess
import tempfile
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from . import transforms as _x
from .homes import codex_home

HOOKS_STEP = "start `codex` in the project, run /hooks and trust the rf-harness hooks"


def codex_exe() -> str | None:
    return shutil.which("codex")


def _rpc(exe: str, cwd: Path, home: Path, timeout: float) -> list[dict[str, Any]] | None:
    env = dict(os.environ, CODEX_HOME=str(home))
    try:
        home.mkdir(parents=True, exist_ok=True)     # the app-server exits at once when CODEX_HOME does not exist
        proc = subprocess.Popen([exe, "app-server"], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                stderr=subprocess.DEVNULL, cwd=str(cwd), env=env)
    except OSError:
        return None
    lines: queue.Queue[bytes] = queue.Queue()

    def pump() -> None:
        assert proc.stdout is not None
        for line in proc.stdout:
            lines.put(line)
        lines.put(b"")

    threading.Thread(target=pump, daemon=True).start()
    deadline = time.monotonic() + timeout

    def send(message: dict[str, Any]) -> None:
        assert proc.stdin is not None
        proc.stdin.write((json.dumps(message) + "\n").encode("utf-8"))
        proc.stdin.flush()

    def wait(msg_id: int) -> dict[str, Any] | None:
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return None
            try:
                line = lines.get(timeout=remaining)
            except queue.Empty:
                return None
            if not line:
                return None
            try:
                message = json.loads(line)
            except ValueError:
                continue
            if isinstance(message, dict) and message.get("id") == msg_id:
                return message

    try:
        send({"jsonrpc": "2.0", "id": 1, "method": "initialize",
              "params": {"clientInfo": {"name": "rf-harness", "version": "1"}}})
        if wait(1) is None:
            return None
        send({"jsonrpc": "2.0", "method": "initialized", "params": {}})
        send({"jsonrpc": "2.0", "id": 2, "method": "hooks/list", "params": {"cwd": str(cwd)}})
        reply = wait(2)
        if reply is None or not isinstance(reply.get("result"), dict):
            return None
        hooks: list[dict[str, Any]] = []
        for group in reply["result"].get("data") or []:
            hooks.extend(h for h in group.get("hooks") or [] if isinstance(h, dict))
        return hooks
    except (OSError, ValueError):
        return None
    finally:
        try:
            proc.terminate()
            proc.wait(timeout=5)
        except (OSError, subprocess.TimeoutExpired):
            proc.kill()


def list_hooks(cwd: Path, home: Path | None = None, timeout: float = 30.0) -> list[dict[str, Any]] | None:
    """Hooks Codex sees for ``cwd`` (None when codex is missing or the app-server did not answer)."""
    exe = codex_exe()
    if not exe:
        return None
    return _rpc(exe, cwd, home or codex_home(), timeout)


def is_ours(hook: dict[str, Any], marker: str = "", plugin_id: str = "") -> bool:
    if hook.get("isManaged"):
        return False
    command = str(hook.get("command") or "")
    if marker and marker in command:
        return True
    return bool(plugin_id) and (hook.get("pluginId") == plugin_id or
                                (hook.get("source") == "plugin" and "rfh-launch" in command))


def _project_hooks_untrusted(project: Path, marker: str, plugin_id: str) -> list[dict[str, Any]]:
    with tempfile.TemporaryDirectory(prefix="rf-harness-codex-") as tmp:
        config = Path(tmp) / "config.toml"
        config.write_text(f"[projects.{_x.toml_basic_string(_x.native_path(project))}]\ntrust_level = \"trusted\"\n",
                          encoding="utf-8")
        hooks = list_hooks(project, Path(tmp)) or []
    return [h for h in hooks if h.get("source") == "project" and is_ours(h, marker, plugin_id)]


@dataclass
class TrustResult:
    ok: bool
    entries: dict[str, str] = field(default_factory=dict)
    message: str = ""
    project_trusted: bool = True


def our_hooks(project: Path, scope: str, marker: str = "", plugin_id: str = "") -> tuple[list[dict[str, Any]] | None,
                                                                                      bool]:
    """(rf-harness hooks Codex lists, project trusted?). For an untrusted project, project hooks come from a probe."""
    hooks = list_hooks(project)
    if hooks is None:
        return None, True
    mine = [h for h in hooks if is_ours(h, marker, plugin_id)]
    trusted = True
    if scope == "project" and marker and not _x.codex_project_trusted(codex_home() / "config.toml", project):
        trusted = False
        if not any(h.get("source") == "project" for h in mine):
            mine += _project_hooks_untrusted(project, marker, plugin_id)
    return mine, trusted


def provision(project: Path, scope: str, marker: str = "", plugin_id: str = "") -> TrustResult:
    """Trust exactly the rf-harness hooks; return the written ``{key: hash}`` (empty + message when impossible)."""
    if not codex_exe():
        return TrustResult(False, message="codex is not on PATH, so its hook trust could not be provisioned")
    mine, project_trusted = our_hooks(project, scope, marker, plugin_id)
    if mine is None:
        return TrustResult(False, message="`codex app-server` did not list the hooks")
    entries = {str(h["key"]): str(h["currentHash"]) for h in mine if h.get("key") and h.get("currentHash")}
    if not entries:
        return TrustResult(False, message="codex lists no rf-harness hooks yet", project_trusted=project_trusted)
    config = codex_home() / "config.toml"
    try:
        _x.set_codex_trust(config, entries)
    except (OSError, ValueError) as exc:
        return TrustResult(False, message=f"could not update {config}: {exc}", project_trusted=project_trusted)
    return TrustResult(True, entries, project_trusted=project_trusted)


def status(project: Path, scope: str, marker: str = "", plugin_id: str = "") -> tuple[str, str]:
    """('trusted' | 'untrusted' | 'missing' | 'unavailable' | 'project-untrusted', detail) for doctor."""
    if not codex_exe():
        return "unavailable", "codex is not on PATH"
    mine, project_trusted = our_hooks(project, scope, marker, plugin_id)
    if mine is None:
        return "unavailable", "`codex app-server` did not list the hooks"
    if not mine:
        return "missing", "codex lists no rf-harness hooks"
    stored = _x.read_codex_trust(codex_home() / "config.toml")
    bad = [h for h in mine if h.get("trustStatus") != "trusted" and stored.get(str(h.get("key"))) != h.get("currentHash")]
    if bad:
        return "untrusted", f"{len(bad)} of {len(mine)} rf-harness hooks are not trusted"
    if not project_trusted:
        return "project-untrusted", "the hooks are pre-trusted, but Codex loads .codex/ only in trusted projects"
    return "trusted", f"{len(mine)} rf-harness hooks trusted"
