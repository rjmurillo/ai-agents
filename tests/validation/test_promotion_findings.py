"""Findings, the four classes, and the previous-manifest baseline.

ADR-113 decisions 8 and 9, issue #5636. The state-to-finding table and the
class rules each get a case that proves the line between two classes.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

import pytest

from scripts.validation.evidence import CheckOutcome, EvidenceState
from scripts.validation.promotion_evidence import (
    REASON_MALFORMED,
    REASON_REVISION_MISMATCH,
    REASON_UNREADABLE,
    Candidate,
    EvidenceRecord,
    RejectedEvidence,
)
from scripts.validation.promotion_exceptions import PromotionException, parse_exceptions
from scripts.validation.promotion_findings import (
    MAX_MANIFEST_BYTES,
    REASON_MISSING,
    ClassifiedFinding,
    Finding,
    FindingClass,
    ManifestError,
    PreviousFinding,
    blocks_promotion,
    classify_findings,
    collect_findings,
    counts,
    findings_for,
    is_finding,
    load_previous_manifest,
    missing_outcomes,
    overall_state,
    parse_previous_manifest,
    passed_scopes,
    remediated_findings,
    unreadable_outcomes,
)

SHA = "a" * 40
PREV_SHA = "b" * 40
TODAY = date(2026, 10, 1)


def _approve(_record: PromotionException) -> bool:
    return True


def _deny(_record: PromotionException) -> bool:
    return False


def _fail(validator: str = "pytest", scope: str = "tests/", **kw: Any) -> CheckOutcome:
    return CheckOutcome.failed(validator, reason="tests.failed", scope=scope, **kw)


def _finding(item: str = "", validator: str = "pytest") -> Finding:
    return Finding(validator, "tests.failed", "tests/", item, EvidenceState.FAIL)


def _exception(item: str = "", **overrides: Any) -> PromotionException:
    entry: dict[str, Any] = {
        "validator": "pytest",
        "reason": "tests.failed",
        "scope": "tests/",
        "rationale": "Tracked flaky test.",
        "owner": "rjmurillo",
        "approval": {"pr": 1, "reviewer": "second"},
        "expires": "2026-12-31",
        "remediate_by": "2026-11-30",
    }
    if item:
        entry["item"] = item
    entry.update(overrides)
    return parse_exceptions({"schema_version": "1", "entries": [entry]})[0]


class TestIsFinding:
    def test_pass_is_not_a_finding(self) -> None:
        passed = CheckOutcome.passed("v", revision=SHA, scope="s")
        assert not is_finding(passed)

    def test_policy_exempt_skip_is_not_a_finding(self) -> None:
        assert not is_finding(CheckOutcome.skipped("v", reason="policy.exempt", scope="s"))

    def test_other_skip_is_a_finding(self) -> None:
        assert is_finding(CheckOutcome.skipped("v", reason="policy.quick_mode", scope="s"))

    @pytest.mark.parametrize("maker", ["failed", "blocked", "unknown"])
    def test_fail_blocked_unknown_are_findings(self, maker: str) -> None:
        outcome = getattr(CheckOutcome, maker)("v", reason="x.y", scope="s")
        assert is_finding(outcome)


class TestFindingsFor:
    def test_one_finding_without_items(self) -> None:
        found = findings_for(EvidenceRecord(_fail()))
        assert [f.item for f in found] == [""]

    def test_one_finding_per_item(self) -> None:
        found = findings_for(EvidenceRecord(_fail(), items=("a.py", "b.py")))
        assert [f.item for f in found] == ["a.py", "b.py"]
        assert len({f.fingerprint for f in found}) == 2

    def test_pass_yields_nothing(self) -> None:
        passed = CheckOutcome.passed("v", revision=SHA, scope="s")
        assert findings_for(EvidenceRecord(passed)) == ()


class TestMissingAndUnreadable:
    def test_required_validator_with_no_record_is_unknown(self) -> None:
        present = EvidenceRecord(CheckOutcome.passed("a", revision=SHA, scope="s", examined=1))
        out = missing_outcomes(["a", "b"], [present], Candidate(SHA))
        assert [o.validator for o in out] == ["b"]
        assert out[0].state is EvidenceState.UNKNOWN
        assert out[0].reason == REASON_MISSING

    def test_nothing_missing_when_all_present(self) -> None:
        present = EvidenceRecord(CheckOutcome.passed("a", revision=SHA, scope="s", examined=1))
        assert missing_outcomes(["a"], [present], Candidate(SHA)) == ()

    def test_unrequired_validators_are_not_missing(self) -> None:
        assert missing_outcomes([], [], Candidate(SHA)) == ()

    def test_malformed_and_unreadable_files_become_unknown(self) -> None:
        rejected = [
            RejectedEvidence("a.json", "pytest", REASON_MALFORMED),
            RejectedEvidence("b.json", "", REASON_UNREADABLE),
        ]
        out = unreadable_outcomes(rejected)
        assert [o.validator for o in out] == ["pytest", "evidence"]
        assert all(o.state is EvidenceState.UNKNOWN for o in out)

    def test_binding_rejection_alone_is_not_unreadable(self) -> None:
        rejected = [RejectedEvidence("a.json", "pytest", REASON_REVISION_MISMATCH)]
        assert unreadable_outcomes(rejected) == ()

    def test_collect_includes_synthesized_outcomes(self) -> None:
        unknown = CheckOutcome.unknown("b", reason=REASON_MISSING, scope="s")
        found = collect_findings([EvidenceRecord(_fail())], [unknown])
        assert {f.validator for f in found} == {"pytest", "b"}


class TestClassify:
    def test_no_exception_is_unresolved(self) -> None:
        (item,) = classify_findings([_finding()], [], TODAY, _approve)
        assert item.finding_class is FindingClass.UNRESOLVED
        assert item.exception is None

    def test_active_exception_is_accepted(self) -> None:
        (item,) = classify_findings([_finding()], [_exception()], TODAY, _approve)
        assert item.finding_class is FindingClass.ACCEPTED
        assert item.exception is not None

    def test_lapsed_exception_is_expired(self) -> None:
        lapsed = _exception(expires="2026-09-30", remediate_by="2026-09-30")
        (item,) = classify_findings([_finding()], [lapsed], TODAY, _approve)
        assert item.finding_class is FindingClass.EXPIRED

    def test_unproven_approval_is_unresolved_not_accepted(self) -> None:
        (item,) = classify_findings([_finding()], [_exception()], TODAY, _deny)
        assert item.finding_class is FindingClass.UNRESOLVED
        assert "unapproved" in item.note

    def test_overdue_remediation_is_unresolved(self) -> None:
        overdue = _exception(remediate_by="2026-09-30")
        (item,) = classify_findings([_finding()], [overdue], TODAY, _approve)
        assert item.finding_class is FindingClass.UNRESOLVED
        assert "remediation_overdue" in item.note

    def test_exception_covers_only_its_own_item(self) -> None:
        covered = _finding("a.py")
        other = _finding("b.py")
        result = classify_findings([covered, other], [_exception("a.py")], TODAY, _approve)
        assert [c.finding_class for c in result] == [FindingClass.ACCEPTED, FindingClass.UNRESOLVED]

    def test_whole_scope_exception_does_not_cover_an_item_finding(self) -> None:
        (item,) = classify_findings([_finding("a.py")], [_exception()], TODAY, _approve)
        assert item.finding_class is FindingClass.UNRESOLVED

    def test_to_dict_carries_class_and_exception(self) -> None:
        (item,) = classify_findings([_finding()], [_exception()], TODAY, _approve)
        data = item.to_dict()
        assert data["class"] == "accepted"
        assert data["exception"]["owner"] == "rjmurillo"
        assert data["fingerprint"] == _finding().fingerprint

    def test_to_dict_without_exception(self) -> None:
        assert ClassifiedFinding(_finding(), FindingClass.UNRESOLVED).to_dict()["exception"] is None


class TestCountsAndVerdict:
    def _tally(self, *classes: FindingClass, remediated: int = 0) -> dict[str, int]:
        items = [ClassifiedFinding(_finding(str(i)), c) for i, c in enumerate(classes)]
        return counts(items, remediated)

    def test_every_class_is_present_at_zero(self) -> None:
        assert self._tally() == {"remediated": 0, "accepted": 0, "expired": 0, "unresolved": 0}

    def test_counts_each_class(self) -> None:
        tally = self._tally(FindingClass.ACCEPTED, FindingClass.UNRESOLVED, remediated=2)
        assert tally == {"remediated": 2, "accepted": 1, "expired": 0, "unresolved": 1}

    def test_unresolved_blocks(self) -> None:
        assert blocks_promotion(self._tally(FindingClass.UNRESOLVED))

    def test_expired_blocks(self) -> None:
        assert blocks_promotion(self._tally(FindingClass.EXPIRED))

    def test_accepted_and_remediated_do_not_block(self) -> None:
        assert not blocks_promotion(self._tally(FindingClass.ACCEPTED, remediated=3))

    def test_empty_outcomes_aggregate_to_unknown(self) -> None:
        assert overall_state([]).state is EvidenceState.UNKNOWN

    def test_worst_state_wins(self) -> None:
        outcomes = [CheckOutcome.passed("a", revision=SHA, scope="s"), _fail()]
        assert overall_state(outcomes).state is EvidenceState.FAIL


def _manifest(**overrides: Any) -> dict[str, Any]:
    doc: dict[str, Any] = {
        "schema_version": "1",
        "candidate": {"sha": PREV_SHA, "digest": ""},
        "findings": [
            {
                "fingerprint": "f1",
                "class": "unresolved",
                "validator": "pytest",
                "reason": "tests.failed",
                "scope": "tests/",
                "item": "",
            },
            {
                "fingerprint": "f2",
                "class": "remediated",
                "validator": "x",
                "reason": "y.z",
                "scope": "s",
                "item": "",
            },
        ],
    }
    doc.update(overrides)
    return doc


class TestPreviousManifest:
    def test_keeps_open_findings_and_drops_remediated(self) -> None:
        parsed = parse_previous_manifest(_manifest())
        assert parsed.candidate_sha == PREV_SHA
        assert [f.fingerprint for f in parsed.findings] == ["f1"]

    @pytest.mark.parametrize("document", [[], "x", None, {"schema_version": "2"}])
    def test_wrong_document_is_refused(self, document: Any) -> None:
        with pytest.raises(ManifestError, match="schema"):
            parse_previous_manifest(document)

    @pytest.mark.parametrize("candidate", [None, {}, {"sha": "abc"}, {"sha": 5}, "x"])
    def test_candidate_sha_is_required(self, candidate: Any) -> None:
        with pytest.raises(ManifestError, match="candidate.sha"):
            parse_previous_manifest(_manifest(candidate=candidate))

    def test_findings_must_be_a_list(self) -> None:
        with pytest.raises(ManifestError, match="list"):
            parse_previous_manifest(_manifest(findings={}))

    @pytest.mark.parametrize(
        "raw",
        [{"class": "unresolved", "fingerprint": "f"}, {"class": "unresolved", "fingerprint": 1}],
    )
    def test_a_partial_open_finding_is_refused(self, raw: Any) -> None:
        with pytest.raises(ManifestError, match="string"):
            parse_previous_manifest(_manifest(findings=[raw]))

    @pytest.mark.parametrize("raw", ["x", 5, None, ["a"]])
    def test_a_non_object_entry_is_refused_not_skipped(self, raw: Any) -> None:
        with pytest.raises(ManifestError, match="JSON object"):
            parse_previous_manifest(_manifest(findings=[raw]))

    @pytest.mark.parametrize("klass", [None, "", "open", 5])
    def test_an_entry_without_a_known_class_is_refused(self, klass: Any) -> None:
        raw = {"fingerprint": "f", "validator": "v", "reason": "r.x", "scope": "s", "item": ""}
        raw["class"] = klass
        with pytest.raises(ManifestError, match="class"):
            parse_previous_manifest(_manifest(findings=[raw]))

    def test_load_reads_a_file(self, tmp_path: Path) -> None:
        path = tmp_path / "m.json"
        path.write_text(json.dumps(_manifest()), encoding="utf-8")
        assert load_previous_manifest(path).candidate_sha == PREV_SHA

    def test_load_refuses_bad_json(self, tmp_path: Path) -> None:
        path = tmp_path / "m.json"
        path.write_text("{nope", encoding="utf-8")
        with pytest.raises(ManifestError, match="not valid JSON"):
            load_previous_manifest(path)

    def test_load_refuses_nan(self, tmp_path: Path) -> None:
        path = tmp_path / "m.json"
        path.write_text('{"schema_version": "1", "x": NaN}', encoding="utf-8")
        with pytest.raises(ManifestError, match="not valid JSON"):
            load_previous_manifest(path)

    def test_load_refuses_a_huge_file(self, tmp_path: Path) -> None:
        path = tmp_path / "m.json"
        path.write_bytes(b" " * (MAX_MANIFEST_BYTES + 1))
        with pytest.raises(ManifestError, match="larger"):
            load_previous_manifest(path)

    def test_load_missing_file_raises_oserror(self, tmp_path: Path) -> None:
        with pytest.raises(OSError):
            load_previous_manifest(tmp_path / "absent.json")


class TestRemediated:
    def _prev(self, fingerprint: str, scope: str = "s") -> PreviousFinding:
        return PreviousFinding(fingerprint, "v", "r.x", scope, "")

    def _passed(self) -> frozenset[tuple[str, str]]:
        return frozenset({("v", "s")})

    def test_previous_finding_gone_and_revalidated_is_remediated(self) -> None:
        gone = remediated_findings([self._prev("old")], [_finding()], self._passed())
        assert [item.fingerprint for item in gone] == ["old"]

    def test_previous_finding_still_present_is_not_remediated(self) -> None:
        still = self._prev(_finding().fingerprint)
        assert remediated_findings([still], [_finding()], self._passed()) == ()

    def test_no_previous_means_nothing_remediated(self) -> None:
        assert remediated_findings([], [_finding()], self._passed()) == ()

    def test_a_validator_that_did_not_re_run_is_not_remediated(self) -> None:
        assert remediated_findings([self._prev("old")], [], frozenset()) == ()

    def test_a_pass_on_another_scope_is_not_remediation(self) -> None:
        other = frozenset({("v", "elsewhere")})
        assert remediated_findings([self._prev("old")], [], other) == ()

    @pytest.mark.parametrize("examined", [0, None])
    def test_a_pass_that_examined_nothing_does_not_prove_remediation(
        self, examined: int | None
    ) -> None:
        empty = EvidenceRecord(CheckOutcome.passed("v", revision=SHA, scope="s", examined=examined))
        assert passed_scopes([empty]) == frozenset()

    def test_passed_scopes_lists_only_pass_records(self) -> None:
        ok = EvidenceRecord(CheckOutcome.passed("a", revision=SHA, scope="x", examined=2))
        bad = EvidenceRecord(_fail("b", "y"))
        assert passed_scopes([ok, bad]) == frozenset({("a", "x")})


class TestExemptDoesNotSatisfy:
    def test_a_lone_exempt_skip_leaves_a_required_validator_missing(self) -> None:
        exempt = EvidenceRecord(CheckOutcome.skipped("a", reason="policy.exempt", scope="s"))
        out = missing_outcomes(["a"], [exempt], Candidate(SHA))
        assert [o.validator for o in out] == ["a"]

    def test_a_failing_validator_is_present_not_also_missing(self) -> None:
        failing = EvidenceRecord(_fail("a"))
        assert missing_outcomes(["a"], [failing], Candidate(SHA)) == ()


class TestPassThatExaminedNothing:
    @pytest.mark.parametrize("examined", [0, None])
    def test_a_pass_with_no_examined_count_leaves_the_validator_missing(
        self, examined: int | None
    ) -> None:
        empty = EvidenceRecord(CheckOutcome.passed("a", revision=SHA, scope="s", examined=examined))
        out = missing_outcomes(["a"], [empty], Candidate(SHA))
        assert [o.validator for o in out] == ["a"]

    def test_a_pass_that_examined_something_is_present(self) -> None:
        ok = EvidenceRecord(CheckOutcome.passed("a", revision=SHA, scope="s", examined=3))
        assert missing_outcomes(["a"], [ok], Candidate(SHA)) == ()
