"""Minimal stdlib prompts: a numbered multi-select with toggles, and yes/no confirmation."""

from __future__ import annotations

import sys
from collections.abc import Callable, Sequence

InputFn = Callable[[str], str]


def is_tty() -> bool:
    try:
        return sys.stdin.isatty() and sys.stdout.isatty()
    except (ValueError, OSError, AttributeError):
        return False


def multiselect(title: str, options: Sequence[tuple[str, str]], preselected: set[str],
                input_fn: InputFn | None = None, out: Callable[[str], None] = print) -> list[str] | None:
    """Toggle options by number; Enter confirms, ``q`` cancels (returns None). ``options`` = [(value, label)]."""
    ask = input_fn or input
    chosen = {value for value, _ in options if value in preselected}
    while True:
        out(title)
        for index, (value, label) in enumerate(options, 1):
            out(f"  [{'x' if value in chosen else ' '}] {index}. {label}")
        try:
            raw = ask("Toggle with numbers (e.g. '1 3'), a = all, n = none, Enter = confirm, q = cancel: ")
        except (EOFError, KeyboardInterrupt):
            return None
        raw = raw.strip().lower()
        if not raw:
            return [value for value, _ in options if value in chosen]
        if raw in ("q", "quit", "cancel"):
            return None
        if raw in ("a", "all"):
            chosen = {value for value, _ in options}
            continue
        if raw in ("n", "none"):
            chosen = set()
            continue
        for token in raw.replace(",", " ").split():
            if token.isdigit() and 1 <= int(token) <= len(options):
                value = options[int(token) - 1][0]
                chosen.symmetric_difference_update({value})
            else:
                out(f"  ignored '{token}'")


def confirm(question: str, default: bool = True, input_fn: InputFn | None = None) -> bool:
    suffix = " [Y/n] " if default else " [y/N] "
    try:
        answer = (input_fn or input)(question + suffix).strip().lower()
    except (EOFError, KeyboardInterrupt):
        return False
    if not answer:
        return default
    return answer in ("y", "yes")
