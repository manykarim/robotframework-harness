"""Fake ``codex`` CLI for installer tests: ``--version``, ``plugin ...`` (logged) and ``app-server`` (JSON-RPC
``initialize`` + ``hooks/list``), modeled on codex-cli 0.162: hooks come from ``$CODEX_HOME/hooks.json`` (source user)
and ``<cwd>/.codex/hooks.json`` when the project is trusted (source project); keys are
``<file>:<snake_event>:<group>:<hook>``; trust comes from ``[hooks.state."<key>"] trusted_hash`` in config.toml.
The hash is a fake (sha256 of the hook definition), parsed independently of the installer's code.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys
from pathlib import Path

SNAKE = {"SessionStart": "session_start", "UserPromptSubmit": "user_prompt_submit", "PreToolUse": "pre_tool_use",
         "PostToolUse": "post_tool_use", "Stop": "stop", "SessionEnd": "session_end"}


def codex_home() -> Path:
    return Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex")


def config_text() -> str:
    path = codex_home() / "config.toml"
    return path.read_text(encoding="utf-8") if path.is_file() else ""


def trust_state() -> dict[str, str]:
    state: dict[str, str] = {}
    for key, value in re.findall(r'^\[hooks\.state\."((?:[^"\\]|\\.)*)"\]\s*\ntrusted_hash\s*=\s*"([^"]*)"',
                                 config_text(), re.M):
        state[json.loads(f'"{key}"')] = value
    return state


def project_trusted(cwd: str) -> bool:
    pattern = r'^\[projects\.' + re.escape(json.dumps(cwd)) + r'\]\s*\ntrust_level\s*=\s*"trusted"'
    return re.search(pattern, config_text(), re.M) is not None


def fake_hash(event: str, group: dict, hook: dict) -> str:
    blob = json.dumps({"event": event, "matcher": group.get("matcher"), "command": hook.get("command"),
                       "timeout": hook.get("timeout")}, sort_keys=True)
    return "sha256:" + hashlib.sha256(blob.encode()).hexdigest()


def hooks_in(path: Path, source: str, state: dict[str, str]) -> list[dict]:
    if not path.is_file():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    out = []
    for event, groups in (data.get("hooks") or {}).items():
        for gi, group in enumerate(groups):
            for hi, hook in enumerate(group.get("hooks") or []):
                key = f"{path}:{SNAKE.get(event, event.lower())}:{gi}:{hi}"
                current = fake_hash(event, group, hook)
                stored = state.get(key)
                out.append({"key": key, "eventName": event, "command": hook.get("command"),
                            "matcher": group.get("matcher"), "source": source, "pluginId": None, "isManaged": False,
                            "currentHash": current,
                            "trustStatus": "trusted" if stored == current else ("modified" if stored else "untrusted")})
    return out


def app_server() -> int:
    for line in sys.stdin:
        try:
            msg = json.loads(line)
        except ValueError:
            continue
        if msg.get("method") == "initialize":
            print(json.dumps({"jsonrpc": "2.0", "id": msg["id"], "result": {"userAgent": "fake"}}), flush=True)
        elif msg.get("method") == "hooks/list":
            cwd = msg.get("params", {}).get("cwd") or os.getcwd()
            state = trust_state()
            hooks = hooks_in(codex_home() / "hooks.json", "user", state)
            if project_trusted(cwd):
                hooks += hooks_in(Path(cwd) / ".codex" / "hooks.json", "project", state)
            print(json.dumps({"jsonrpc": "2.0", "id": msg["id"],
                              "result": {"data": [{"cwd": cwd, "hooks": hooks, "warnings": [], "errors": []}]}}),
                  flush=True)
    return 0


def main(argv: list[str]) -> int:
    if argv[:1] == ["--version"]:
        print("codex-cli 0.0.0-fake")
        return 0
    if argv[:1] == ["app-server"]:
        return app_server()
    log = os.environ.get("FAKE_CODEX_LOG")
    if log:
        with open(log, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(argv) + "\n")
    return int(os.environ.get("FAKE_CODEX_EXIT", "0"))


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
