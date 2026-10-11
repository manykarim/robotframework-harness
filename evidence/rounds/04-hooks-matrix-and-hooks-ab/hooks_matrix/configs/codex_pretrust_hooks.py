#!/usr/bin/env python3
"""Pre-trust Codex hooks without the TUI (/hooks) and without --dangerously-bypass-hook-trust.
Verified on codex-cli 0.161.0 (trustprobe/): app-server `hooks/list` returns key + currentHash; writing
[hooks.state."<key>"] trusted_hash = "<currentHash>" into $CODEX_HOME/config.toml makes `codex exec` run the hook.
Usage: CODEX_HOME=... python3 codex_pretrust_hooks.py <project_dir>   (prints TOML to append)"""
import json, os, select, subprocess, sys, time
proj = sys.argv[1]
p = subprocess.Popen(["codex", "app-server"], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, cwd=proj)
send = lambda m: (p.stdin.write((json.dumps(m) + "\n").encode()), p.stdin.flush())
def recv(i, t=20):
    end = time.time() + t
    while time.time() < end:
        if select.select([p.stdout], [], [], 0.5)[0]:
            m = json.loads(p.stdout.readline())
            if m.get("id") == i:
                return m
send({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"clientInfo": {"name": "pretrust", "version": "0"}}}); recv(1)
send({"jsonrpc": "2.0", "method": "initialized", "params": {}})
send({"jsonrpc": "2.0", "id": 2, "method": "hooks/list", "params": {"cwd": proj}})
for d in recv(2)["result"]["data"]:
    for h in d["hooks"]:
        if h["trustStatus"] != "trusted" and not h["isManaged"]:
            print(f'\n[hooks.state."{h["key"]}"]\ntrusted_hash = "{h["currentHash"]}"')
p.terminate()
