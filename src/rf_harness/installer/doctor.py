"""``rf-harness doctor``: prove the harness works, with one pass/fail line and a fix per check (task 4.6).

Per installed agent: files / settings present, Codex hooks trusted, and a synthetic hook event in that agent's
payload format sent through the launcher (the launcher's trace shows whether it reached the runtime). For the
project: the chosen Python environment, Robot Framework / robotcode / runtime versions, the libraries the suites
import (and Playwright browsers for Browser). Live readiness: a 10-second smoke step against the bundled demo page.
Exit code 1 when any check fails.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

from .. import __version__
from . import _assets, codex_trust, envfind, homes
from . import manifest as _m
from . import transforms as _x
from .adapters import Options, by_name
from .adapters._base import PLUGIN_ID

SETUP_RUNTIME = "uvx robotframework-harness install --runtime-only"
LAUNCHER_AGENT = {"claude-code": "claude", "codex": "codex", "copilot-cli": "copilot", "vscode": "vscode",
                  "opencode": "opencode"}
SMOKE_TIMEOUT = 10


@dataclass
class Check:
    name: str
    ok: bool
    detail: str = ""
    fix: str = ""

    def lines(self) -> list[str]:
        out = [f"{'PASS' if self.ok else 'FAIL'}  {self.name}" + (f": {self.detail}" if self.detail else "")]
        if not self.ok and self.fix:
            out.append(f"      fix: {self.fix}")
        return out


def demo_page() -> Path:
    checkout = Path(__file__).resolve().parents[3] / "demo" / "site" / "index.html"
    return checkout if checkout.is_file() else Path(__file__).resolve().parent / "demo_site" / "index.html"


def launcher_python() -> list[str] | None:
    """How the hook commands start the launcher on this machine (python3 -S; py -3 -S on Windows)."""
    if os.name == "nt":
        if shutil.which("py"):
            return ["py", "-3", "-S"]
        exe = shutil.which("python")
        return [exe, "-S"] if exe else None
    exe = shutil.which("python3")
    return [exe, "-S"] if exe else None


# ------------------------------------------------------------------------------------------------ agent checks
def _opts_for(ins: _m.Installation, project: Path) -> Options:
    return Options(scope=ins.scope, project=project, mode=ins.mode)


def check_installed(ins: _m.Installation, project: Path) -> Check:
    name = f"{ins.agent}: installed ({ins.mode} mode, {ins.scope} scope)"
    missing = [f.path for f in ins.files if not Path(f.path).is_file()]
    absent_entries = []
    for entry in ins.entries:
        path = Path(entry.path)
        if entry.kind == "json_keys":
            absent_entries += [f"{path} [{k}]" for k in entry.values if _x.get_json_value(path, entry.key_path, k)
                               is None]
        elif entry.kind == "json_hooks" and not _x.owned_hook_groups(path, entry.marker,
                                                                      entry.key_path[0] if entry.key_path else "hooks"):
            absent_entries.append(f"{path} [rf-harness hooks]")
    if missing or absent_entries:
        return Check(name, False, f"{len(missing)} file(s) and {len(absent_entries)} entr(y/ies) missing: "
                     + ", ".join((missing + absent_entries)[:3]), f"rf-harness install --agent {ins.agent} "
                     f"--scope {ins.scope} --mode {ins.mode}")
    detail = f"{len(ins.files)} files, {len(ins.entries)} config entries, bundle {ins.bundle_version}"
    if ins.bundle_version != __version__:
        return Check(name, False, detail + f" (installer is {__version__})",
                     f"rf-harness install --agent {ins.agent} --scope {ins.scope} --mode {ins.mode}")
    return Check(name, True, detail)


def check_copilot_trust(ins: _m.Installation, project: Path) -> Check | None:
    """Files mode at project scope writes .github/hooks/, which Copilot CLI runs only in trusted folders."""
    if ins.mode != "files" or ins.scope != "project":
        return None
    trusted = homes.copilot_folder_trusted(project)
    name = "copilot-cli: folder trusted (repository hooks run only in trusted folders)"
    if trusted:
        return Check(name, True, str(project))
    detail = "no Copilot config found" if trusted is None else f"{project} is not in trusted_folders"
    return Check(name, False, detail, f"start copilot in {project} once and trust the folder, or add it to "
                 f"trusted_folders in {homes.copilot_home() / 'config.json'}")


def check_codex_trust(ins: _m.Installation, project: Path) -> Check:
    adapter = by_name("codex")
    assert adapter is not None
    opts = _opts_for(ins, project)
    support = adapter.support_dir(opts)
    marker = _x.native_path(support / "bin" / "rfh-launch") if ins.mode == "files" and support else ""
    state, detail = codex_trust.status(project, ins.scope, marker=marker,
                                       plugin_id=PLUGIN_ID if ins.mode == "plugin" else "")
    if state == "trusted":
        return Check("codex: hooks trusted", True, detail)
    if state == "project-untrusted":
        return Check("codex: hooks trusted", False, detail, f"start codex in {project} once and accept the trust "
                     "prompt for the folder")
    if state == "missing" and ins.mode == "plugin":
        commands = " && ".join(" ".join(c) for c in adapter.plugin_commands(opts))  # type: ignore[attr-defined]
        return Check("codex: hooks trusted", False, detail, f"{commands}, then rf-harness install --agent codex "
                     "--yes (provisions trust) or /hooks in codex")
    return Check("codex: hooks trusted", False, detail,
                 f"rf-harness install --agent codex --scope {ins.scope} --yes, or {codex_trust.HOOKS_STEP}")


def probe(ins: _m.Installation, project: Path) -> Check:
    name = f"{ins.agent}: probe event reaches the harness"
    adapter = by_name(ins.agent)
    if adapter is None:
        return Check(name, False, f"unknown agent {ins.agent}")
    runner = launcher_python()
    if runner is None:
        return Check(name, False, "python3 is not on PATH, so the hook commands cannot start",
                     "install Python 3 and make `python3` available on PATH")
    support = adapter.support_dir(_opts_for(ins, project)) if ins.mode == "files" else None
    launcher = (support / "bin" / "rfh-launch") if support else _assets.plugin_root() / "bin" / "rfh-launch"
    if not launcher.is_file():
        return Check(name, False, f"launcher missing: {launcher}", f"rf-harness install --agent {ins.agent}")
    event, payload = adapter.probe_payload(project)
    with tempfile.TemporaryDirectory(prefix="rf-harness-doctor-") as tmp:
        trace_file = Path(tmp) / "trace.jsonl"
        # RFH_WATCH_PID: daemons a probe starts exit with doctor (running daemons of a real session are reused)
        env = dict(os.environ, RF_HARNESS_LAUNCH_TRACE=str(trace_file), RF_HARNESS_DEDUPE_S="0",
                   RFH_WATCH_PID=str(os.getpid()))
        try:
            proc = subprocess.run([*runner, str(launcher), event, "--agent", LAUNCHER_AGENT.get(ins.agent, "auto")],
                                  input=json.dumps(payload), capture_output=True, text=True, timeout=90,
                                  cwd=str(project), env=env)
        except (OSError, subprocess.SubprocessError) as exc:
            return Check(name, False, f"launcher did not finish: {exc}")
        try:
            records = [json.loads(line) for line in trace_file.read_text(encoding="utf-8").splitlines() if line]
        except (OSError, ValueError):
            records = []
    record = records[-1] if records else {}
    if proc.returncode != 0:
        return Check(name, False, f"launcher exited {proc.returncode}: {proc.stderr.strip()[-200:]}")
    out = proc.stdout.strip()
    if out:
        try:
            json.loads(out.splitlines()[-1])
        except ValueError:
            return Check(name, False, f"hook output is not JSON: {out[:120]!r}")
    if record.get("action") == "exec":
        return Check(name, True, f"{event} -> runtime {record.get('version')} in {record.get('python')} "
                     f"({record.get('source')}, {record.get('ms')} ms launcher)")
    status = record.get("status", "unknown")
    return Check(name, False, f"the launcher did not reach the runtime (runtime {status} in "
                 f"{record.get('python') or 'no interpreter'})", SETUP_RUNTIME)


# ------------------------------------------------------------------------------------------------ environment
def environment_checks(project: Path, explicit_python: str | None) -> tuple[list[Check], Path | None, dict | None]:
    checks: list[Check] = []
    recorded = envfind.harness_json(project).get("python")
    if explicit_python:
        choice = envfind.find_env(project, explicit_python)
    elif recorded and Path(recorded).is_file():
        choice = envfind.EnvChoice(Path(recorded), ".rf/harness.json", "recorded by rf-harness install")
    else:
        choice = envfind.find_env(project)
    if choice.python is None:
        checks.append(Check("python environment", False, choice.detail, "create a virtual environment (e.g. "
                            "`uv venv`) and install Robot Framework into it"))
        return checks, None, None
    libs = envfind.scan_libraries(project)
    info = envfind.inspect(choice.python, sorted(set(libs) | {"Browser", "rf_harness.runtime.smoke"}))
    if info is None:
        checks.append(Check("python environment", False, f"{choice.python} did not start", "check the interpreter"))
        return checks, choice.python, None
    versions = info.get("versions", {})
    imports = info.get("imports", {})
    checks.append(Check("python environment", True, f"{choice.python} (Python {info.get('python')}, {choice.source})"))
    checks.append(Check("robot framework", bool(imports.get("robot")), versions.get("robotframework") or "missing",
                        envfind._pip_hint(choice.python, "robotframework")))
    checks.append(Check("robotcode", bool(imports.get("robotcode")), versions.get("robotcode") or "missing",
                        SETUP_RUNTIME))
    runtime_ok = envfind.runtime_ready(info) and envfind.runtime_compatible(info)
    runtime_v = versions.get(envfind.DIST)
    detail = runtime_v or "not installed"
    if runtime_v and not envfind.runtime_compatible(info):
        detail += f" (installer {__version__}: incompatible)"
    checks.append(Check("harness runtime", runtime_ok, detail, SETUP_RUNTIME))
    for lib in envfind.library_report(choice.python, libs, info):
        used = ", ".join(lib.files[:2]) + (" ..." if len(lib.files) > 2 else "")
        ok = lib.importable and not lib.extra
        detail = ("importable" if lib.importable else "not importable") + f" (used by {used})"
        if lib.extra:
            detail += "; " + "; ".join(lib.extra)
        checks.append(Check(f"library {lib.name}", ok, detail, lib.fix))
    return checks, choice.python, info


def _smoke_suite(page: Path, browser: bool) -> str:
    url = page.resolve().as_uri()
    if browser:
        return f"""*** Settings ***
Library    Browser    timeout={SMOKE_TIMEOUT}s

*** Test Cases ***
rf-harness doctor smoke
    New Browser    chromium    headless=True
    New Page    {url}
    Get Text    h1    ==    rf-harness demo
    Fill Text    id=name    doctor
    Click    id=greet
    Get Text    id=greeting    ==    Hello, doctor!
    [Teardown]    Close Browser    ALL
"""
    path = str(page.resolve()).replace("\\", "/")
    return f"""*** Settings ***
Library    OperatingSystem

*** Test Cases ***
rf-harness doctor smoke
    ${{html}}=    Get File    {path}
    Should Contain    ${{html}}    rf-harness demo
"""


def _browser_fix(python: Path, info: dict | None) -> str | None:
    """Fix line when the live smoke cannot run Browser, else None."""
    imports = (info or {}).get("imports", {})
    rfbrowser = python.parent / ("rfbrowser.exe" if os.name == "nt" else "rfbrowser")
    init = f"{rfbrowser if rfbrowser.exists() else 'rfbrowser'} init chromium"
    if not imports.get("Browser"):
        return f"{envfind._pip_hint(python, 'robotframework-browser')} && {init}"
    if not envfind.browser_binaries_present(info or {}):
        return init
    return None


def live_smoke(python: Path | None, info: dict | None) -> Check:
    name = f"live smoke ({SMOKE_TIMEOUT} s step against demo/site)"
    if python is None or not envfind.runtime_ready(info):
        return Check(name, False, "the harness runtime is not importable in the project environment", SETUP_RUNTIME)
    page = demo_page()
    imports = (info or {}).get("imports", {})
    suite_dir = None
    if imports.get("rf_harness.runtime.smoke"):
        fix = _browser_fix(python, info)
        if fix:
            return Check(name, False, "the live session opens the page with the Browser library and headless chromium, "
                         "which are not ready in the project environment", fix)
        cmd = [str(python), "-m", "rf_harness.runtime.smoke", "--page", str(page), "--timeout", str(SMOKE_TIMEOUT)]
        how = "live session (rf_harness.runtime.smoke)"
    else:
        browser = _browser_fix(python, info) is None
        suite_dir = tempfile.mkdtemp(prefix="rf-harness-smoke-")
        suite = Path(suite_dir) / "rf_harness_doctor_smoke.robot"
        suite.write_text(_smoke_suite(page, browser), encoding="utf-8")
        cmd = [str(python), "-m", "robot", "--output", "NONE", "--log", "NONE", "--report", "NONE", "--console",
               "dotted", str(suite)]
        how = "plain robot run" + (" with Browser" if browser else " (Browser not ready: file check only)")
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=SMOKE_TIMEOUT * 9, stdin=subprocess.DEVNULL)
    except subprocess.TimeoutExpired:
        return Check(name, False, f"{how} timed out", "run `rf-harness doctor` again; check the browser setup")
    except OSError as exc:
        return Check(name, False, f"{how}: {exc}")
    finally:
        if suite_dir:
            shutil.rmtree(suite_dir, ignore_errors=True)
    result: dict = {}
    for line in reversed(proc.stdout.strip().splitlines()):
        try:
            parsed = json.loads(line)
        except ValueError:
            continue
        if isinstance(parsed, dict):
            result = parsed
            break
    if proc.returncode == 0:
        if result:
            return Check(name, True, f"{how}: page title {result.get('title')!r} in {result.get('ms')} ms")
        return Check(name, True, how)
    error = str(result.get("error") or " | ".join((proc.stdout + proc.stderr).strip().splitlines()[-3:]))
    return Check(name, False, f"{how} failed: {error.splitlines()[0][:300] if error else 'no output'}",
                 "see the error above; `rf-harness doctor` lists missing libraries and browsers")


# ------------------------------------------------------------------------------------------------ entry point
def run(project: Path, agents: list[str] | None, scopes: list[str], explicit_python: str | None, live: bool = True,
        out: object = print) -> int:
    emit = out if callable(out) else print
    checks: list[Check] = []
    installations: list[_m.Installation] = []
    for scope in scopes:
        installations += _m.Manifest.load(_m.manifest_path(scope, project)).installations
    if agents:
        names = {ins.agent for ins in installations}
        for agent in agents:
            if agent not in names:
                checks.append(Check(f"{agent}: installed", False, "not installed",
                                    f"rf-harness install --agent {agent}"))
        installations = [ins for ins in installations if ins.agent in agents]
    if not installations and not agents:
        checks.append(Check("agents", False, "rf-harness is not installed for any agent here",
                            "rf-harness install"))
    for ins in installations:
        checks.append(check_installed(ins, project))
        if ins.agent == "codex":
            checks.append(check_codex_trust(ins, project))
        if ins.agent == "copilot-cli":
            ct = check_copilot_trust(ins, project)
            if ct is not None:
                checks.append(ct)
        checks.append(probe(ins, project))
    env_checks, python, info = environment_checks(project, explicit_python)
    checks += env_checks
    if live:
        checks.append(live_smoke(python, info))
    emit(f"rf-harness doctor {__version__} ({project})")
    for check in checks:
        for line in check.lines():
            emit(line)
    failed = [c for c in checks if not c.ok]
    emit(f"{len(checks) - len(failed)} passed, {len(failed)} failed")
    return 1 if failed else 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(run(Path.cwd(), None, ["project", "user"], None))
