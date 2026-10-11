"""rfharness2 -- Robot Framework agent harness made of an Agent Skill + hooks (research prototype, no agent CLI).

Entry point for every agent hook: ``python -S <pkg>/rfharness2/hook.py <event> --agent <name>`` (stdlib only,
fast) or ``python -m rfharness2.hook <event> --agent <name>``. Heavy work runs in two background daemons:
``rfharness2.execd`` (live RF session, file-step engine, page state) and ``rfharness2.lintd`` (robotcode
analyzer + robocop + portability: the static gate). Keep this module free of imports.
"""
__version__ = "0.1.0"
