"""Tests for verdict parsing, merging, and presentation mapping.

Split from test_ai_review.py (issue #1963). Covers get_verdict, merge_verdicts,
extract_verdict, and the verdict-to-presentation helpers (alert type, exit code,
emoji). Moved verbatim; behavior unchanged.
"""

from __future__ import annotations

import pytest

from scripts.ai_review_common import (
    get_verdict,
    get_verdict_alert_type,
    get_verdict_emoji,
    get_verdict_exit_code,
    merge_verdicts,
)

# ---------------------------------------------------------------------------
# Verdict parsing
# ---------------------------------------------------------------------------


class TestGetVerdict:
    def test_explicit_verdict_pass(self):
        assert get_verdict("Analysis complete. VERDICT: PASS. Good work!") == "PASS"

    def test_explicit_verdict_critical_fail(self):
        assert get_verdict("Found issues. VERDICT: CRITICAL_FAIL") == "CRITICAL_FAIL"

    def test_explicit_verdict_warn(self):
        assert get_verdict("Minor issues found. VERDICT: WARN") == "WARN"

    def test_explicit_verdict_rejected(self):
        assert get_verdict("Cannot approve. VERDICT: REJECTED") == "REJECTED"

    def test_keyword_critical_fail_severe(self):
        assert get_verdict("This has a severe issue that needs attention") == "CRITICAL_FAIL"

    def test_keyword_rejected_must_fix(self):
        assert get_verdict("You must fix this before merging") == "REJECTED"

    def test_keyword_rejected_blocking(self):
        assert get_verdict("This is a blocking issue") == "REJECTED"

    def test_keyword_pass_approved(self):
        assert get_verdict("Changes approved, good to merge") == "PASS"

    def test_keyword_pass_looks_good(self):
        assert get_verdict("Everything looks good to me") == "PASS"

    def test_keyword_pass_no_issues(self):
        assert get_verdict("I found no issues with this code") == "PASS"

    def test_keyword_warn_warning(self):
        assert get_verdict("There is a warning about potential issues") == "WARN"

    def test_keyword_warn_caution(self):
        assert get_verdict("Proceed with caution on this change") == "WARN"

    def test_empty_output(self):
        assert get_verdict("") == "CRITICAL_FAIL"

    def test_none_output(self):
        assert get_verdict("") == "CRITICAL_FAIL"

    def test_whitespace_only(self):
        assert get_verdict("   ") == "CRITICAL_FAIL"

    def test_unparseable_output(self):
        assert get_verdict("Some random text without any verdict keywords") == "CRITICAL_FAIL"

    def test_explicit_verdict_overrides_keyword(self):
        assert get_verdict("This looks good but VERDICT: CRITICAL_FAIL") == "CRITICAL_FAIL"


# ---------------------------------------------------------------------------
# Verdict aggregation
# ---------------------------------------------------------------------------


class TestMergeVerdicts:
    def test_all_pass(self):
        assert merge_verdicts(["PASS", "PASS", "PASS"]) == "PASS"

    def test_warn_with_pass(self):
        assert merge_verdicts(["PASS", "WARN", "PASS"]) == "WARN"

    def test_critical_fail_present(self):
        assert merge_verdicts(["PASS", "CRITICAL_FAIL", "PASS"]) == "CRITICAL_FAIL"

    def test_rejected_present(self):
        assert merge_verdicts(["PASS", "REJECTED", "WARN"]) == "CRITICAL_FAIL"

    def test_critical_over_warn(self):
        assert merge_verdicts(["WARN", "CRITICAL_FAIL", "WARN"]) == "CRITICAL_FAIL"

    def test_single_pass(self):
        assert merge_verdicts(["PASS"]) == "PASS"

    def test_single_critical_fail(self):
        assert merge_verdicts(["CRITICAL_FAIL"]) == "CRITICAL_FAIL"

    def test_fail_present(self):
        assert merge_verdicts(["PASS", "FAIL", "WARN"]) == "CRITICAL_FAIL"

    def test_empty_array(self):
        # REQ-008-05 (issue #1934): empty sequence returns UNKNOWN; the caller
        # cannot claim PASS when no axes were evaluated. Behavior changed from
        # PASS in PR #1934.
        assert merge_verdicts([]) == "UNKNOWN"

    def test_unknown_alone(self):
        assert merge_verdicts(["UNKNOWN"]) == "UNKNOWN"

    def test_unknown_with_pass(self):
        # UNKNOWN downgrades a would-be PASS: caller cannot claim PASS when
        # an axis failed to evaluate.
        assert merge_verdicts(["PASS", "UNKNOWN"]) == "UNKNOWN"

    def test_unknown_with_warn(self):
        # UNKNOWN does not override a real WARN finding.
        assert merge_verdicts(["WARN", "UNKNOWN"]) == "WARN"

    def test_unknown_with_critical(self):
        # UNKNOWN does not override CRITICAL_FAIL.
        assert merge_verdicts(["CRITICAL_FAIL", "UNKNOWN"]) == "CRITICAL_FAIL"

    def test_all_unknown(self):
        assert merge_verdicts(["UNKNOWN", "UNKNOWN", "UNKNOWN"]) == "UNKNOWN"

    def test_unrecognized_token_returns_unknown(self):
        # PR #1965 cluster J: previously unrecognized tokens silently fell
        # through to PASS, undermining the UNKNOWN safety mechanism.
        # Garbage input must produce UNKNOWN, never PASS.
        assert merge_verdicts(["FOOBAR"]) == "UNKNOWN"
        assert merge_verdicts(["pass"]) == "UNKNOWN"  # lowercase
        assert merge_verdicts(["Pass"]) == "UNKNOWN"  # mixed case
        assert merge_verdicts(["PASS", "FOOBAR"]) == "UNKNOWN"

    def test_unrecognized_does_not_override_critical(self):
        # CRITICAL_FAIL still wins over unrecognized tokens.
        assert merge_verdicts(["FOOBAR", "CRITICAL_FAIL"]) == "CRITICAL_FAIL"

    def test_unrecognized_does_not_override_warn(self):
        # WARN still wins over unrecognized tokens.
        assert merge_verdicts(["FOOBAR", "WARN"]) == "WARN"

    def test_compliant_treated_as_pass(self):
        # PR #1965 coderabbit Y14: COMPLIANT is a CI-valid token from the
        # spec-validation flow; merge as PASS-equivalent.
        assert merge_verdicts(["COMPLIANT"]) == "PASS"
        assert merge_verdicts(["PASS", "COMPLIANT"]) == "PASS"

    def test_non_compliant_treated_as_fail(self):
        # NON_COMPLIANT is in FAIL_VERDICTS now.
        assert merge_verdicts(["NON_COMPLIANT"]) == "CRITICAL_FAIL"
        assert merge_verdicts(["PASS", "NON_COMPLIANT"]) == "CRITICAL_FAIL"

    def test_partial_treated_as_warn(self):
        # PARTIAL is warn-equivalent (used by spec validation).
        assert merge_verdicts(["PARTIAL"]) == "WARN"
        assert merge_verdicts(["PASS", "PARTIAL"]) == "WARN"

    def test_fail_alone_returns_critical_fail(self):
        # FAIL is in FAIL_VERDICTS; must collapse to CRITICAL_FAIL.
        assert merge_verdicts(["FAIL"]) == "CRITICAL_FAIL"

    def test_needs_review_alone_returns_critical_fail(self):
        # NEEDS_REVIEW added in Issue #470: AI ambiguity treated as blocking.
        assert merge_verdicts(["NEEDS_REVIEW"]) == "CRITICAL_FAIL"

    def test_needs_review_with_pass(self):
        assert merge_verdicts(["PASS", "NEEDS_REVIEW", "PASS"]) == "CRITICAL_FAIL"


# Parametrized AC verification: every literal vector enumerated in REQ-008-05
# must match. PR #1965 critic Finding 2: spec contract had ACs without
# 1:1 verbatim test mapping.
_REQ_008_05_AC_VECTORS = [
    # AC enumerations from REQ-008-05 (in spec order):
    ([], "UNKNOWN"),
    (["UNKNOWN"], "UNKNOWN"),
    (["PASS"], "PASS"),
    (["PASS", "WARN"], "WARN"),
    (["PASS", "UNKNOWN"], "UNKNOWN"),
    (["WARN", "UNKNOWN"], "WARN"),
    (["PASS", "WARN", "CRITICAL_FAIL"], "CRITICAL_FAIL"),
    (["PASS", "FAIL"], "CRITICAL_FAIL"),
    (["PASS", "REJECTED"], "CRITICAL_FAIL"),
    (["UNKNOWN", "WARN"], "WARN"),
    (["CRITICAL_FAIL", "UNKNOWN"], "CRITICAL_FAIL"),
    (["UNKNOWN", "UNKNOWN"], "UNKNOWN"),
]


@pytest.mark.parametrize("verdicts,expected", _REQ_008_05_AC_VECTORS)
def test_req_008_05_literal_ac_vectors(verdicts, expected):
    """Every merge_verdicts AC vector enumerated in REQ-008-05 verifies.

    Adds 1:1 spec-text-to-test traceability per PR #1965 critic Finding 2.
    """
    from scripts.ai_review_common.verdict import merge_verdicts as _mv

    assert _mv(verdicts) == expected, (
        f"REQ-008-05 AC failed: merge_verdicts({verdicts}) "
        f"returned {_mv(verdicts)!r}, spec says {expected!r}"
    )


class TestExtractVerdict:
    def test_simple_verdict_line(self):
        from scripts.ai_review_common.verdict import extract_verdict

        assert extract_verdict("Verdict: PASS") == "PASS"

    def test_final_verdict_prefix(self):
        from scripts.ai_review_common.verdict import extract_verdict

        assert extract_verdict("Final verdict: WARN due to X") == "WARN"

    def test_uppercase_label(self):
        from scripts.ai_review_common.verdict import extract_verdict

        assert extract_verdict("VERDICT: CRITICAL_FAIL") == "CRITICAL_FAIL"

    def test_no_match_returns_unknown(self):
        from scripts.ai_review_common.verdict import extract_verdict

        assert extract_verdict("no verdict marker here") == "UNKNOWN"

    def test_empty_input(self):
        from scripts.ai_review_common.verdict import extract_verdict

        assert extract_verdict("") == "UNKNOWN"

    def test_whitespace_only(self):
        from scripts.ai_review_common.verdict import extract_verdict

        assert extract_verdict("   \n\t  ") == "UNKNOWN"

    def test_multiline_finds_marker(self):
        from scripts.ai_review_common.verdict import extract_verdict

        text = "## Findings\n\nSomething went wrong.\n\nVerdict: REJECTED\n\nMore text."
        assert extract_verdict(text) == "REJECTED"

    def test_indented_marker(self):
        from scripts.ai_review_common.verdict import extract_verdict

        assert extract_verdict("   Verdict: PASS") == "PASS"

    def test_invalid_token_returns_unknown(self):
        from scripts.ai_review_common.verdict import extract_verdict

        # Token not in the allowed set: pattern requires whole word boundary
        assert extract_verdict("Verdict: MAYBE") == "UNKNOWN"

    def test_last_match_wins(self):
        # PR #1965 coderabbit Y5: spec says "the response MUST contain a
        # final line matching..." so the LAST verdict marker is canonical.
        from scripts.ai_review_common.verdict import extract_verdict

        assert extract_verdict("Verdict: PASS\nVerdict: WARN") == "WARN"

    def test_extract_needs_review_token(self):
        # PR #1965 coderabbit Y7: NEEDS_REVIEW is in FAIL_VERDICTS but
        # was missing from the regex alternation; now included.
        from scripts.ai_review_common.verdict import extract_verdict

        assert extract_verdict("Verdict: NEEDS_REVIEW") == "NEEDS_REVIEW"
        assert extract_verdict("Final verdict: NEEDS_REVIEW") == "NEEDS_REVIEW"

    def test_extract_bracketed_verdict(self):
        # PR #1965 copilot AA1: CI action.yml accepts `VERDICT: [PASS]`
        # bracketed form (Issue #575 fix). extract_verdict was strict on
        # bare tokens which would mismatch.
        from scripts.ai_review_common.verdict import extract_verdict

        assert extract_verdict("Verdict: [PASS]") == "PASS"
        assert extract_verdict("Final verdict: [CRITICAL_FAIL]") == "CRITICAL_FAIL"
        assert extract_verdict("VERDICT: [WARN]") == "WARN"

    def test_lowercase_token_returns_unknown(self):
        # PR #1965 cluster A: global IGNORECASE caused `Verdict: pass` to match
        # PASS. Token is now case-sensitive uppercase; lowercase verdict text
        # is malformed and returns UNKNOWN.
        from scripts.ai_review_common.verdict import extract_verdict

        assert extract_verdict("Verdict: pass") == "UNKNOWN"
        assert extract_verdict("Verdict: warn") == "UNKNOWN"
        assert extract_verdict("Verdict: critical_fail") == "UNKNOWN"

    def test_mixed_case_token_returns_unknown(self):
        from scripts.ai_review_common.verdict import extract_verdict

        assert extract_verdict("Verdict: Pass") == "UNKNOWN"
        assert extract_verdict("Verdict: WaRn") == "UNKNOWN"

    def test_label_case_insensitive(self):
        # Label retains IGNORECASE: VERDICT, Verdict, verdict all match.
        from scripts.ai_review_common.verdict import extract_verdict

        assert extract_verdict("verdict: PASS") == "PASS"
        assert extract_verdict("VERDICT: WARN") == "WARN"
        assert extract_verdict("Verdict: CRITICAL_FAIL") == "CRITICAL_FAIL"
        assert extract_verdict("FINAL VERDICT: PASS") == "PASS"
        assert extract_verdict("final verdict: WARN") == "WARN"

    def test_fenced_code_block_does_not_override_final(self):
        # PR #1965 coderabbit Y5 (combined with cluster F): an example
        # verdict inside a fenced code block at the top of output cannot
        # override the real final verdict line at the bottom. Last-match
        # semantics make this safe regardless of whether the early example
        # is in a code block, prose, or anywhere else.
        from scripts.ai_review_common.verdict import extract_verdict

        text = "```text\nVerdict: PASS\n```\n\nReal output here.\n\nVerdict: WARN"
        assert extract_verdict(text) == "WARN"

    def test_template_alternation_rejected(self):
        # PR #1965 copilot 7k: axis prompts contain literal template lines
        # such as `VERDICT: [PASS|WARN|CRITICAL_FAIL]`. Without the trailing
        # `(?![|A-Z_])` lookahead the pattern matched `PASS` and silently
        # coerced a template echo to a real verdict. The lookahead rejects
        # any token followed by `|` (alternation marker).
        from scripts.ai_review_common.verdict import extract_verdict

        assert extract_verdict("VERDICT: [PASS|WARN|CRITICAL_FAIL]") == "UNKNOWN"
        assert extract_verdict("Verdict: PASS|WARN") == "UNKNOWN"
        assert extract_verdict("Final verdict: [PASS|WARN|CRITICAL_FAIL|REJECTED]") == "UNKNOWN"

    def test_template_then_real_verdict_finds_real(self):
        # An axis prompt may quote the template AND emit the real verdict
        # later. The template line is rejected; the real bare token wins.
        from scripts.ai_review_common.verdict import extract_verdict

        text = "Format: VERDICT: [PASS|WARN|CRITICAL_FAIL]\n\nFindings: ...\n\nVERDICT: WARN"
        assert extract_verdict(text) == "WARN"

    def test_token_prefix_collision_rejected(self):
        # The lookahead also rejects unknown uppercase tokens that share a
        # known token prefix (e.g., `PASS_THROUGH`, `WARN_LATER`). Without
        # `(?![|A-Z_])` the alternation would silently match the prefix and
        # drop the rest as `].?` trailing.
        from scripts.ai_review_common.verdict import extract_verdict

        assert extract_verdict("Verdict: PASS_THROUGH") == "UNKNOWN"
        assert extract_verdict("Verdict: WARN_LATER") == "UNKNOWN"


# ---------------------------------------------------------------------------
# Formatting: verdict alert type
# ---------------------------------------------------------------------------


class TestGetVerdictAlertType:
    def test_pass(self):
        assert get_verdict_alert_type("PASS") == "TIP"

    def test_compliant(self):
        assert get_verdict_alert_type("COMPLIANT") == "TIP"

    def test_warn(self):
        assert get_verdict_alert_type("WARN") == "WARNING"

    def test_partial(self):
        assert get_verdict_alert_type("PARTIAL") == "WARNING"

    def test_critical_fail(self):
        assert get_verdict_alert_type("CRITICAL_FAIL") == "CAUTION"

    def test_rejected(self):
        assert get_verdict_alert_type("REJECTED") == "CAUTION"

    def test_fail(self):
        assert get_verdict_alert_type("FAIL") == "CAUTION"

    def test_unknown(self):
        assert get_verdict_alert_type("SOMETHING_ELSE") == "NOTE"


# ---------------------------------------------------------------------------
# Formatting: verdict exit code
# ---------------------------------------------------------------------------


class TestGetVerdictExitCode:
    def test_pass_returns_0(self):
        assert get_verdict_exit_code("PASS") == 0

    def test_warn_returns_0(self):
        assert get_verdict_exit_code("WARN") == 0

    def test_critical_fail_returns_1(self):
        assert get_verdict_exit_code("CRITICAL_FAIL") == 1

    def test_rejected_returns_1(self):
        assert get_verdict_exit_code("REJECTED") == 1

    def test_fail_returns_1(self):
        assert get_verdict_exit_code("FAIL") == 1

    def test_unknown_returns_0(self):
        assert get_verdict_exit_code("UNKNOWN") == 0


# ---------------------------------------------------------------------------
# Formatting: verdict emoji
# ---------------------------------------------------------------------------


class TestGetVerdictEmoji:
    def test_pass(self):
        assert get_verdict_emoji("PASS") == "\u2705"

    def test_compliant(self):
        assert get_verdict_emoji("COMPLIANT") == "\u2705"

    def test_warn(self):
        assert get_verdict_emoji("WARN") == "\u26a0\ufe0f"

    def test_partial(self):
        assert get_verdict_emoji("PARTIAL") == "\u26a0\ufe0f"

    def test_critical_fail(self):
        assert get_verdict_emoji("CRITICAL_FAIL") == "\u274c"

    def test_rejected(self):
        assert get_verdict_emoji("REJECTED") == "\u274c"

    def test_fail(self):
        assert get_verdict_emoji("FAIL") == "\u274c"

    def test_unknown(self):
        assert get_verdict_emoji("UNKNOWN") == "\u2754"
