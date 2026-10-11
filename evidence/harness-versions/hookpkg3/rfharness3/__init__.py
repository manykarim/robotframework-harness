"""rfharness3 -- Robot Framework agent harness made of an Agent Skill + hooks (research prototype, no agent CLI).

Entry point for every agent hook: ``python -S <pkg>/rfharness3/hook.py <event> --agent <name>`` (stdlib only,
fast) or ``python -m rfharness3.hook <event> --agent <name>``. Heavy work runs in two background daemons:
``rfharness3.execd`` (live RF session, file-step engine, page state) and ``rfharness3.lintd`` (robotcode
analyzer + robocop + portability: the static gate). Keep this module free of imports.
"""
__version__ = "0.1.0"
