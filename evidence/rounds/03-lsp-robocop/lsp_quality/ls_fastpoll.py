"""Launcher: robotcode language server with the diagnostics loop's 1 s idle poll capped (default 0.05 s).
usage: python ls_fastpoll.py language-server --stdio   (env RC_POLL=0.05)"""
import os, sys
import robotcode.language_server.common.parts.diagnostics as D
from robotcode.core.concurrent import check_current_task_canceled as _orig
POLL = float(os.environ.get("RC_POLL", "0.05"))
def _capped(at_least_seconds=None, raise_exception=True):
    if at_least_seconds is not None and at_least_seconds > POLL:
        at_least_seconds = POLL
    return _orig(at_least_seconds, raise_exception)
D.check_current_task_canceled = _capped
from robotcode.cli.__main__ import main
sys.exit(main())
