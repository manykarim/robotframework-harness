"""Command line entry point (``rf-harness`` / ``robotframework-harness``).

Commands:
  targets     list the supported agents with detection result and version
  install     set up skill + hooks per agent (plugin or files mode, project or user scope) and the runtime
  uninstall   remove what install recorded (unmodified items only)
  list        show the recorded installations
  doctor      prove the harness works (install, trust, probe event, environment, live smoke)
  version     print the installer and plugin versions

Adapted from robotframework-agentskills' ``installer/src/rf_agentskills/cli.py`` (same author, Apache-2.0); stdlib
only so ``uvx robotframework-harness install`` starts fast anywhere.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import shutil
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path

from rf_harness import __version__

from . import _assets, coexist, doctor, envfind, executor, prompt
from . import manifest as _m
from . import transforms as _x
from .adapters import ALL_ADAPTERS, Options, Plan, all_names, by_name
from .adapters._base import MARKETPLACE_REPO, PLUGIN_ID
from .homes import claude_home, codex_home, copilot_home, opencode_home, user_agents_skills

STATIC_ENV = ("RFH_STATIC", "runtime-only")
PLUGIN_REMOVE = {"claude-code": f"claude plugin uninstall {PLUGIN_ID}", "codex": f"codex plugin remove {PLUGIN_ID}"}


class UsageError(Exception):
    """Invalid command line selection."""


# ------------------------------------------------------------------------------------------------ parser
def _selection_args(sp: argparse.ArgumentParser) -> None:
    group = sp.add_mutually_exclusive_group()
    group.add_argument("--agents", metavar="SEL", help="all | detected | comma-separated agents: "
                       + ", ".join(all_names()))
    group.add_argument("--agent", metavar="AGENT", help="a single agent (" + ", ".join(all_names()) + ")")


def _scope_args(sp: argparse.ArgumentParser, default: str | None = "project") -> None:
    sp.add_argument("--scope", choices=("project", "user"), default=default,
                    help=("project: the project directory (default); user: your home directory" if default else
                          "check only this scope (default: both)"))
    sp.add_argument("--project", metavar="DIR", type=Path, help="project directory (default: current directory)")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="rf-harness",
                                description="Set up the Robot Framework agent harness for coding agents.")
    p.add_argument("--version", action="version", version=f"rf-harness {__version__}")
    sub = p.add_subparsers(dest="command", metavar="COMMAND")

    sub.add_parser("targets", help="list supported agents with detection result and version")

    sp = sub.add_parser("install", help="install the harness for one or more agents and the runtime")
    _selection_args(sp)
    sp.add_argument("--mode", choices=("plugin", "files"), default="plugin",
                    help="plugin (default): point the agent at the marketplace; files: copy skill, hooks and launcher "
                    "(OpenCode always uses files)")
    _scope_args(sp)
    sp.add_argument("--python", metavar="PATH", help="interpreter (or environment directory) of the project")
    runtime = sp.add_mutually_exclusive_group()
    runtime.add_argument("--runtime-only", action="store_true",
                         help="only provision the runtime into the project environment")
    runtime.add_argument("--no-runtime", action="store_true", help="do not provision the runtime")
    sp.add_argument("--runtime-source", metavar="PATH", help="install the runtime from a local source checkout "
                    "instead of PyPI (testing before a release)")
    sp.add_argument("--ref", metavar="TAG", help="plugin mode: pin the marketplace to a tag, e.g. v1.0.0")
    sp.add_argument("--coexist", choices=("keep", "replace"), default="keep",
                    help="keep (default): keep other RF agent tools and let rf-agentskills report static errors "
                    "(RFH_STATIC=runtime-only); replace: rf-harness runs its full static checks and research "
                    "prototype installs are removed (other tools' entries are never modified)")
    sp.add_argument("--dry-run", action="store_true", help="print every planned change without writing anything")
    sp.add_argument("--yes", "-y", action="store_true", help="accept the defaults without prompting (runs the Codex "
                    "plugin commands and installs the runtime)")
    sp.add_argument("--no-input", action="store_true", help="never prompt")

    sp = sub.add_parser("uninstall", help="remove what install recorded (modified files are kept)")
    _selection_args(sp)
    _scope_args(sp)
    sp.add_argument("--dry-run", action="store_true", help="print what would be removed")
    sp.add_argument("--yes", "-y", action="store_true", help="do not ask for confirmation")
    sp.add_argument("--no-input", action="store_true", help="never prompt")

    sp = sub.add_parser("list", help="show recorded installations (project and user)")
    sp.add_argument("--project", metavar="DIR", type=Path, help="project directory (default: current directory)")

    sp = sub.add_parser("doctor", help="check that the harness works; exits non-zero on any failure")
    _selection_args(sp)
    _scope_args(sp, default=None)
    sp.add_argument("--python", metavar="PATH", help="interpreter of the project (default: .rf/harness.json)")
    sp.add_argument("--no-live", action="store_true", help="skip the live smoke step")

    sub.add_parser("version", help="print the installer and plugin versions")
    return p


# ------------------------------------------------------------------------------------------------ helpers
def _project(args: argparse.Namespace) -> Path:
    return Path(getattr(args, "project", None) or Path.cwd()).expanduser().resolve()


def _detected() -> list[str]:
    return [cls.name for cls in ALL_ADAPTERS if cls().detect()]


def explicit_selection(args: argparse.Namespace) -> list[str] | None:
    if getattr(args, "agent", None):
        names = [args.agent]
    elif getattr(args, "agents", None):
        token = args.agents.strip().lower()
        if token == "all":
            return list(all_names())
        if token == "detected":
            return _detected()
        names = [n.strip() for n in args.agents.split(",") if n.strip()]
    else:
        return None
    resolved: list[str] = []
    for name in names:
        adapter = by_name(name.lower())
        if adapter is None:
            raise UsageError(f"unknown agent {name!r}; valid: {', '.join(all_names())}")
        if adapter.name not in resolved:
            resolved.append(adapter.name)
    return resolved


def _interactive(args: argparse.Namespace) -> bool:
    return not getattr(args, "yes", False) and not getattr(args, "no_input", False) and prompt.is_tty()


def _looks_like_project(project: Path) -> bool:
    if any((project / m).exists() for m in (".venv", "pyproject.toml", ".git", ".rf", "robot.toml")):
        return True
    return bool(envfind._suite_files(project, limit=1))


def _record_project(manifest: _m.Manifest, key: str, value: str) -> None:
    items = manifest.project.setdefault(key, [])
    if value not in items:
        items.append(value)


def _gitignore(project: Path, manifest: _m.Manifest, line: str) -> None:
    if _x.ensure_line(project / ".gitignore", line):
        _record_project(manifest, "gitignore", line)
        print(f"  added {line} to {project / '.gitignore'}")


def _uninstall_stops(project: Path) -> set[Path]:
    home = Path.home()
    return {project, home, project / ".claude", project / ".codex", project / ".github", project / ".opencode",
            project / ".agents", project / ".agents" / "skills", project / ".github" / "hooks", home / ".claude",
            claude_home(), codex_home(), copilot_home(), copilot_home() / "hooks", opencode_home(),
            user_agents_skills().parent, user_agents_skills()}


# ------------------------------------------------------------------------------------------------ targets / list
def cmd_targets(_args: argparse.Namespace) -> int:
    adapters = [cls() for cls in ALL_ADAPTERS]
    detected = [a.detect() for a in adapters]
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(adapters)) as pool:
        versions = list(pool.map(lambda pair: pair[0].version() if pair[1] else None, zip(adapters, detected, strict=True)))
    print(f"{'agent':12} {'name':20} {'detected':9} {'modes':14} version")
    for adapter, found, version in zip(adapters, detected, versions, strict=True):
        modes = "plugin, files" if adapter.supports_plugin else "files"
        print(f"{adapter.name:12} {adapter.pretty:20} {'yes' if found else 'no':9} {modes:14} {version or '-'}")
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    project = _project(args)
    rows = []
    for scope in ("project", "user"):
        path = _m.manifest_path(scope, project)
        rows += [(ins, path) for ins in _m.Manifest.load(path).installations]
    if not rows:
        print("no rf-harness installations recorded (project or user scope)")
        return 0
    print(f"{'agent':12} {'scope':8} {'mode':7} {'bundle':8} {'files':6} {'entries':8} installed_at")
    for ins, path in rows:
        print(f"{ins.agent:12} {ins.scope:8} {ins.mode:7} {ins.bundle_version:8} {len(ins.files):<6} "
              f"{len(ins.entries):<8} {ins.installed_at}  ({path})")
    return 0


def cmd_version(_args: argparse.Namespace) -> int:
    print(f"rf-harness {__version__}")
    try:
        root = _assets.plugin_root()
        print(f"plugin {_assets.bundle_version(root)} ({root})")
    except (_assets.AssetsMissing, OSError, ValueError) as exc:
        print(f"plugin: {exc}")
    return 0


# ------------------------------------------------------------------------------------------------ install
def _choose_agents(args: argparse.Namespace) -> list[str]:
    selection = explicit_selection(args)
    if selection is not None:
        return selection
    detected = _detected()
    if _interactive(args):
        options = [(cls.name, f"{cls.pretty} ({cls.name})" + ("  [detected]" if cls.name in detected else ""))
                   for cls in ALL_ADAPTERS]
        chosen = prompt.multiselect("Install the Robot Framework agent harness for:", options, set(detected))
        if chosen is None:
            raise UsageError("cancelled")
        return chosen
    return detected


def _coexistence(args: argparse.Namespace, project: Path, interactive: bool) -> tuple[tuple[str, str], ...]:
    found = coexist.scan(project)
    if not found.findings:
        return ()
    print("Other Robot Framework agent tooling found:")
    for finding in found.findings:
        print(f"  - {finding.describe()}")
    if found.agentskills:
        if args.coexist == "keep":
            print("  rf-agentskills validates .robot edits too: keeping both; rf-harness reports runtime results only "
                  "(RFH_STATIC=runtime-only). --coexist replace lets rf-harness run its static checks as well (then "
                  "disable rf-agentskills' validation hooks yourself).")
        else:
            print("  --coexist replace: rf-harness runs its full static checks; rf-agentskills' entries are left "
                  "untouched, disable its validation hooks yourself to avoid duplicate reports.")
    if found.of("rf-mcp"):
        print("  rf-mcp is configured: both routes work, but agents may mix MCP tools and hook feedback; the docs "
              "explain when to use which.")
    prototypes = found.of("prototype")
    if prototypes:
        remove = args.coexist == "replace"
        if not remove and interactive and not args.dry_run:
            remove = prompt.confirm("Remove the research-prototype harness entries listed above (superseded by "
                                    "rf-harness)?", default=False)
        for finding in prototypes if remove else []:
            if args.dry_run:
                print(f"  [dry-run] would remove {finding.describe()}")
            elif coexist.remove_prototype(finding):
                print(f"  removed {finding.describe()}")
        if not remove:
            print("  research-prototype entries kept (remove them with --coexist replace).")
    return (STATIC_ENV,) if found.agentskills and args.coexist == "keep" else ()


def _run_commands(commands: list[list[str]]) -> str:
    """Run plugin-mode commands; return an error message ('' on success)."""
    for cmd in commands:
        exe = shutil.which(cmd[0])
        if exe is None:
            return f"{cmd[0]} is not on PATH; run the commands above yourself"
        print(f"  $ {' '.join(cmd)}")
        try:
            proc = subprocess.run([exe, *cmd[1:]], capture_output=True, text=True, timeout=300,
                                  stdin=subprocess.DEVNULL)
        except (OSError, subprocess.SubprocessError) as exc:
            return f"{' '.join(cmd)}: {exc}"
        if proc.returncode != 0:
            return f"`{' '.join(cmd)}` exited {proc.returncode}: {(proc.stderr or proc.stdout).strip()[-300:]}"
    return ""


def _report(outcome: executor.Outcome, plan: Plan) -> None:
    if not outcome.changed and not outcome.kept and not outcome.skipped:
        print(f"  no changes ({outcome.unchanged} files up to date)")
    else:
        print(f"  {len(outcome.written)} files written, {outcome.unchanged} unchanged, "
              f"{len(outcome.merged)} config entries updated, {len(outcome.removed)} obsolete items removed")
    for path in outcome.removed:
        print(f"  removed {path} (no longer shipped)")
    for path in outcome.kept:
        print(f"  kept {path} (modified by you)")
    for path in outcome.skipped:
        print(f"  error: {path} exists and was not written by rf-harness; move it away and re-run", file=sys.stderr)
    for warning in outcome.warnings:
        print(f"  warning: {warning}")
    for note in plan.notes:
        print(f"  -> {note}")


def _install_agents(args: argparse.Namespace, project: Path, interactive: bool) -> int:
    selection = _choose_agents(args)
    if not selection:
        print("error: no agents detected and none selected; pass --agents all|detected|<list> or --agent <name> "
              f"(valid: {', '.join(all_names())})", file=sys.stderr)
        return 1
    coexist_env = _coexistence(args, project, interactive)
    manifest = _m.Manifest.load(_m.manifest_path(args.scope, project))
    rc = 0
    for name in selection:
        adapter = by_name(name)
        assert adapter is not None
        mode = args.mode
        if mode == "plugin" and not adapter.supports_plugin:
            print(f"{adapter.pretty}: no plugin marketplace, installing files instead.")
            mode = "files"
        opts = Options(scope=args.scope, project=project, mode=mode, ref=args.ref, coexist_env=coexist_env)
        plan = adapter.plan(opts)
        if args.dry_run:
            for line in executor.render_plan(adapter, plan, args.scope, manifest):
                print(line)
            continue
        print(f"{adapter.pretty} ({mode} mode, {args.scope} scope)")
        command_error = _run_commands(plan.commands) if plan.commands and args.yes else ""
        outcome = executor.apply_plan(adapter, plan, args.scope, manifest)
        manifest.save()
        if command_error:
            outcome.failed = True
            outcome.warnings.append(command_error)
        _report(outcome, plan)
        if outcome.failed:
            rc = 1
    if not args.dry_run and args.scope == "project":
        if coexist_env and args.mode == "plugin":
            envfind.write_harness_json(project, {"env": dict(coexist_env)})
            for key, _ in coexist_env:
                _record_project(manifest, "harness_env", key)
        _gitignore(project, manifest, _m.MANIFEST_DIR + "/")
        manifest.save()
    return rc


def _provision_runtime(args: argparse.Namespace, project: Path, interactive: bool) -> int:
    choice = envfind.find_env(project, args.python)
    if choice.python is None:
        hint = "" if choice.source == "--python" else "; create a project environment (e.g. `uv venv`) or pass --python"
        print(f"error: {choice.detail}{hint}", file=sys.stderr)
        return 1
    print(f"Python environment: {choice.python} ({choice.detail})")
    info = envfind.inspect(choice.python)
    if info is None:
        print(f"error: {choice.python} did not start", file=sys.stderr)
        return 1
    ready = envfind.runtime_ready(info) and envfind.runtime_compatible(info)
    if ready and not args.runtime_source:
        if args.dry_run:
            print(f"[dry-run] runtime {info['versions'].get(envfind.DIST)} is already installed in {choice.python}")
            return 0
    else:
        cmd = envfind.install_command(choice.python, __version__, args.runtime_source)
        if args.dry_run:
            print(f"[dry-run] would run: {' '.join(cmd)}")
            print(f"[dry-run] would write {project / envfind.HARNESS_JSON} and add .rf/ to .gitignore")
            return 0
        consent = args.yes or (interactive and prompt.confirm(
            f"Install the harness runtime into this environment?\n  {' '.join(cmd)}\n", default=True))
        if not consent:
            print(f"Runtime not installed; run: {' '.join(cmd)}  (or: rf-harness install --runtime-only --yes)")
            return 0
        ok, tail = envfind.run_install(choice.python, __version__, args.runtime_source)
        if not ok:
            print(f"error: runtime installation failed:\n{tail}", file=sys.stderr)
            return 1
        info = envfind.inspect(choice.python) or {}
    imports = info.get("imports", {})
    versions = info.get("versions", {})
    for module in ("robot", "robotcode", "rf_harness.runtime"):
        print(f"  {'ok  ' if imports.get(module) else 'FAIL'} import {module}")
    if not all(imports.get(m) for m in ("robot", "robotcode", "rf_harness.runtime")):
        print("error: the runtime does not import in the project environment", file=sys.stderr)
        return 1
    manifest = _m.Manifest.load(_m.manifest_path("project", project))
    envfind.write_harness_json(project, {
        "python": str(choice.python), "version": versions.get(envfind.DIST), "source": choice.source,
        "site_packages": info.get("sys_path", []), "installer": __version__,
    })
    print(f"  runtime {versions.get(envfind.DIST)} (Robot Framework {versions.get('robotframework')}, robotcode "
          f"{versions.get('robotcode')}) recorded in {project / envfind.HARNESS_JSON}")
    _gitignore(project, manifest, ".rf/")
    manifest.save()
    for lib in envfind.library_report(choice.python, envfind.scan_libraries(project)):
        if lib.importable and not lib.extra:
            print(f"  ok   library {lib.name}")
        else:
            reason = "; ".join(lib.extra) or "not installed in this environment"
            print(f"  MISSING library {lib.name} ({reason}; used by {', '.join(lib.files[:2])}): {lib.fix}")
    return 0


def cmd_install(args: argparse.Namespace) -> int:
    if args.ref and args.mode != "plugin":
        raise UsageError("--ref needs --mode plugin")
    project = _project(args)
    interactive = _interactive(args)
    rc = 0
    if not args.runtime_only:
        rc |= _install_agents(args, project, interactive)
    if args.no_runtime:
        return rc
    if args.scope == "user" and not args.runtime_only and not args.python and not _looks_like_project(project):
        print("Runtime: not provisioned (no project here). In each Robot Framework project run: "
              "uvx robotframework-harness install --runtime-only")
        return rc
    return rc | _provision_runtime(args, project, interactive)


# ------------------------------------------------------------------------------------------------ uninstall
def _cleanup_project(project: Path, manifest: _m.Manifest) -> None:
    harness_keys = manifest.project.get("harness_env", [])
    path = project / envfind.HARNESS_JSON
    if harness_keys and path.is_file():
        data = envfind.harness_json(project)
        env = {k: v for k, v in (data.get("env") or {}).items() if k not in harness_keys}
        if env:
            data["env"] = env
        else:
            data.pop("env", None)
        _x.write_text_if_changed(path, _x.dump_json(data))
    for line in manifest.project.get("gitignore", []):
        if line == _m.MANIFEST_DIR + "/" or not (project / line.rstrip("/")).exists():
            _x.remove_line(project / ".gitignore", line)
    manifest.project = {}


def cmd_uninstall(args: argparse.Namespace) -> int:
    project = _project(args)
    manifest = _m.Manifest.load(_m.manifest_path(args.scope, project))
    selection = explicit_selection(args)
    installations = [i for i in manifest.installations if selection is None or i.agent in selection]
    if not installations:
        print(f"nothing to uninstall ({args.scope} scope, {manifest.path})")
        return 0
    if _interactive(args) and not args.dry_run:
        names = ", ".join(i.agent for i in installations)
        if not prompt.confirm(f"Remove rf-harness for {names} ({args.scope} scope)?", default=True):
            print("cancelled")
            return 0
    stops = _uninstall_stops(project)
    verb = "would remove" if args.dry_run else "removed"
    for ins in installations:
        outcome = executor.uninstall(ins, manifest, stops, dry_run=args.dry_run)
        print(f"{ins.agent} ({ins.mode} mode, {ins.scope} scope): {verb} {len(outcome.removed)} items")
        for item in outcome.removed:
            print(f"  {verb} {item}")
        for item in outcome.kept:
            print(f"  kept {item} (modified by you)")
        if ins.mode == "plugin" and ins.agent in PLUGIN_REMOVE:
            print(f"  -> the agent keeps its own plugin copy; remove it with: {PLUGIN_REMOVE[ins.agent]}")
    if args.dry_run:
        return 0
    if not manifest.installations and args.scope == "project":
        _cleanup_project(project, manifest)
    manifest.save()
    if args.scope == "project":
        print("The runtime stays in the project environment (remove it with: uv pip uninstall robotframework-harness).")
    return 0


# ------------------------------------------------------------------------------------------------ doctor
def cmd_doctor(args: argparse.Namespace) -> int:
    scopes = [args.scope] if args.scope else ["project", "user"]
    return doctor.run(_project(args), explicit_selection(args), scopes, args.python, live=not args.no_live)


# ------------------------------------------------------------------------------------------------ entry
HANDLERS = {"targets": cmd_targets, "install": cmd_install, "uninstall": cmd_uninstall, "list": cmd_list,
            "doctor": cmd_doctor, "version": cmd_version}


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)
    if args.command is None:
        parser.print_help()
        print(f"\nrf-harness {__version__}; marketplace: {MARKETPLACE_REPO}")
        return 0
    try:
        return int(HANDLERS[args.command](args))
    except UsageError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except _assets.AssetsMissing as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
