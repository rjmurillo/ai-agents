"""Typed states for the citation, contradiction, review-marker, dash, and Copilot gates.

Issue #5636: each gate used to collapse every non-pass path to a bare ``bool``.
These tests pin the state and reason code each path now returns, and whether the
pre-PR policy blocks it. The blocking column is the invariant: no path that
blocked before may stop blocking, and no path that passed may start blocking.

Functions are imported through ``scripts.validation.pre_pr`` and patched by their
flat module names, the way the sibling tests do, because ``pre_pr`` loads the
``checks_*`` modules flat and a patch on the package-path copy would miss.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from scripts.validation.evidence import (
    REASON_ADVISORY_FINDINGS,
    REASON_BASE_REF_UNRESOLVED,
    REASON_DIFF_FAILED,
    REASON_ENTRIES_UNREADABLE,
    REASON_MALFORMED_OUTPUT,
    REASON_PR_UNRESOLVED,
    REASON_SCOPE_EMPTY,
    REASON_SCRIPT_ABSENT,
    REASON_SCRIPT_FAILED,
    REASON_TREE_ABSENT,
    REASON_VALIDATOR_RAISED,
    REASON_VIOLATIONS_FOUND,
    CheckOutcome,
    EvidenceState,
    pre_pr_policy,
)
from scripts.validation.pre_pr import (
    validate_canonical_citations,
    validate_dash_prohibition,
    validate_orchestrator_citations,
    validate_review_marker,
    validate_spec_contradiction,
)

_EM_DASH = chr(0x2014)


def _repo(tmp_path: Path, script: str | None) -> Path:
    validation = tmp_path / "scripts" / "validation"
    validation.mkdir(parents=True)
    if script:
        (validation / script).write_text("# stub\n", encoding="utf-8")
    return tmp_path


def _check(outcome: CheckOutcome, state: EvidenceState, reason: str, *, blocks: bool) -> None:
    assert outcome.state is state
    assert outcome.reason == reason
    assert pre_pr_policy().accepts(outcome) is not blocks


@pytest.fixture(autouse=True)
def _local_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("CI", "GITHUB_ACTIONS", "REVIEW_MARKER_ENFORCED"):
        monkeypatch.delenv(name, raising=False)


class TestCanonicalCitations:
    _SCRIPT = "check_canonical_citations.py"

    def _run(self, tmp_path: Path, result: tuple[int, str, str]) -> CheckOutcome:
        repo = _repo(tmp_path, self._SCRIPT)
        with patch("checks_citations._run_subprocess", return_value=result):
            return validate_canonical_citations(repo)

    def test_an_absent_script_is_a_licensed_skip(self, tmp_path: Path) -> None:
        outcome = validate_canonical_citations(_repo(tmp_path, None))

        _check(outcome, EvidenceState.SKIP, REASON_SCRIPT_ABSENT, blocks=False)

    def test_a_clean_report_is_a_pass(self, tmp_path: Path) -> None:
        outcome = self._run(tmp_path, (0, "[PASS] No uncited mirror-claims found.\n", ""))

        assert outcome.state is EvidenceState.PASS

    def test_a_soft_warning_is_a_counted_advisory_finding(self, tmp_path: Path) -> None:
        out = "[WARN] 3 uncited mirror-claim(s) found.\n"
        outcome = self._run(tmp_path, (0, out, ""))

        _check(outcome, EvidenceState.FAIL, REASON_ADVISORY_FINDINGS, blocks=False)
        assert outcome.findings == 3

    def test_an_early_pass_line_cannot_hide_a_later_warning(self, tmp_path: Path) -> None:
        out = "[PASS] header\n[WARN] 2 uncited mirror-claim(s) found.\n"
        outcome = self._run(tmp_path, (0, out, ""))

        _check(outcome, EvidenceState.FAIL, REASON_ADVISORY_FINDINGS, blocks=False)
        assert outcome.findings == 2

    def test_no_scan_roots_is_a_licensed_skip(self, tmp_path: Path) -> None:
        outcome = self._run(tmp_path, (0, "[SKIP] no scan roots present\n", ""))

        _check(outcome, EvidenceState.SKIP, REASON_TREE_ABSENT, blocks=False)

    @pytest.mark.parametrize("stdout", ["", "all good\n", "[FAIL] 2 uncited mirror-claim(s)\n"])
    def test_an_unreadable_report_at_exit_zero_is_counted_not_a_pass(
        self, tmp_path: Path, stdout: str
    ) -> None:
        outcome = self._run(tmp_path, (0, stdout, ""))

        _check(outcome, EvidenceState.BLOCKED, REASON_MALFORMED_OUTPUT, blocks=False)

    def test_strict_mode_failure_still_blocks(self, tmp_path: Path) -> None:
        outcome = self._run(tmp_path, (1, "[FAIL] 2 uncited mirror-claim(s)\n", ""))

        _check(outcome, EvidenceState.FAIL, REASON_VIOLATIONS_FOUND, blocks=True)

    def test_a_configuration_exit_is_a_script_failure_not_a_violation(
        self, tmp_path: Path
    ) -> None:
        """Exit 2 means the repo root was invalid; nothing was measured (PR #6066 review)."""
        outcome = self._run(tmp_path, (2, "", "[FAIL] repo root not found"))

        _check(outcome, EvidenceState.FAIL, REASON_SCRIPT_FAILED, blocks=True)

    def test_a_timeout_blocks_with_its_own_reason(self, tmp_path: Path) -> None:
        stderr = "Command timed out after 30s"
        outcome = self._run(tmp_path, (-1, "", stderr))

        assert outcome.state is EvidenceState.FAIL
        assert outcome.reason == "timeout"
        assert not pre_pr_policy().accepts(outcome)


class TestOrchestratorCitations:
    _SCRIPT = "check_orchestrator_citations.py"

    def test_an_absent_script_blocks(self, tmp_path: Path) -> None:
        outcome = validate_orchestrator_citations(_repo(tmp_path, None))

        _check(outcome, EvidenceState.FAIL, REASON_SCRIPT_ABSENT, blocks=True)

    def test_exit_zero_is_a_pass(self, tmp_path: Path) -> None:
        repo = _repo(tmp_path, self._SCRIPT)
        with patch("checks_citations._run_subprocess", return_value=(0, "ok", "")):
            outcome = validate_orchestrator_citations(repo)

        assert outcome.state is EvidenceState.PASS

    @pytest.mark.parametrize(
        ("exit_code", "reason"),
        [(1, REASON_VIOLATIONS_FOUND), (2, REASON_SCRIPT_FAILED)],
    )
    def test_a_nonzero_exit_blocks_and_names_finding_versus_script_error(
        self, tmp_path: Path, exit_code: int, reason: str
    ) -> None:
        repo = _repo(tmp_path, self._SCRIPT)
        with patch("checks_citations._run_subprocess", return_value=(exit_code, "", "bad")):
            outcome = validate_orchestrator_citations(repo)

        _check(outcome, EvidenceState.FAIL, reason, blocks=True)


class TestSpecContradiction:
    _SCRIPT = "spec_contradiction.py"

    def _run(self, tmp_path: Path, result: tuple[int, str, str]) -> CheckOutcome:
        repo = _repo(tmp_path, self._SCRIPT)
        with (
            patch("checks_citations._resolve_branch_base_ref", return_value="origin/main"),
            patch("checks_citations._run_subprocess", return_value=result),
        ):
            return validate_spec_contradiction(repo)

    def test_an_absent_script_is_a_licensed_skip(self, tmp_path: Path) -> None:
        _check(
            validate_spec_contradiction(_repo(tmp_path, None)),
            EvidenceState.SKIP,
            REASON_SCRIPT_ABSENT,
            blocks=False,
        )

    def test_a_clean_report_is_a_pass(self, tmp_path: Path) -> None:
        outcome = self._run(tmp_path, (0, "[PASS] No spec-vs-code contradictions detected.", ""))

        assert outcome.state is EvidenceState.PASS

    def test_a_contradiction_is_a_counted_advisory_finding(self, tmp_path: Path) -> None:
        out = "[WARN] 2 spec-vs-code contradiction(s) detected:\n  - a"
        outcome = self._run(tmp_path, (0, out, ""))

        _check(outcome, EvidenceState.FAIL, REASON_ADVISORY_FINDINGS, blocks=False)
        assert outcome.findings == 2

    @pytest.mark.parametrize("exit_code", [2, -1, -9])
    def test_a_script_error_or_kill_never_blocks(self, tmp_path: Path, exit_code: int) -> None:
        """The old wrapper returned True for every non-zero exit; so does this."""
        outcome = self._run(tmp_path, (exit_code, "", "boom"))

        _check(outcome, EvidenceState.BLOCKED, REASON_SCRIPT_FAILED, blocks=False)

    def test_an_unreadable_report_at_exit_zero_is_counted_not_a_pass(
        self, tmp_path: Path
    ) -> None:
        outcome = self._run(tmp_path, (0, "nothing recognizable", ""))

        _check(outcome, EvidenceState.BLOCKED, REASON_MALFORMED_OUTPUT, blocks=False)

    @pytest.mark.parametrize("reason", ["pr.unresolved", "base_ref.unresolved", "scope.empty"])
    def test_a_producer_that_compared_nothing_is_a_licensed_skip_with_its_reason(
        self, tmp_path: Path, reason: str
    ) -> None:
        out = f"[SKIP] reason={reason} nothing was compared (no PR).\n"
        outcome = self._run(tmp_path, (0, out, ""))

        _check(outcome, EvidenceState.SKIP, reason, blocks=False)

    def test_a_skip_with_a_malformed_reason_falls_back_to_tree_absent(
        self, tmp_path: Path
    ) -> None:
        outcome = self._run(tmp_path, (0, "[SKIP] reason=NOT A SLUG\n", ""))

        _check(outcome, EvidenceState.SKIP, REASON_TREE_ABSENT, blocks=False)


class TestProducerContract:
    """The wrappers parse what the real producers print, not strings written for the test."""

    def _outcome(self, name: str, text: str) -> CheckOutcome:
        import checks_citations

        return checks_citations._status_outcome(name, "scope", text)

    def test_canonical_clean_and_warn_reports_map_to_pass_and_advisory_fail(self) -> None:
        import check_canonical_citations as producer

        clean = producer.format_report([], strict=False)
        warn = producer.format_report(
            [producer.Violation(path="a.py", matched_token="matches", excerpt="x")], strict=False
        )

        assert self._outcome("validate_canonical_citations", clean).state is EvidenceState.PASS
        flagged = self._outcome("validate_canonical_citations", warn)
        _check(flagged, EvidenceState.FAIL, REASON_ADVISORY_FINDINGS, blocks=False)
        assert flagged.findings == 1

    def test_canonical_strict_report_is_not_read_as_a_pass_at_exit_zero(self) -> None:
        import check_canonical_citations as producer

        strict = producer.format_report(
            [producer.Violation(path="a.py", matched_token="matches", excerpt="x")], strict=True
        )

        outcome = self._outcome("validate_canonical_citations", strict)

        _check(outcome, EvidenceState.BLOCKED, REASON_MALFORMED_OUTPUT, blocks=False)

    @staticmethod
    def _load_contradiction_producer(monkeypatch: pytest.MonkeyPatch):
        import importlib.util

        path = Path(__file__).resolve().parents[2] / "scripts/validation/spec_contradiction.py"
        spec = importlib.util.spec_from_file_location("spec_contradiction_contract", path)
        assert spec is not None and spec.loader is not None
        producer = importlib.util.module_from_spec(spec)
        # A dataclass looks its module up in sys.modules while it is defined.
        monkeypatch.setitem(sys.modules, spec.name, producer)
        spec.loader.exec_module(producer)
        return producer

    def test_contradiction_reports_map_to_pass_finding_and_skip(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        producer = self._load_contradiction_producer(monkeypatch)
        finding = producer.Contradiction("model-tier", "model", "sonnet", "opus", "f.md", "PR")

        name = "validate_spec_contradiction"
        assert self._outcome(name, producer.format_report([])).state is EvidenceState.PASS
        warned = self._outcome(name, producer.format_report([finding]))
        _check(warned, EvidenceState.FAIL, REASON_ADVISORY_FINDINGS, blocks=False)
        assert warned.findings == 1
        skipped = self._outcome(name, producer.format_skip("pr.unresolved"))
        _check(skipped, EvidenceState.SKIP, "pr.unresolved", blocks=False)

    def test_the_producer_skip_reasons_match_the_evidence_constants(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """The producer is stdlib-only and hardcodes the codes, so pin them here."""
        producer = self._load_contradiction_producer(monkeypatch)
        monkeypatch.setattr(producer, "fetch_current_pr_body", lambda o, r: None)
        assert producer.collect_with_skip_reason(tmp_path, "o", "r")[1] == REASON_PR_UNRESOLVED

        monkeypatch.setattr(producer, "fetch_current_pr_body", lambda o, r: "body")
        monkeypatch.setattr(producer, "_resolve_base_ref", lambda root: None)
        assert (
            producer.collect_with_skip_reason(tmp_path, "o", "r")[1] == REASON_BASE_REF_UNRESOLVED
        )

        monkeypatch.setattr(producer, "_changed_agent_files", lambda root, base: {})
        skip = producer.collect_with_skip_reason(tmp_path, "o", "r", base_ref="origin/main")[1]
        assert skip == REASON_SCOPE_EMPTY


class TestReviewMarker:
    _SCRIPT = "validate_review_marker.py"

    def _run(self, tmp_path: Path, result: tuple[int, str, str]) -> CheckOutcome:
        repo = _repo(tmp_path, self._SCRIPT)
        with patch("checks_coverage._run_subprocess", return_value=result):
            return validate_review_marker(repo)

    def test_a_valid_marker_is_a_pass_naming_the_revision(self, tmp_path: Path) -> None:
        outcome = self._run(tmp_path, (0, "[PASS] marker binds HEAD", ""))

        assert outcome.state is EvidenceState.PASS
        assert outcome.revision == "HEAD"

    def test_advisory_absent_script_is_a_licensed_skip(self, tmp_path: Path) -> None:
        _check(
            validate_review_marker(_repo(tmp_path, None)),
            EvidenceState.SKIP,
            REASON_SCRIPT_ABSENT,
            blocks=False,
        )

    def test_enforced_absent_script_blocks(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("REVIEW_MARKER_ENFORCED", "1")

        _check(
            validate_review_marker(_repo(tmp_path, None)),
            EvidenceState.FAIL,
            REASON_SCRIPT_ABSENT,
            blocks=True,
        )

    @pytest.mark.parametrize("exit_code", [1, 2, -1, -9])
    def test_advisory_nonzero_never_blocks(self, tmp_path: Path, exit_code: int) -> None:
        outcome = self._run(tmp_path, (exit_code, "[FAIL] no marker", ""))

        _check(outcome, EvidenceState.FAIL, REASON_ADVISORY_FINDINGS, blocks=False)

    @pytest.mark.parametrize("exit_code", [1, 2])
    def test_enforced_nonzero_blocks(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, exit_code: int
    ) -> None:
        monkeypatch.setenv("REVIEW_MARKER_ENFORCED", "true")
        outcome = self._run(tmp_path, (exit_code, "[FAIL] no marker", ""))

        _check(outcome, EvidenceState.FAIL, REASON_VIOLATIONS_FOUND, blocks=True)


class TestDashProhibition:
    def _run(self, tmp_path: Path, calls: list[tuple[int, str, str]] | None) -> CheckOutcome:
        with (
            patch(
                "checks_dash._resolve_branch_base_ref",
                return_value=None if calls is None else "origin/main",
            ),
            patch("checks_dash._run_subprocess", side_effect=calls or []),
        ):
            return validate_dash_prohibition(tmp_path)

    def test_an_unresolved_base_ref_is_a_licensed_skip_locally(self, tmp_path: Path) -> None:
        outcome = self._run(tmp_path, None)

        _check(outcome, EvidenceState.SKIP, REASON_BASE_REF_UNRESOLVED, blocks=False)

    @pytest.mark.parametrize("variable", ["CI", "GITHUB_ACTIONS"])
    def test_an_unresolved_base_ref_blocks_under_ci(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, variable: str
    ) -> None:
        monkeypatch.setenv(variable, "true")

        _check(
            self._run(tmp_path, None),
            EvidenceState.FAIL,
            REASON_BASE_REF_UNRESOLVED,
            blocks=True,
        )

    def test_a_failed_git_diff_keeps_its_own_reason_and_the_ci_split(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        failed = [(128, "", "fatal: bad revision")]

        _check(self._run(tmp_path, failed), EvidenceState.SKIP, REASON_DIFF_FAILED, blocks=False)
        monkeypatch.setenv("CI", "1")
        _check(self._run(tmp_path, failed), EvidenceState.FAIL, REASON_DIFF_FAILED, blocks=True)

    def test_no_markdown_files_is_a_pass_that_says_zero_examined(self, tmp_path: Path) -> None:
        outcome = self._run(tmp_path, [(0, "src/app.py\n", "")])

        assert outcome.state is EvidenceState.PASS
        assert outcome.examined == 0

    def test_a_clean_branch_is_a_pass_naming_the_examined_count(self, tmp_path: Path) -> None:
        outcome = self._run(tmp_path, [(0, "a.md\nb.md\n", ""), (0, "ok\n", ""), (0, "ok\n", "")])

        assert outcome.state is EvidenceState.PASS
        assert (outcome.revision, outcome.examined) == ("HEAD", 2)

    def test_a_violation_blocks_and_counts_the_hits(self, tmp_path: Path) -> None:
        calls = [(0, "a.md\n", ""), (0, f"x{_EM_DASH}y\nfine\nz{_EM_DASH}\n", "")]

        outcome = self._run(tmp_path, calls)

        _check(outcome, EvidenceState.FAIL, REASON_VIOLATIONS_FOUND, blocks=True)
        assert outcome.findings == 2

    def test_a_narrowed_scan_is_blocked_but_licensed_not_a_clean_pass(self, tmp_path: Path) -> None:
        """A blob git cannot read was never checked, so PASS would overclaim (PR #6066 review)."""
        calls = [(0, "a.md\nb.md\n", ""), (128, "", "gone"), (0, "ok\n", "")]

        outcome = self._run(tmp_path, calls)

        _check(outcome, EvidenceState.BLOCKED, REASON_ENTRIES_UNREADABLE, blocks=False)
        assert "1 of 2 candidate file(s) examined; 1 unreadable" in outcome.detail

    def test_a_violation_beside_an_unreadable_file_still_blocks(self, tmp_path: Path) -> None:
        calls = [(0, "a.md\nb.md\n", ""), (128, "", "gone"), (0, f"x{_EM_DASH}y\n", "")]

        outcome = self._run(tmp_path, calls)

        _check(outcome, EvidenceState.FAIL, REASON_VIOLATIONS_FOUND, blocks=True)


class TestCopilotRoutingExclusions:
    def _run(self, tmp_path: Path, module_result: Mock) -> CheckOutcome:
        import argparse

        import pre_pr_sequence

        with patch("checks_copilot._validate_module", module_result):
            outcome = pre_pr_sequence._run_copilot_routing_exclusions(
                tmp_path, argparse.Namespace()
            )
        assert isinstance(outcome, CheckOutcome), "the sequence must not collapse it to a bool"
        return outcome

    def test_a_clean_scan_is_a_pass(self, tmp_path: Path) -> None:
        assert self._run(tmp_path, Mock(return_value=True)).state is EvidenceState.PASS

    def test_a_violation_blocks(self, tmp_path: Path) -> None:
        outcome = self._run(tmp_path, Mock(return_value=False))

        _check(outcome, EvidenceState.FAIL, REASON_VIOLATIONS_FOUND, blocks=True)

    def test_a_missing_template_is_a_licensed_skip(self, tmp_path: Path) -> None:
        outcome = self._run(tmp_path, Mock(side_effect=FileNotFoundError("template")))

        _check(outcome, EvidenceState.SKIP, REASON_TREE_ABSENT, blocks=False)

    def test_a_raise_blocks_with_the_raised_reason(self, tmp_path: Path) -> None:
        outcome = self._run(tmp_path, Mock(side_effect=ValueError("bad config")))

        _check(outcome, EvidenceState.FAIL, REASON_VALIDATOR_RAISED, blocks=True)
        assert "bad config" in outcome.detail

    def test_a_missing_template_blocks_through_the_real_scanner(self, tmp_path: Path) -> None:
        """It raises RoutingConfigError, not FileNotFoundError, so it is not a SKIP."""
        import checks_copilot

        outcome = checks_copilot.validate_copilot_routing_exclusions(tmp_path)

        _check(outcome, EvidenceState.FAIL, REASON_VALIDATOR_RAISED, blocks=True)
