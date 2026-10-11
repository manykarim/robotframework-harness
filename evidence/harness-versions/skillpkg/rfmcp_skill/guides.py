"""`rfmcp guide [topic]` -- prints a bundled guide (generated from rf-mcp's guidance code by tools/gen_guides.py)."""
from __future__ import annotations

from pathlib import Path
from typing import Tuple

DIR = Path(__file__).with_name("guides")
ALIASES = {"locators": "browser", "playwright": "browser", "iframe": "browser", "iframes": "browser",
           "shadow": "browser", "shadow-dom": "browser", "browser-locators": "browser",
           "seleniumlibrary": "selenium", "api": "requests", "rest": "requests", "requestslibrary": "requests",
           "output": "results", "output.xml": "results", "result": "results", "rebot": "results",
           "wait": "waits", "timeouts": "waits", "timeout": "waits", "screenshot": "visual", "vision": "visual",
           "shell": "quoting", "heredoc": "quoting",
           "debugging": "debug", "fix": "debug", "failing": "debug", "failures": "debug", "repair": "debug",
           "explore": "explore", "exploring": "explore", "widgets": "explore", "forms": "explore", "form": "explore",
           "dropdown": "explore", "select": "explore", "checkbox": "explore", "radio": "explore", "date": "explore",
           "dates": "explore", "dialog": "explore", "dialogs": "explore", "alert": "explore", "popup": "explore",
           "cookie": "explore", "overlay": "explore", "unknown-page": "explore"}
SUMMARY = {
    "debug": "fix an existing failing suite: run, read output.xml, reproduce live, fix, re-run",
    "explore": "unknown live page: state controls, stable selectors, styled radios/checkboxes, dropdowns, dates, dialogs",
    "browser": "Browser/Playwright locators, iframes (>>>), shadow DOM, strict mode",
    "selenium": "SeleniumLibrary locators and frames",
    "requests": "RequestsLibrary sessions, JSON bodies, response access, status asserts",
    "results": "running robot, analyzing output.xml (robotcode results, ExecutionResult API)",
    "waits": "auto-waits, assertion retries (1 s!), Wait For Condition, long steps",
    "visual": "when a screenshot beats the DOM/ARIA tree",
    "quoting": "shell quoting for rfmcp step, heredocs",
}


def guide(topic: str) -> Tuple[str, bool]:
    t = ALIASES.get(topic.strip().lower(), topic.strip().lower())
    f = DIR / f"{t}.txt"
    if t and f.is_file():
        return f.read_text(), True
    lines = ["rfmcp guide <topic>:"] + [f"  {k:<9} {v}" for k, v in SUMMARY.items()]
    lines.append("portable suites: imports by path -> rfmcp guide debug (PORTABLE)")
    if t:
        lines.insert(0, f"unknown topic '{topic}'")
    return "\n".join(lines) + "\n", not t
