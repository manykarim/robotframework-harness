"""robotcode plugin: `robotcode rfmcp ...` (client, NOT wrappable) + `robotcode rfmcp-serve` (daemon, @wrappable).

Why two top-level commands: robotcode applies `--wrapper` / profile `wrapper` by re-exec'ing the WHOLE CLI
when the invoked top-level command is @wrappable. Wrapping `rfmcp start` would put the short-lived starter
under `xvfb-run` (Xvfb dies when start returns); so `start` spawns `robotcode <root opts> rfmcp-serve`, and
robotcode's own wrapper logic wraps only the long-lived daemon.
"""
from __future__ import annotations

import sys
from typing import List

import click

from robotcode.plugin import Application, hookimpl, pass_application
from robotcode.plugin.click_helper.wrappable import wrappable

_PASS = {"ignore_unknown_options": True, "allow_extra_args": True, "help_option_names": []}


def _root_opts(ctx: click.Context) -> List[str]:
    p = ctx.find_root().params
    out: List[str] = []
    for c in p.get("config_files") or []:
        out += ["-c", str(c)]
    for pr in p.get("profiles") or []:
        out += ["-p", pr]
    if p.get("root"):
        out += ["-r", str(p["root"])]
    if p.get("wrapper"):
        out += ["--wrapper", p["wrapper"]]
    if p.get("no_wrapper"):
        out += ["--no-wrapper"]
    if p.get("verbose"):
        out += ["-v"]
    return out


@click.command(name="rfmcp", context_settings=_PASS, add_help_option=False)
@click.argument("args", nargs=-1, type=click.UNPROCESSED)
@click.pass_context
def rfmcp(ctx: click.Context, args: List[str]) -> None:
    """rf-mcp local helper: start | step | vars | status | interrupt | stop | build | batch."""
    from . import cli, proto

    args = list(args)
    if args and args[0] == "start":
        d_arg = None
        if "--dir" in args:
            i = args.index("--dir")
            d_arg = args[i + 1]
            del args[i : i + 2]
        daemon_cmd = [sys.executable, "-m", "robotcode.cli", *_root_opts(ctx), "rfmcp-serve"]
        ctx.exit(cli.start(proto.state_dir(d_arg), args[1:], daemon_cmd=daemon_cmd))
    ctx.exit(cli.main(args))


@wrappable
@click.command(name="rfmcp-serve", context_settings=_PASS, add_help_option=False)
@click.argument("args", nargs=-1, type=click.UNPROCESSED)
@pass_application
def rfmcp_serve(app: Application, args: List[str]) -> None:
    """(internal) run the rf-mcp helper daemon in the foreground; honours -p/--wrapper/robot.toml."""
    from .daemon import build_parser, serve

    opts = build_parser().parse_args(list(args))
    sys.exit(serve(app, opts))


@hookimpl
def register_cli_commands() -> List[click.Command]:
    return [rfmcp, rfmcp_serve]
