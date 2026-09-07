"""A signal-killed child carries no verdict (issue #5653).

``classify_subprocess_failure`` gated its whole body on
``exit_code == _SENTINEL_EXIT`` (-1), the value ``_run_subprocess`` returns for
the two failures it synthesizes itself. :func:`subprocess.run` reports a child
killed by a signal as the negated signal number, so ``-9`` is SIGKILL and
``-15`` is SIGTERM. Neither is -1 and neither carries a stderr marker, so both
fell through to the caller's ``default``.

For the two linter validators that ``default`` is the empty string, and the
code then read the kill as the linter's own findings exit. ``validate_workflow
_yaml`` reported workflow violations that do not exist, with an ``examined``
count asserting it had read every file; ``validate_yaml_style`` returned a PASS
whose scope claimed ``advisory findings tolerated``. The second is the
dangerous one: its findings path is a PASS, so the fabricated verdict is green.

Found by Devin Review on PR #5649, which fixed the two failures the wrapper
documents and treated that enumeration as complete.

The unit cases live here rather than beside the existing classifier tests
because the wiring cases below are the point: the classifier can be correct
while a call site still ignores it, which is exactly the shape #5649 shipped.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from scripts.validation.evidence import (
    REASON_PROCESS_SIGNALED,
    REASON_TIMEOUT,
    REASON_TOOL_ABSENT,
    EvidenceState,
    default_pre_pr_policy,
)
from scripts.validation.pre_pr import validate_workflow_yaml, validate_yaml_style
from scripts.validation.subprocess_runner import classify_subprocess_failure

#: SIGKILL and SIGTERM as ``subprocess.run`` reports them, plus the markerless
#: -1 that is SIGHUP rather than this wrapper's sentinel.
_SIGNAL_EXITS = (-9, -15, -1, -2, -6)


class TestClassifierReadsTheSign:
    """The rule is the sign of the code, not one sentinel value."""

    @pytest.mark.parametrize("exit_code", _SIGNAL_EXITS)
    def test_a_signal_exit_is_named_rather_than_defaulted(self, exit_code: int) -> None:
        """The discriminating case: every one of these returned "" before."""
        assert (
            classify_subprocess_failure(exit_code, "", default="") == REASON_PROCESS_SIGNALED
        )

    def test_a_markerless_minus_one_is_a_signal_not_the_sentinel(self) -> None:
        """Edge, and the one that looks wrong until you read the wrapper.

        ``_run_subprocess`` writes ``Command timed out after`` or ``Command not
        found:`` whenever it returns -1 itself, so a markerless -1 cannot have
        come from the wrapper. It is SIGHUP, and reading it as a findings exit
        is the same defect with a different signal number.
        """
        assert classify_subprocess_failure(-1, "", default="") == REASON_PROCESS_SIGNALED

    def test_the_two_marked_sentinels_still_win_over_the_sign_rule(self) -> None:
        """Negative control on the new branch.

        Both markers arrive on -1, which the sign rule also matches. If the new
        branch were placed above them it would swallow both, collapsing three
        remedies (find the killer, raise the timeout, install the tool) into
        one. Ordering is the property under test, so assert it directly.
        """
        assert (
            classify_subprocess_failure(-1, "Command timed out after 120s", default="")
            == REASON_TIMEOUT
        )
        assert (
            classify_subprocess_failure(-1, "Command not found: actionlint", default="")
            == REASON_TOOL_ABSENT
        )

    @pytest.mark.parametrize("exit_code", (1, 2, 123))
    def test_a_positive_exit_still_reaches_the_caller_default(self, exit_code: int) -> None:
        """Positive control. A real findings exit must stay a findings exit.

        Without this, a classifier that returned the signal reason for every
        non-zero code would pass every test above while turning every genuine
        lint violation into UNKNOWN.
        """
        assert classify_subprocess_failure(exit_code, "", default="lint.violation") == (
            "lint.violation"
        )

    def test_a_signal_exit_outranks_a_non_empty_caller_default(self) -> None:
        """The three call sites that pass a real default gain accuracy here.

        ``validate_session_end`` passes ``diff.failed``; a killed ``git diff``
        is not a diff that failed to resolve, and both already map to UNKNOWN,
        so this changes the reason without changing the state.
        """
        assert (
            classify_subprocess_failure(-9, "", default="diff.failed")
            == REASON_PROCESS_SIGNALED
        )


def _run_workflow(tmp_path: Path, result: tuple[int, str, str]) -> Any:
    """Drive the real actionlint validator over one changed workflow file."""
    (tmp_path / ".github" / "workflows").mkdir(parents=True)
    with patch("checks_tooling.shutil.which", return_value="/usr/bin/actionlint"):
        with patch("checks_tooling._workflow_yaml_targets", return_value=["ci.yml"]):
            with patch("checks_tooling._run_subprocess", return_value=result):
                return validate_workflow_yaml(tmp_path)


def _run_yaml_style(tmp_path: Path, result: tuple[int, str, str]) -> Any:
    """Drive the real yamllint validator over one changed YAML file."""
    with patch("checks_tooling.shutil.which", return_value="/usr/bin/yamllint"):
        with patch("checks_tooling._yaml_style_targets", return_value=["config.yml"]):
            with patch("checks_tooling._run_subprocess", return_value=result):
                return validate_yaml_style(tmp_path)


class TestWorkflowYamlWiring:
    """A correct classifier proves nothing until the call site reads it."""

    @pytest.mark.parametrize("exit_code", _SIGNAL_EXITS)
    def test_a_killed_actionlint_reports_unknown(
        self, tmp_path: Path, exit_code: int
    ) -> None:
        """The discriminating case: this was FAIL actionlint.violation."""
        outcome = _run_workflow(tmp_path / str(exit_code), (exit_code, "", ""))

        assert outcome.state is EvidenceState.UNKNOWN
        assert outcome.reason == REASON_PROCESS_SIGNALED

    def test_a_killed_actionlint_claims_no_examined_count(self, tmp_path: Path) -> None:
        """``ci-scripts.md`` MUST 12. The old FAIL carried examined=1.

        A count is the reader's evidence that the gate looked. Reporting one
        for a run that was killed mid-scan is the same lie as the verdict.
        """
        outcome = _run_workflow(tmp_path, (-9, "", ""))

        assert outcome.examined is None
        assert outcome.findings is None

    def test_a_killed_actionlint_is_not_licensed_by_the_pre_pr_policy(
        self, tmp_path: Path
    ) -> None:
        """UNKNOWN blocks. Only an absent actionlint is licensed.

        Licensing this would convert a spurious red into a silent green, which
        is worse than the defect being fixed.
        """
        outcome = _run_workflow(tmp_path, (-9, "", ""))

        assert not default_pre_pr_policy().accepts(outcome)

    def test_a_real_actionlint_finding_still_fails(self, tmp_path: Path) -> None:
        """Positive control for every case above."""
        outcome = _run_workflow(tmp_path, (1, 'ci.yml:3:1: unexpected key "jobss"', ""))

        assert outcome.state is EvidenceState.FAIL
        assert outcome.reason == "actionlint.violation"
        assert outcome.examined == 1


class TestYamlStyleWiring:
    """The half where the fabricated verdict was green rather than red."""

    @pytest.mark.parametrize("exit_code", _SIGNAL_EXITS)
    def test_a_killed_yamllint_reports_unknown(
        self, tmp_path: Path, exit_code: int
    ) -> None:
        """The discriminating case: this was a PASS.

        The scope string said ``advisory findings tolerated``, so the summary
        showed a clean advisory run for a linter that never finished.
        """
        outcome = _run_yaml_style(tmp_path, (exit_code, "", ""))

        assert outcome.state is EvidenceState.UNKNOWN
        assert outcome.reason == REASON_PROCESS_SIGNALED

    def test_a_killed_yamllint_does_not_claim_tolerated_findings(
        self, tmp_path: Path
    ) -> None:
        """The specific false claim the old PASS made about its own scope."""
        outcome = _run_yaml_style(tmp_path, (-15, "", ""))

        assert "advisory findings tolerated" not in outcome.scope
        assert outcome.examined is None

    def test_a_killed_yamllint_is_not_licensed_by_the_pre_pr_policy(
        self, tmp_path: Path
    ) -> None:
        """The advisory licence covers an absent yamllint, not an unfinished one."""
        outcome = _run_yaml_style(tmp_path, (-9, "", ""))

        assert not default_pre_pr_policy().accepts(outcome)

    def test_tolerated_style_findings_still_pass(self, tmp_path: Path) -> None:
        """Positive control. Issue #2374 keeps style findings non-blocking."""
        outcome = _run_yaml_style(tmp_path, (1, "config.yml:1:1: [warning] ...", ""))

        assert outcome.state is EvidenceState.PASS
        assert "advisory findings tolerated" in outcome.scope

    def test_an_absent_yamllint_is_still_blocked_and_licensed(
        self, tmp_path: Path
    ) -> None:
        """Positive control on the branch above the new one.

        The tool-absent case shares the -1 code with the sign rule, so a
        misordered guard would reroute it to UNKNOWN and start blocking every
        contributor who has not installed yamllint.
        """
        outcome = _run_yaml_style(tmp_path, (-1, "", "Command not found: yamllint"))

        assert outcome.state is EvidenceState.BLOCKED
        assert outcome.reason == REASON_TOOL_ABSENT
        assert default_pre_pr_policy().accepts(outcome)
