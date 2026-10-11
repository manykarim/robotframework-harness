r"""Value graders accept equivalent assertion forms (round-7 fix, stdlib only).

A suite may assert a value with a regex keyword (`Should Match Regexp    ${summary}    Total\s*\$916\.99`), so the
file holds `\$916\.99`, not `$916.99`. A value grader (file_contains / files_contain whose regex contains a digit and
at least one escaped literal character such as `\.` or `\$`) is matched as  (?:<regex>)|(?:<tolerant regex>)  where the
tolerant regex allows up to two backslashes before every escaped literal character (the raw regex form and the
Robot-Framework-escaped `\\.` form). Other regexes are used unchanged.
"""
from __future__ import annotations

import re

_LEADING_FLAGS = re.compile(r"^\(\?[aiLmsux]+\)")


def _escaped_literal_positions(rx: str) -> list[int]:
    r"""Indexes of `\X` escapes OUTSIDE character classes where X is a literal (non-alphanumeric) character."""
    out, i, in_class = [], 0, False
    while i < len(rx):
        c = rx[i]
        if c == "\\" and i + 1 < len(rx):
            if not in_class and not rx[i + 1].isalnum() and rx[i + 1] != "_":
                out.append(i)
            i += 2
            continue
        if c == "[" and not in_class:
            in_class = True
            if rx[i + 1:i + 2] == "^":
                i += 1
            if rx[i + 1:i + 2] == "]":          # a literal ']' first in the class
                i += 1
        elif c == "]" and in_class:
            in_class = False
        i += 1
    return out


def is_value_regex(rx: str) -> bool:
    r"""A value grader regex: it contains a digit and at least one escaped literal character (e.g. `\$?916\.99`)."""
    return bool(re.search(r"\d", rx)) and bool(_escaped_literal_positions(rx))


def regex_escaped_variant(rx: str) -> str:
    r"""`\$?916\.99` -> `(?:\\{0,2}\$)?916(?:\\{0,2}\.)99`: every escaped literal may be preceded by 0-2 backslashes."""
    pos = set(_escaped_literal_positions(rx))
    out, i = [], 0
    while i < len(rx):
        if i in pos:
            out.append("(?:\\\\{0,2}" + rx[i:i + 2] + ")")
            i += 2
            continue
        if rx[i] == "\\" and i + 1 < len(rx):
            out.append(rx[i:i + 2])
            i += 2
            continue
        out.append(rx[i])
        i += 1
    return "".join(out)


def value_tolerant_regex(rx: str) -> str:
    """The regex a value grader really uses: the literal OR its regex-escaped form (unchanged for other regexes)."""
    if not is_value_regex(rx):
        return rx
    m = _LEADING_FLAGS.match(rx)
    flags, body = (m.group(0), rx[m.end():]) if m else ("", rx)
    return f"{flags}(?:{body})|(?:{regex_escaped_variant(body)})"


def value_search(rx: str, text: str) -> tuple[bool, bool]:
    """(matched, matched only through the regex-escaped variant)."""
    if re.search(rx, text, re.MULTILINE):
        return True, False
    tol = value_tolerant_regex(rx)
    if tol != rx and re.search(tol, text, re.MULTILINE):
        return True, True
    return False, False
