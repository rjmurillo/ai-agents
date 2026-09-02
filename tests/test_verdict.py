# taste-lint: ignore file-size
# Verdict parsing, local-axis adapters, and legacy helpers share one contract surface.
"""Tests for verdict parsing, merging, and presentation mapping.

Split from test_ai_review.py (issue #1963). Covers get_verdict, merge_verdicts,
extract_verdict, and the verdict-to-presentation helpers (alert type, exit code,
emoji). Moved verbatim; behavior unchanged.
"""

from __future__ import annotations

import json

import pytest

from scripts.ai_review_common import (
    adapt_local_axis_verdict,
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

    def test_did_not_run_with_pass(self):
        assert merge_verdicts(["PASS", "DID_NOT_RUN"]) == "UNKNOWN"

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
    (["PASS", "DID_NOT_RUN"], "UNKNOWN"),
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

    def test_extract_did_not_run_token(self):
        from scripts.ai_review_common.verdict import extract_verdict

        assert extract_verdict("Verdict: DID_NOT_RUN") == "DID_NOT_RUN"

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


def lint_payload(
    *,
    error_count: int = 0,
    warning_count: int = 0,
    files_scanned: int = 3,
    applicable_files: int = 3,
    files_by_category: dict[str, int] | None = None,
) -> str:
    """One golden-principles or taste-lints JSON payload.

    Carries the shape both scanners really emit, so a test cannot pass on a
    payload the adapter would refuse in production. `applicable_files` is
    golden-principles only; `files_by_category` is taste-lints only, and it is
    where a generated-only run shows up, because taste-lints counts a generated
    file into `files_scanned` and then skips it without running a rule.
    """
    if files_by_category is None:
        files_by_category = {"authored": files_scanned}
    return json.dumps(
        {
            "files_scanned": files_scanned,
            "applicable_files": applicable_files,
            "files_by_category": files_by_category,
            "error_count": error_count,
            "warning_count": warning_count,
        }
    )



def _scored(value: float = 8.0, confidence: float = 0.9) -> dict:
    return {"value": value, "confidence": confidence, "reasons": []}


def cq_file(path: str = "a.py", category: str = "authored", *, scored: bool = True) -> dict:
    """One assess.py `files` entry, carrying the five quality metrics.

    `_unreadable_assessment` keeps the real category while zeroing every
    confidence, so a test payload without the metrics cannot tell a scored file
    from one the scanner gave up on.
    """
    quality = _scored() if scored else _scored(10.0, 0.0)
    entry: dict[str, object] = {"path": path, "category": category}
    for field in ("cohesion", "coupling", "encapsulation", "testability", "non_redundancy"):
        entry[field] = dict(quality)
    return entry


def cq_payload(files: list[dict]) -> str:
    return json.dumps(
        {"files": files, "summary": {"file_count": len(files)}, "comparisons": []}
    )


class TestAdaptLocalAxisVerdict:
    def test_code_quality_pass_requires_an_assessed_file(self):
        payload = cq_payload([cq_file()])
        assert adapt_local_axis_verdict("code-qualities-assessment", payload, 0) == "PASS"

    @pytest.mark.parametrize("category", ["authored", "test"])
    def test_code_quality_pass_accepts_either_scored_category(self, category):
        payload = cq_payload([cq_file(category=category)])
        assert adapt_local_axis_verdict("code-qualities-assessment", payload, 0) == "PASS"

    def test_generated_only_assessment_is_not_a_pass(self):
        """assess.py returns an unscored assessment for a generated file.

        `classify_file_category` short-circuits to
        `_unscored_generated_assessment`, so the entry is counted but never
        scored. A diff of nothing but generated artifacts is a file list, not a
        review, and `/review` says generated artifacts create no local quality
        finding.
        """
        payload = cq_payload([cq_file("gen.ts", "generated", scored=False)])
        assert adapt_local_axis_verdict("code-qualities-assessment", payload, 0) == "UNKNOWN"

    def test_one_authored_file_beside_generated_ones_still_passes(self):
        """Negative control: the gate needs one scored file, not all of them."""
        payload = cq_payload(
            [cq_file("gen.ts", "generated", scored=False), cq_file()]
        )
        assert adapt_local_axis_verdict("code-qualities-assessment", payload, 0) == "PASS"

    def test_missing_category_field_stays_unknown(self):
        payload = '{"files": [{"path": "a.py"}], "summary": {"file_count": 1}, "comparisons": []}'
        assert adapt_local_axis_verdict("code-qualities-assessment", payload, 0) == "UNKNOWN"

    def test_code_quality_empty_assessment_is_unknown_not_pass(self):
        """A clean exit over zero files is silence, not a verdict.

        assess.py emits this shape in regression mode when the diff has no
        assessable head files, such as a deletion-only change.
        """
        payload = '{"files": [], "summary": {"file_count": 0}, "comparisons": []}'
        assert adapt_local_axis_verdict("code-qualities-assessment", payload, 0) == "UNKNOWN"

    def test_code_quality_file_count_disagreeing_with_files_is_unknown(self):
        """Two halves describing different runs are not evidence of a pass."""
        payload = '{"files": [], "summary": {"file_count": 2}, "comparisons": []}'
        assert adapt_local_axis_verdict("code-qualities-assessment", payload, 0) == "UNKNOWN"

    def test_code_quality_non_integer_file_count_is_unknown(self):
        payload = (
            '{"files": [{"path": "a.py"}], "summary": {"file_count": "1"},'
            ' "comparisons": []}'
        )
        assert adapt_local_axis_verdict("code-qualities-assessment", payload, 0) == "UNKNOWN"

    def test_code_quality_regressed_comparable_maps_to_fail(self):
        """SKILL.md:377 documents exit 10 as a gate failure that fails the PR."""
        payload = (
            '{"files": [{"path": "a.py"}], "summary": {"file_count": 1},'
            ' "comparisons": []}'
        )
        assert adapt_local_axis_verdict("code-qualities-assessment", payload, 10) == "FAIL"

    def test_code_quality_threshold_breach_maps_to_fail(self):
        """SKILL.md:378 documents exit 11 as a gate failure that fails the PR."""
        payload = '{"files": [], "summary": {"file_count": 1}, "comparisons": []}'
        assert adapt_local_axis_verdict("code-qualities-assessment", payload, 11) == "FAIL"

    def test_code_quality_malformed_json_shape_stays_unknown(self):
        payload = '{"files": null, "summary": null}'
        assert adapt_local_axis_verdict("code-qualities-assessment", payload, 0) == "UNKNOWN"

    def test_code_quality_invalid_json_stays_unknown(self):
        assert adapt_local_axis_verdict("code-qualities-assessment", "{", 0) == "UNKNOWN"

    @pytest.mark.parametrize(
        "axis",
        [
            "code-qualities-assessment",
            "doc-accuracy",
            "golden-principles",
            "taste-lints",
        ],
    )
    @pytest.mark.parametrize("output", ["", "   \n\t  "])
    def test_silent_stdout_stays_unknown(self, axis, output):
        """A skill that printed nothing reported nothing, on every axis.

        Empty or whitespace-only stdout is the shape a skill leaves when it
        dies before its first write, so a clean exit beside it is not evidence
        of a pass.
        """
        assert adapt_local_axis_verdict(axis, output, 0) == "UNKNOWN"

    def test_unscored_eligible_file_is_not_a_pass(self):
        """`_unreadable_assessment` keeps the category and zeroes confidence.

        Reading only the category let a file the scanner explicitly gave up on
        stand in as evidence of a review.
        """
        payload = cq_payload([cq_file(scored=False)])
        assert adapt_local_axis_verdict("code-qualities-assessment", payload, 0) == "UNKNOWN"

    def test_one_unscored_eligible_file_blocks_the_pass(self):
        """A hole in the evidence is not covered by a scored sibling.

        assess.py records a file that raised as all-unscored, so a partly
        failed run reaches here as a scored entry beside an unscored one.
        """
        payload = cq_payload([cq_file("a.py"), cq_file("b.py", scored=False)])
        assert adapt_local_axis_verdict("code-qualities-assessment", payload, 0) == "UNKNOWN"

    def test_unscored_generated_file_does_not_block_a_pass(self):
        """Negative control: generated entries are never scored by design."""
        payload = cq_payload([cq_file(), cq_file("gen.ts", "generated", scored=False)])
        assert adapt_local_axis_verdict("code-qualities-assessment", payload, 0) == "PASS"

    def test_one_scored_quality_is_enough(self):
        """Negative control: the gate needs evidence, not five metrics."""
        entry = cq_file(scored=False)
        entry["testability"] = _scored()
        payload = cq_payload([entry])
        assert adapt_local_axis_verdict("code-qualities-assessment", payload, 0) == "PASS"

    def test_boolean_confidence_is_not_a_score(self):
        entry = cq_file(scored=False)
        entry["cohesion"] = {"value": 8.0, "confidence": True, "reasons": []}
        payload = cq_payload([entry])
        assert adapt_local_axis_verdict("code-qualities-assessment", payload, 0) == "UNKNOWN"

    def test_non_mapping_quality_is_not_a_score(self):
        entry = cq_file(scored=False)
        entry["cohesion"] = "great"
        payload = cq_payload([entry])
        assert adapt_local_axis_verdict("code-qualities-assessment", payload, 0) == "UNKNOWN"

    def test_malformed_entry_beside_a_valid_one_stays_unknown(self):
        """A valid sibling must not carry an entry the adapter cannot read.

        Letting it through is the partial-evidence pass this gate exists to
        refuse, and the adapter contract says malformed output fails closed.
        """
        payload = cq_payload([cq_file(), "not-an-object"])
        assert adapt_local_axis_verdict("code-qualities-assessment", payload, 0) == "UNKNOWN"

    def test_unknown_category_beside_a_valid_one_stays_unknown(self):
        payload = cq_payload([cq_file(), cq_file("x.py", "vendored")])
        assert adapt_local_axis_verdict("code-qualities-assessment", payload, 0) == "UNKNOWN"

    def test_every_known_category_is_accepted(self):
        """Negative control: the three labels assess.py emits all parse."""
        payload = cq_payload(
            [cq_file("a.py"), cq_file("b.py", "test"), cq_file("g.ts", "generated", scored=False)]
        )
        assert adapt_local_axis_verdict("code-qualities-assessment", payload, 0) == "PASS"

    def test_code_quality_unexpected_exit_stays_unknown(self):
        payload = '{"files": [], "summary": {"file_count": 0}, "comparisons": []}'
        assert adapt_local_axis_verdict("code-qualities-assessment", payload, 3) == "UNKNOWN"

    def test_doc_accuracy_json_pass_maps_to_pass(self):
        payload = (
            '{"gate_result": {"verdict": "PASS"},'
            ' "assessment": {"documentation_files": [{"path": "README.md"}]}}'
        )
        assert adapt_local_axis_verdict("doc-accuracy", payload, 0) == "PASS"

    def test_doc_accuracy_partial_inventory_is_unknown(self):
        """A changed Markdown file the walk pruned is not covered by its peers.

        `changed_files` names both; `documentation_files` holds only the one
        that survived EXCLUDE_DIRS, and check_gate still reports PASS.
        """
        payload = json.dumps(
            {
                "gate_result": {"verdict": "PASS"},
                "assessment": {
                    "documentation_files": [{"path": "docs/guide.md"}],
                    "changed_files": ["docs/guide.md", "build/notes.md"],
                },
            }
        )
        assert adapt_local_axis_verdict("doc-accuracy", payload, 0) == "UNKNOWN"

    def test_doc_accuracy_complete_inventory_passes(self):
        """Negative control: every changed document accounted for."""
        payload = json.dumps(
            {
                "gate_result": {"verdict": "PASS"},
                "assessment": {
                    "documentation_files": [{"path": "docs/guide.md"}],
                    "changed_files": ["docs/guide.md", "src/app.py"],
                },
            }
        )
        assert adapt_local_axis_verdict("doc-accuracy", payload, 0) == "PASS"

    def test_doc_accuracy_without_a_diff_scope_needs_no_completeness(self):
        """`changed_files` is null on a full-repo run, so there is no set to
        be complete against."""
        payload = json.dumps(
            {
                "gate_result": {"verdict": "PASS"},
                "assessment": {
                    "documentation_files": [{"path": "README.md"}],
                    "changed_files": None,
                },
            }
        )
        assert adapt_local_axis_verdict("doc-accuracy", payload, 0) == "PASS"

    def test_doc_accuracy_pass_over_zero_documents_is_unknown(self):
        """check_gate passes when no claim contradicts the code.

        A run that inventoried nothing has no claims, so its PASS says only
        that it found no docs. A deletion-only Markdown diff, or one under an
        EXCLUDE_DIRS path, reaches that state without opening a changed file.
        """
        payload = (
            '{"gate_result": {"verdict": "PASS"},'
            ' "assessment": {"documentation_files": []}}'
        )
        assert adapt_local_axis_verdict("doc-accuracy", payload, 0) == "UNKNOWN"

    def test_doc_accuracy_pass_without_an_assessment_block_is_unknown(self):
        payload = '{"gate_result": {"verdict": "PASS"}}'
        assert adapt_local_axis_verdict("doc-accuracy", payload, 0) == "UNKNOWN"

    def test_doc_accuracy_summary_pass_is_unknown(self):
        """Summary mode prints no examined-file count, so it cannot prove a PASS.

        It can still report a FAIL, which needs no such evidence.
        """
        output = "--- Documentation Accuracy Summary ---\nGate: PASS (threshold: high)\n"
        assert adapt_local_axis_verdict("doc-accuracy", output, 0) == "UNKNOWN"

    def test_doc_accuracy_summary_fail_maps_to_fail(self):
        output = "--- Documentation Accuracy Summary ---\nGate: FAIL (threshold: high)\n"
        assert adapt_local_axis_verdict("doc-accuracy", output, 10) == "FAIL"

    def test_doc_accuracy_did_not_run_maps_to_unknown(self):
        payload = '{"gate_result": {"verdict": "DID_NOT_RUN"}}'
        assert adapt_local_axis_verdict("doc-accuracy", payload, 1) == "UNKNOWN"

    def test_doc_accuracy_non_object_json_stays_unknown(self):
        assert adapt_local_axis_verdict("doc-accuracy", "[]", 0) == "UNKNOWN"

    def test_doc_accuracy_non_mapping_gate_result_stays_unknown(self):
        payload = '{"gate_result": []}'
        assert adapt_local_axis_verdict("doc-accuracy", payload, 0) == "UNKNOWN"

    @pytest.mark.parametrize("axis", ["golden-principles", "taste-lints"])
    def test_local_lint_error_maps_to_fail(self, axis):
        payload = lint_payload(error_count=1)
        assert adapt_local_axis_verdict(axis, payload, 10) == "FAIL"

    @pytest.mark.parametrize("axis", ["golden-principles", "taste-lints"])
    def test_local_lint_warning_maps_to_warn(self, axis):
        payload = lint_payload(warning_count=1)
        assert adapt_local_axis_verdict(axis, payload, 0) == "WARN"

    @pytest.mark.parametrize("axis", ["golden-principles", "taste-lints"])
    def test_local_lint_clean_maps_to_pass(self, axis):
        payload = lint_payload()
        assert adapt_local_axis_verdict(axis, payload, 0) == "PASS"

    @pytest.mark.parametrize("axis", ["golden-principles", "taste-lints"])
    def test_scanning_nothing_is_not_a_pass(self, axis):
        """A deletion-only diff exits 0 with every count at zero.

        Both scanners take their file list from a diff, which names deleted
        paths, then skip anything that is no longer a file before incrementing
        `files_scanned`. Reading only the counts called that silence a PASS.
        """
        payload = lint_payload(files_scanned=0, applicable_files=0)
        assert adapt_local_axis_verdict(axis, payload, 0) == "UNKNOWN"

    @pytest.mark.parametrize("axis", ["golden-principles", "taste-lints"])
    def test_missing_files_scanned_stays_unknown(self, axis):
        """No `files_scanned` field is output the adapter cannot vouch for."""
        payload = '{"error_count": 0, "warning_count": 0}'
        assert adapt_local_axis_verdict(axis, payload, 0) == "UNKNOWN"

    def test_golden_principles_needs_an_applicable_file(self):
        """Opening files a GP rule does not govern is not a reviewed design.

        Its axis note says a clean result on a non-toolkit repo "means no rule
        applied, not that design was reviewed".
        """
        payload = lint_payload(files_scanned=9, applicable_files=0)
        assert adapt_local_axis_verdict("golden-principles", payload, 0) == "UNKNOWN"

    def test_taste_lints_has_no_applicable_files_gate(self):
        """Negative control: the extra gate is golden-principles only.

        taste-lints emits no `applicable_files`, so gating both axes on it
        would make every taste-lints run UNKNOWN.
        """
        payload = json.dumps(
            {
                "files_scanned": 9,
                "files_by_category": {"authored": 9},
                "error_count": 0,
                "warning_count": 0,
            }
        )
        assert adapt_local_axis_verdict("taste-lints", payload, 0) == "PASS"

    @pytest.mark.parametrize("axis", ["golden-principles", "taste-lints"])
    def test_bool_counts_stay_unknown(self, axis):
        payload = '{"error_count": false, "warning_count": 0}'
        assert adapt_local_axis_verdict(axis, payload, 0) == "UNKNOWN"

    @pytest.mark.parametrize("axis", ["golden-principles", "taste-lints"])
    def test_missing_lint_counts_stay_unknown(self, axis):
        payload = '{"error_count": 0}'
        assert adapt_local_axis_verdict(axis, payload, 0) == "UNKNOWN"

    @pytest.mark.parametrize("axis", ["golden-principles", "taste-lints"])
    @pytest.mark.parametrize("exit_code", [1, 2, 127])
    def test_lint_undefined_exit_status_stays_unknown(self, axis, exit_code):
        """Only 0 and 10 are defined; every other status is a crashed run.

        Exit 1 is the documented script error. The counts a dying scanner
        printed are not a verdict, so the status is read before them.
        """
        payload = '{"error_count": 0, "warning_count": 0}'
        assert adapt_local_axis_verdict(axis, payload, exit_code) == "UNKNOWN"

    @pytest.mark.parametrize("axis", ["golden-principles", "taste-lints"])
    def test_lint_script_error_does_not_downgrade_to_warn(self, axis):
        """A crashed scan carrying warnings is UNKNOWN, never an ack-able WARN.

        Reading warning_count before the status let exit 1 report WARN, which
        made a failed scan mergeable on an acknowledgement.
        """
        payload = '{"error_count": 0, "warning_count": 3}'
        assert adapt_local_axis_verdict(axis, payload, 1) == "UNKNOWN"

    @pytest.mark.parametrize("axis", ["golden-principles", "taste-lints"])
    def test_lint_errors_under_undefined_exit_do_not_report_fail(self, axis):
        """An error payload under an undefined status is UNKNOWN, not FAIL.

        FAIL is a claim the scanner ran and found violations. Exit 3 says it
        did not run the way the contract describes.
        """
        payload = '{"error_count": 4, "warning_count": 0}'
        assert adapt_local_axis_verdict(axis, payload, 3) == "UNKNOWN"

    @pytest.mark.parametrize("axis", ["golden-principles", "taste-lints"])
    def test_lint_violations_exit_without_errors_stays_unknown(self, axis):
        """Exit 10 with no errors contradicts the scanner's own gate.

        Both scanners return EXIT_VIOLATIONS from `error_count > 0` alone
        (scan_principles.py:455-457, taste_lints.py:1122-1124), so this pair
        cannot come from one run.
        """
        payload = lint_payload(warning_count=2)
        assert adapt_local_axis_verdict(axis, payload, 10) == "UNKNOWN"

    @pytest.mark.parametrize("axis", ["golden-principles", "taste-lints"])
    def test_lint_errors_under_clean_exit_stays_unknown(self, axis):
        """The mirror contradiction: errors reported under exit 0."""
        payload = lint_payload(error_count=1)
        assert adapt_local_axis_verdict(axis, payload, 0) == "UNKNOWN"

    def test_taste_lints_generated_only_scan_is_not_a_pass(self):
        """taste-lints counts a generated file then skips it without linting.

        `run_lint` does `result.files_scanned += 1` inside the
        `_generated_by_path` branch and then continues, so files_scanned alone
        cannot separate a linted run from a skipped one. A generated-only diff,
        such as a changed shipped mirror, reached PASS with no rule run.
        """
        payload = lint_payload(files_by_category={"generated": 3})
        assert adapt_local_axis_verdict("taste-lints", payload, 0) == "UNKNOWN"

    def test_taste_lints_generated_beside_authored_still_passes(self):
        """Negative control: one linted file is enough."""
        payload = lint_payload(files_by_category={"generated": 2, "authored": 1})
        assert adapt_local_axis_verdict("taste-lints", payload, 0) == "PASS"

    def test_taste_lints_test_category_counts_as_linted(self):
        payload = lint_payload(files_by_category={"test": 2})
        assert adapt_local_axis_verdict("taste-lints", payload, 0) == "PASS"

    def test_taste_lints_missing_category_map_stays_unknown(self):
        payload = json.dumps(
            {"files_scanned": 3, "error_count": 0, "warning_count": 0}
        )
        assert adapt_local_axis_verdict("taste-lints", payload, 0) == "UNKNOWN"

    def test_golden_principles_needs_no_category_map(self):
        """Negative control: the category gate is taste-lints only.

        golden-principles emits applicable_files instead and no
        files_by_category, so gating both axes on it would make every
        golden-principles run UNKNOWN.
        """
        payload = json.dumps(
            {
                "files_scanned": 3,
                "applicable_files": 2,
                "error_count": 0,
                "warning_count": 0,
            }
        )
        assert adapt_local_axis_verdict("golden-principles", payload, 0) == "PASS"

    def test_malformed_output_stays_unknown(self):
        assert adapt_local_axis_verdict("taste-lints", "not json", 0) == "UNKNOWN"

    def test_unknown_axis_raises_value_error(self):
        with pytest.raises(ValueError):
            adapt_local_axis_verdict("invented-axis", "{}", 0)


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

    def test_did_not_run(self):
        assert get_verdict_emoji("DID_NOT_RUN") == "\u2754"
