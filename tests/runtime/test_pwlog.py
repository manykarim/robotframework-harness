"""Playwright call-log classification (rf_harness.runtime.pwlog): the evidence behind every live verdict."""

from __future__ import annotations

import pytest

from rf_harness.runtime import pwlog

HEAD = "TimeoutError: locator.click: Timeout 2500ms exceeded.\nCall log:\n  - waiting for locator('id=target')\n"
RESOLVED = "    - locator resolved to <input id=\"target\" type=\"radio\"/>\n"


@pytest.mark.parametrize(("tail", "cls"), [
    ("", "absent"),
    (RESOLVED + "  - attempting click action\n    - <span class=\"ideal-radio\"></span> intercepts pointer events\n",
     "covered"),
    (RESOLVED + "    - element is not visible\n", "hidden"),
    (RESOLVED + "    - element is not enabled\n", "disabled"),
    (RESOLVED + "    - element is not stable\n", "animating"),
    (RESOLVED + "    - element is not attached to the DOM\n", "detached"),
    (RESOLVED + "  - did not find some options\n", "nooption"),
    (RESOLVED + "  - attempting click action\n  - some other reason\n", "present"),
])
def test_classify(tail, cls):
    res = pwlog.classify(HEAD + tail)
    assert res["cls"] == cls, res
    assert res["selector"] == "id=target"


def test_covered_keeps_the_intercepting_fragment_verbatim():
    res = pwlog.classify(HEAD + RESOLVED + "    - <span class=\"ideal-radio\"></span> intercepts pointer events\n")
    assert res["evidence"] == '<span class="ideal-radio"></span> intercepts pointer events'
    assert res["resolved"].startswith("<input")


def test_strict_mode_is_ambiguous():
    res = pwlog.classify("Error: strict mode violation: locator('button') resolved to 3 elements:\n  1) ...")
    assert (res["cls"], res["count"]) == ("ambiguous", 3)


def test_non_playwright_messages_have_no_class():
    assert pwlog.classify("Variable '${x}' not found.")["cls"] == ""
    assert pwlog.classify(None)["cls"] == ""


@pytest.mark.parametrize(("msg", "expected"), [
    ("Text 'Total: 40.00 EUR' (str) should be 'Total: 99.00 EUR' (str)",
     {"what": "Text", "actual": "Total: 40.00 EUR", "op": "should be", "expected": "Total: 99.00 EUR"}),
    ("one != two", {"what": "value", "actual": "one", "op": "!=", "expected": "two"}),
    ("'Order ORD-1 confirmed' does not contain 'Done'",
     {"what": "value", "actual": "Order ORD-1 confirmed", "op": "should contain", "expected": "Done"}),
])
def test_actual_expected(msg, expected):
    assert pwlog.actual_expected(msg) == expected


def test_actual_expected_ignores_other_failures():
    assert pwlog.actual_expected(HEAD) is None
