#!/usr/bin/env python3
"""Round-2 agent-compat orchestrator: runs tiny headless sessions of claude / codex / opencode /
copilot against a scratch project and observes the probe daemon from OUTSIDE.

  python3 orchestrate.py <agent> <scenario> [<scenario> ...]
  scenarios: s1_detach s2_cross_env s3_naive s4_native s5_stdin_timeout s6_mcp
Results: runs/<agent>/<scenario>/{agent_stdout.log,agent_stderr.log,result.json}
"""
import json
import os
import shutil
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

BASE = Path(__file__).resolve().parent
COMMON = BASE / "common"
RUNS = BASE / "runs"
RC = "~/workspace/robotcode-experiments/.venv/bin/robotcode"
MCP_URL = "http://127.0.0.1:6850/mcp"
TOKEN = "probe-token-123"

PORTS = {"claude": 6810, "codex": 6820, "opencode": 6830, "copilot": 6840}
MODELS = {
    "claude": "claude-haiku-4-5",
    "codex": "gpt-5.6-luna",
    "opencode": "minimax-coding-plan/MiniMax-M2.7",
    "copilot": "gpt-4.1",
}
TIMEOUTS = {"s1_detach": 240, "s2_cross_env": 300, "s3_naive": 240, "s4_native": 300,
            "s5_stdin_timeout": 600, "s6_mcp": 240, "s7_setsid": 240, "s8_replserver": 300}


def proj_for(agent, scenario):
    key = "detach" if scenario in ("s1_detach", "s2_cross_env") else scenario
    return RUNS / agent / f"proj_{key}"


def port_for(agent, scenario):
    off = {"s1_detach": 0, "s2_cross_env": 0, "s3_naive": 1, "s4_native": 2, "s7_setsid": 4}.get(scenario, 3)
    return PORTS[agent] + off


def prompt_for(agent, scenario, proj, port):
    if scenario == "s1_detach":
        return (
            "Run these three shell commands in the current directory, each as its own SEPARATE tool call "
            "(never combine them into one call, never add `&`), then report each output verbatim:\n"
            f"1) python3 daemon.py start --port {port} --label {agent}-detach\n"
            f"2) PROBE_WHO={agent}-call2 python3 client.py ping\n"
            f"3) sleep 5; PROBE_WHO={agent}-call3 python3 client.py ping\n"
            "Do not run anything else and do not stop the daemon.")
    if scenario == "s2_cross_env":
        return (
            "Run each of these shell commands in the current directory as its own SEPARATE tool call, in order, "
            "keep going if one fails, and report each output verbatim:\n"
            f"1) PROBE_WHO={agent}-newsession python3 client.py ping\n"
            "2) python3 client.py stop\n"
            "3) curl -sI https://www.saucedemo.com | head -1\n"
            "4) ls ~/.cache/ms-playwright | head -3\n"
            f"5) echo probe > $HOME/.cache/rfprobe_{agent}.txt && echo HOME_WRITE_OK; "
            f"echo probe > /tmp/rfprobe_{agent}.txt && echo TMP_WRITE_OK\n"
            f"6) {RC} repl --plain --no-history -d {proj}/out < browser_probe.txt 2>&1 | grep -E 'TITLE|FAIL'\n"
            "Do not run anything else.")
    if scenario == "s3_naive":
        return (
            "Run these two shell commands in the current directory, each as its own SEPARATE tool call, "
            "exactly as written, and report each output verbatim:\n"
            f"1) nohup python3 daemon.py run --port {port} --label {agent}-naive > nohup.out 2>&1 &\n"
            f"2) sleep 2; PROBE_WHO={agent}-naive2 python3 client.py ping\n"
            "Do not stop the daemon and do not run anything else.")
    if scenario == "s7_setsid":
        return (
            "Run these two shell commands in the current directory, each as its own SEPARATE tool call, "
            "exactly as written, and report each output verbatim:\n"
            f"1) setsid -f python3 daemon.py run --port {port} --label {agent}-setsidf > setsid.out 2>&1 < /dev/null; echo launched\n"
            f"2) sleep 2; PROBE_WHO={agent}-setsidf2 python3 client.py ping\n"
            "Do not stop the daemon and do not run anything else.")
    if scenario == "s8_replserver":
        return (
            "Run these four shell commands in the current directory, each as its own SEPARATE tool call, strictly "
            "one after another (never in parallel), exactly as written, and report each output verbatim:\n"
            f"1) setsid -f {RC} repl-server --pipe-server .rf/rs.sock -d out > .rf/server.log 2>&1 < /dev/null; "
            "for i in $(seq 40); do [ -S .rf/rs.sock ] && break; sleep 0.25; done; echo started\n"
            "2) python3 rfstep.py run --pipe .rf/rs.sock $'Import Library    Browser\\nNew Browser    chromium    "
            "headless=True\\nNew Page    https://www.saucedemo.com'\n"
            "3) python3 rfstep.py run --pipe .rf/rs.sock $'Fill Text    id=user-name    standard_user\\nFill Text    "
            "id=password    secret_sauce\\nClick    id=login-button\\nGet Url'\n"
            "4) python3 rfstep.py stop --pipe .rf/rs.sock\n"
            "Do not run anything else.")
    if scenario == "s4_native":
        return (
            f"Start the long-running server `python3 daemon.py run --port {port} --label {agent}-native` "
            "using your shell tool's OWN background / async / detached execution mode (do NOT use `&`, nohup, "
            "setsid, disown or any shell-level backgrounding). Then, in a SEPARATE tool call, run "
            f"`sleep 2; PROBE_WHO={agent}-native2 python3 client.py ping`. Report both outputs verbatim and name "
            "the tool/parameter you used for background mode. Do not stop the server. If your shell tool has no "
            "background mode, say NO_BACKGROUND_MODE and stop without running anything.")
    if scenario == "s5_stdin_timeout":
        return (
            "Two small capability checks; report verbatim what happened in each.\n"
            "STEP 1: Start an interactive `python3 -q -i` process and keep it running. Then, in a SEPARATE later "
            "tool call, write the line `print(6*7)` to the stdin of that SAME already-running process and read its "
            "output; then send `exit()`. Do NOT emulate this with pipes, heredocs or `echo ... | python3`. If none "
            "of your tools can write to the stdin of an already-running process, say NO_STDIN_TOOL and go to step 2. "
            "Name the tool(s) you used.\n"
            "STEP 2: Run `date +%T; sleep 70; date +%T; echo SLEEP_DONE` as ONE tool call WITHOUT setting any "
            "timeout parameter. Report whether it completed, timed out, or was moved to background, plus any "
            "message you got.\n"
            "STEP 3: Only if step 2 did not print SLEEP_DONE: run it again with the largest timeout your tool allows "
            "and report the result and the timeout value you used.")
    if scenario == "s6_mcp":
        return (
            "Use the MCP server named `echoprobe` (not the shell): list its tools, then call its echo tool with "
            f"text `{agent}-hello` and report the tool result verbatim. If you cannot see that server, say "
            "NO_ECHOPROBE.")
    raise ValueError(scenario)


def clean_env():
    env = {k: v for k, v in os.environ.items() if not (k.startswith("CLAUDE") or k == "CLAUDECODE")}
    env.pop("ANTHROPIC_BASE_URL", None)
    env["ECHOPROBE_TOKEN"] = TOKEN
    return env


def prepare(agent, scenario, proj, port, cell):
    proj.mkdir(parents=True, exist_ok=True)
    for f in ("daemon.py", "client.py"):
        shutil.copy2(COMMON / f, proj / f)
    (proj / "port").write_text(str(port))
    (proj / "out").mkdir(exist_ok=True)
    if scenario == "s8_replserver":
        shutil.copy2(BASE.parent.parent / "stepwise" / "rfstep.py", proj / "rfstep.py")
        (proj / "robot.toml").touch()
        (proj / ".rf").mkdir(exist_ok=True)
    (proj / "browser_probe.txt").write_text(
        "Import Library    Browser\nNew Browser    chromium    headless=True\n"
        "New Page    https://www.saucedemo.com\n${t}=    Get Title\nLog    TITLE=${t}    console=True\n"
        "Close Browser\n")
    home = RUNS / agent / "home"
    home.mkdir(parents=True, exist_ok=True)
    if agent == "claude":
        shutil.copy2(Path.home() / ".claude" / ".credentials.json", home / ".credentials.json")
        if not (home / ".claude.json").exists():
            shutil.copy2(Path.home() / ".claude.json", home / ".claude.json")
        mcp = {"mcpServers": {}}
        if scenario == "s6_mcp":
            mcp = {"mcpServers": {"echoprobe": {"type": "http", "url": MCP_URL,
                                                "headers": {"Authorization": f"Bearer {TOKEN}"}}}}
        (cell / "claude_mcp.json").write_text(json.dumps(mcp, indent=1))
    elif agent == "codex":
        shutil.copy2(Path.home() / ".codex" / "auth.json", home / "auth.json")
        cfg = f'model = "{MODELS["codex"]}"\nmodel_reasoning_effort = "low"\n'
        cfg += f'[projects."{proj}"]\ntrust_level = "trusted"\n'
        if scenario == "s6_mcp":
            cfg += ('[mcp_servers.echoprobe]\n'
                    f'url = "{MCP_URL}"\n'
                    'bearer_token_env_var = "ECHOPROBE_TOKEN"\n')
        (home / "config.toml").write_text(cfg)
    elif agent == "opencode":
        cfg = {"$schema": "https://opencode.ai/config.json",
               "permission": {"edit": "allow", "bash": "allow", "webfetch": "allow",
                              "external_directory": "allow"}}
        if scenario == "s6_mcp":
            cfg["mcp"] = {"echoprobe": {"type": "remote", "url": MCP_URL, "enabled": True,
                                        "headers": {"Authorization": f"Bearer {TOKEN}"}}}
        (proj / "opencode.json").write_text(json.dumps(cfg, indent=1))
    elif agent == "copilot":
        mcp = {"mcpServers": {"echoprobe": {"type": "http", "url": MCP_URL,
                                            "headers": {"Authorization": f"Bearer {TOKEN}"},
                                            "tools": ["*"]}}}
        (cell / "copilot_mcp.json").write_text(json.dumps(mcp, indent=1))
    return home


def build_cmd(agent, scenario, prompt, proj, home, cell):
    env = clean_env()
    if agent == "claude":
        env["CLAUDE_CONFIG_DIR"] = str(home)
        cmd = ["claude", "-p", prompt, "--model", MODELS["claude"], "--output-format", "stream-json",
               "--verbose", "--dangerously-skip-permissions", "--max-turns", "14",
               "--mcp-config", str(cell / "claude_mcp.json"), "--strict-mcp-config"]
    elif agent == "codex":
        env["CODEX_HOME"] = str(home)
        cmd = ["codex", "exec", "--json", "--skip-git-repo-check", "-C", str(proj),
               "--dangerously-bypass-approvals-and-sandbox", prompt]
    elif agent == "opencode":
        cmd = ["opencode", "run", "--dir", str(proj), "-m", MODELS["opencode"], "--format", "json",
               "--dangerously-skip-permissions", prompt]
    elif agent == "copilot":
        cmd = ["copilot", "-p", prompt, "--model", MODELS["copilot"], "--allow-all", "--no-ask-user",
               "--output-format", "json", "-C", str(proj), "--log-dir", str(cell / "copilot_logs"),
               "--no-auto-update", "--disable-builtin-mcps"]
        if scenario == "s6_mcp":
            cmd += ["--additional-mcp-config", "@" + str(cell / "copilot_mcp.json")]
    else:
        raise ValueError(agent)
    return cmd, env


def pid_alive(pid):
    try:
        os.kill(pid, 0)
        st = Path(f"/proc/{pid}/stat").read_text().split()
        return st[2] != "Z"
    except Exception:
        return False


PATTERNS = {"s8_replserver": ("repl-server", "index.js", "headless_shell")}
CUR_SCENARIO = {"name": None}


def daemon_pids(proj):
    """All live daemon.py processes (or s8: repl-server/node/chromium) whose cwd is proj."""
    pats = PATTERNS.get(CUR_SCENARIO["name"])
    if pats:
        out = []
        for d in Path("/proc").iterdir():
            if not d.name.isdigit():
                continue
            try:
                cmd = (d / "cmdline").read_bytes().replace(b"\0", b" ").decode()
                if any(x in cmd for x in pats) and "claude -p" not in cmd and "copilot" not in cmd \
                        and "codex" not in cmd and "opencode" not in cmd and os.readlink(d / "cwd") == str(proj):
                    out.append(int(d.name))
            except Exception:
                continue
        return out
    out = []
    for d in Path("/proc").iterdir():
        if not d.name.isdigit():
            continue
        try:
            cmd = (d / "cmdline").read_bytes().replace(b"\0", b" ").decode()
            if "daemon.py" not in cmd or "python" not in cmd:
                continue
            cwd = os.readlink(d / "cwd")
            if cwd == str(proj):
                out.append(int(d.name))
        except Exception:
            continue
    return out


def proc_info(pid):
    try:
        st = Path(f"/proc/{pid}/stat").read_text()
        rest = st[st.rindex(")") + 2:].split()
        ppid, pgid, sid = int(rest[1]), int(rest[2]), int(rest[3])
        cmd = Path(f"/proc/{pid}/cmdline").read_bytes().replace(b"\0", b" ").decode()[:160]
        return {"pid": pid, "ppid": ppid, "pgid": pgid, "sid": sid, "cmd": cmd}
    except Exception:
        return None


def ancestry(pid):
    chain = []
    while pid and pid > 1 and len(chain) < 12:
        i = proc_info(pid)
        if not i:
            break
        chain.append(i)
        pid = i["ppid"]
    return chain


def heartbeat_age(proj):
    try:
        return round(time.time() - float((proj / "heartbeat").read_text().strip()), 1)
    except Exception:
        return None


def run(agent, scenario):
    CUR_SCENARIO["name"] = scenario
    proj = proj_for(agent, scenario)
    port = port_for(agent, scenario)
    cell = RUNS / agent / scenario
    if cell.exists():
        shutil.rmtree(cell)
    cell.mkdir(parents=True)
    home = prepare(agent, scenario, proj, port, cell)
    prompt = prompt_for(agent, scenario, proj, port)
    cmd, env = build_cmd(agent, scenario, prompt, proj, home, cell)
    (cell / "cmd.json").write_text(json.dumps({"cmd": cmd, "prompt": prompt}, indent=1))

    samples = []
    first_seen = {}
    stop_mon = threading.Event()

    def monitor():
        t0 = time.time()
        while not stop_mon.is_set():
            pids = daemon_pids(proj)
            for p in pids:
                if p not in first_seen:
                    first_seen[p] = {"t": round(time.time() - t0, 1), "ancestry": ancestry(p)}
            samples.append((round(time.time() - t0, 1), pids))
            time.sleep(0.5)

    mon = threading.Thread(target=monitor, daemon=True)
    t_start = time.time()
    mon.start()
    timed_out = False
    with open(cell / "agent_stdout.log", "wb") as o, open(cell / "agent_stderr.log", "wb") as e:
        p = subprocess.Popen(cmd, cwd=str(proj), env=env, stdout=o, stderr=e, stdin=subprocess.DEVNULL,
                             start_new_session=True)
        try:
            rc = p.wait(timeout=TIMEOUTS[scenario])
        except subprocess.TimeoutExpired:
            timed_out = True
            os.killpg(p.pid, signal.SIGTERM)
            time.sleep(3)
            try:
                os.killpg(p.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            rc = None
    t_end = time.time()
    time.sleep(3)
    after3 = daemon_pids(proj)
    hb3 = heartbeat_age(proj)
    time.sleep(7)
    after10 = daemon_pids(proj)
    hb10 = heartbeat_age(proj)
    stop_mon.set()
    mon.join()
    # compress samples into alive intervals
    transitions = []
    prev = None
    for t, pids in samples:
        cur = tuple(sorted(pids))
        if cur != prev:
            transitions.append({"t": t, "pids": list(cur)})
            prev = cur
    res = {
        "agent": agent, "scenario": scenario, "model": MODELS[agent], "rc": rc, "timed_out": timed_out,
        "session_wall_s": round(t_end - t_start, 1), "port": port,
        "daemon_transitions": transitions, "first_seen": first_seen,
        "alive_3s_after_session": after3, "alive_10s_after_session": after10,
        "heartbeat_age_3s": hb3, "heartbeat_age_10s": hb10,
        "pings_log": (proj / "pings.log").read_text() if (proj / "pings.log").exists() else "",
        "daemon_log_tail": (proj / "daemon.log").read_text()[-1500:] if (proj / "daemon.log").exists() else "",
    }
    # cleanup policy: keep the s1 daemon alive for s2 (cross-session); kill everything else
    if scenario != "s1_detach":
        for pid in daemon_pids(proj):
            try:
                os.kill(pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
        time.sleep(1)
        for pid in daemon_pids(proj):
            try:
                os.kill(pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        res["killed_by_orchestrator"] = True
    (cell / "result.json").write_text(json.dumps(res, indent=1))
    print(json.dumps({k: res[k] for k in ("agent", "scenario", "rc", "timed_out", "session_wall_s",
                                          "alive_3s_after_session", "alive_10s_after_session",
                                          "daemon_transitions")}))
    # truncate pings/daemon logs for next scenario on same proj? keep (s2 appends)
    return res


if __name__ == "__main__":
    agent = sys.argv[1]
    for sc in sys.argv[2:]:
        run(agent, sc)
