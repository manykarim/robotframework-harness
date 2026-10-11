"""Round-7 fix (d): value graders accept the regex-escaped form of the expected value (the `916\\.99` case)."""

from __future__ import annotations

import pytest
import value_graders as VG
from eval_helpers import posix_only

TOTAL = r"\$?916\.99"     # demoshop_order grader, verbatim from round 7


@pytest.mark.parametrize("text", [
    "Should Contain    ${summary}    $916.99",
    "Should Contain    ${summary}    916.99",
    r"Should Match Regexp    ${summary}    Total\s*\$916\.99",       # the recorded artifact
    r"Should Match Regexp    ${summary}    916\.99",
    r"Should Match Regexp    ${summary}    Total\s*\\$916\\.99",     # RF-escaped backslashes
])
def test_total_grader_accepts_plain_and_escaped_forms(text):
    ok, _ = VG.value_search(TOTAL, text)
    assert ok


@pytest.mark.parametrize("text", ["$916.98", "916x99", r"916\x99", "Total 91699", "$9.16"])
def test_total_grader_still_rejects_other_values(text):
    assert VG.value_search(TOTAL, text) == (False, False)


def test_escaped_match_is_reported():
    assert VG.value_search(TOTAL, "$916.99") == (True, False)
    assert VG.value_search(TOTAL, r"\$916\.99") == (True, True)


@pytest.mark.parametrize("rx,text", [
    (r"\$517\.00", r"Should Match Regexp    ${t}    \$517\.00"),
    (r"1,784\.00", r"1,784\.00"),
    (r"82\.400,00", r"Should Match Regexp    ${p}    82\.400,00 €"),
    (r"\b509(\.00)?\b", r"Should Match Regexp    ${p}    ^509\.00$"),
])
def test_every_value_grader_of_round7_accepts_its_escaped_form(rx, text):
    assert VG.is_value_regex(rx)
    assert VG.value_search(rx, text)[0]


@pytest.mark.parametrize("rx", [
    r"Library\s+Browser", r"(?i)sending e-mail success", r"\bab-[0-9a-f]{10}\b", r"ORD-", r"\b114\b",
    r"(?i)(Get Current Date|Add Time To Date|\bdatetime\b|timedelta|relativedelta|new Date\()",
    r"enterproductdata[^\n]*==\s+0\s*$", r"(?i)(total\D{0,20}\b8\b|\b8\b\D{0,20}total)",
])
def test_non_value_graders_are_unchanged(rx):
    assert not VG.is_value_regex(rx)
    assert VG.value_tolerant_regex(rx) == rx


def test_leading_inline_flags_are_kept_global():
    rx = VG.value_tolerant_regex(r"(?i)total\s+\$9\.50")
    assert rx.startswith("(?i)(?:")
    assert VG.value_search(r"(?i)total\s+\$9\.50", r"TOTAL  \$9\.50") == (True, True)


def test_escapes_inside_character_classes_are_not_touched():
    rx = r"[\$]916\.99"
    assert VG.regex_escaped_variant(rx).startswith(r"[\$]916")


@posix_only
def test_harness_grader_passes_a_regex_asserted_total(tmp_path):
    """End to end through harness._grade_one with the verbatim round-7 grader specs."""
    import harness as H

    sc = H.SCEN_BY_ID["demoshop_order"]
    grader = next(g for g in sc.graders if g.get("regex") == TOTAL)
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "shop_order.robot").write_text(
        "*** Test Cases ***\nOrder\n    ${summary}=    Get Text    css=.summary\n"
        "    Should Match Regexp    ${summary}    Total\\s*\\$916\\.99\n", encoding="utf-8")
    v = H._grade_one(grader, tmp_path, tmp_path / "grader_out", None)
    assert v["passed"] is True
    assert v.get("value_escaped_form") is True and "regex-escaped form" in v["detail"]

    debug = H.SCEN_BY_ID["demoshop_debug"]
    g2 = next(g for g in debug.graders if g.get("regex") == r"\$553\.19")
    (tmp_path / "tests" / "shop.robot").write_text(
        "*** Settings ***\nResource    ../resources/shop.resource\n*** Test Cases ***\nT\n    Check Total\n",
        encoding="utf-8")
    (tmp_path / "resources").mkdir()
    (tmp_path / "resources" / "shop.resource").write_text(
        "*** Keywords ***\nCheck Total\n    Should Match Regexp    ${t}    Total: \\$553\\.19\n", encoding="utf-8")
    v2 = H._grade_one(g2, tmp_path, tmp_path / "grader_out", None)
    assert v2["passed"] is True and v2.get("value_escaped_form") is True


@posix_only
def test_harness_grader_still_fails_a_wrong_total(tmp_path):
    import harness as H

    grader = next(g for g in H.SCEN_BY_ID["demoshop_order"].graders if g.get("regex") == TOTAL)
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "shop_order.robot").write_text("    Should Match Regexp    ${s}    \\$916\\.98\n")
    assert H._grade_one(grader, tmp_path, tmp_path / "g", None)["passed"] is False
