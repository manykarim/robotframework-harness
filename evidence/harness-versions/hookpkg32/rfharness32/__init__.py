"""rfharness32 -- Robot Framework agent harness made of an Agent Skill + hooks (research prototype, no agent CLI).

Entry point for every agent hook: ``python -S <pkg>/rfharness32/hook.py <event> --agent <name>`` (stdlib only,
fast) or ``python -m rfharness32.hook <event> --agent <name>``. Heavy work runs in two background daemons:
``rfharness32.execd`` (live RF session, file-step engine, page state) and ``rfharness32.lintd`` (robotcode
analyzer + robocop + portability: the static gate). Keep this module free of imports.
"""
__version__ = "0.1.0"
