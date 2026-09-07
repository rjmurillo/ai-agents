"""An actionlint that never ran must not read as workflow violations (item 6).

``validate_workflow_yaml`` returned ``CheckOutcome.failed(reason=
"actionlint.violation")`` for any non-zero actionlint exit and never called
``classify_subprocess_failure``. ``_run_subprocess`` reports a timeout and a
failed exec with the same non-zero shape as a real finding, so a timed-out or
unexecutable actionlint was reported as violations in workflow files that do not
have any.

This is the exact twin of the ``validate_yaml_style`` defect fixed in #5641; the
fix landed on one half of the pair and not the other. It fails closed rather
than open, so it is less dangerous than its sibling, and the diagnosis it hands
the reader is still wrong: they go read workflow YAML that is fine instead of
finding out why actionlint hung.

``tests/validation_pre_pr/test_yaml_style_checks.py::TestYamlStyleExecutionFailures``
is the sibling suite these mirror.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import patch

from scripts.validation.evidence import (
    REASON_TIMEOUT,
    REASON_TOOL_ABSENT,
    EvidenceState,
    default_pre_pr_policy,
)
from scripts.validation.pre_pr import validate_workflow_yaml


def _run(tmp_path: Path, result: tuple[int, str, str]) -> Any:
    """Drive the real validator over one changed workflow file."""
    (tmp_path / ".github" / "workflows").mkdir(parents=True)
    with patch("checks_tooling.shutil.which", return_value="/usr/bin/actionlint"):
        with patch("checks_tooling._workflow_yaml_targets", return_value=["ci.yml"]):
            with patch("checks_tooling._run_subprocess", return_value=result):
                return validate_workflow_yaml(tmp_path)


class TestWorkflowYamlExecutionFailures:
    """Three non-zero exits, three findings, three remedies."""

    def test_a_real_finding_still_fails(self, tmp_path: Path) -> None:
        """Positive control. actionlint's own finding exit is unchanged."""
        outcome = _run(tmp_path, (1, "ci.yml:3:1: unexpected key \"jobss\"", ""))

        assert outcome.state is EvidenceState.FAIL
        assert outcome.reason == "actionlint.violation"
        assert outcome.examined == 1

    def test_a_timeout_reports_unknown(self, tmp_path: Path) -> None:
        """The discriminating case: this was FAIL actionlint.violation before."""
        outcome = _run(tmp_path, (-1, "", "Command timed out after 120s"))

        assert outcome.state is EvidenceState.UNKNOWN
        assert outcome.reason == REASON_TIMEOUT

    def test_an_unexecutable_binary_reports_blocked(self, tmp_path: Path) -> None:
        """``shutil.which`` found it and exec did not. Nothing was examined.

        A PATH probe answers a different question from an exec attempt: the
        binary can be present, non-executable, and mislinked, and only the exec
        finds out.
        """
        outcome = _run(tmp_path, (-1, "", "Command not found: actionlint"))

        assert outcome.state is EvidenceState.BLOCKED
        assert outcome.reason == REASON_TOOL_ABSENT

    def test_a_timeout_is_not_licensed_by_the_documented_policy(
        self, tmp_path: Path
    ) -> None:
        """The policy licenses an absent actionlint, never an unfinished one.

        Install it versus find out why it hung are different remedies, which is
        why they are different states. Licensing the second the way the first is
        licensed would put the fail-open back in a new place.
        """
        outcome = _run(tmp_path, (-1, "", "Command timed out after 120s"))

        assert not default_pre_pr_policy().accepts(outcome)

    def test_an_unexecutable_binary_is_licensed_the_same_as_an_absent_one(
        self, tmp_path: Path
    ) -> None:
        """Edge, and the reason BLOCKED is the right state rather than UNKNOWN.

        actionlint is an optional developer-machine install. A contributor whose
        copy will not exec is in the same position as one who never installed
        it, and blocking their push would be a new gate rather than a fix.
        """
        outcome = _run(tmp_path, (-1, "", "Command not found: actionlint"))

        assert default_pre_pr_policy().accepts(outcome)

    def test_no_execution_failure_claims_to_have_examined_files(
        self, tmp_path: Path
    ) -> None:
        """``ci-scripts.md`` MUST 12: a run that did nothing must not count.

        A BLOCKED or UNKNOWN carrying ``examined=1`` would tell a summary reader
        the gate looked at a file it never opened.
        """
        for result in (
            (-1, "", "Command timed out after 120s"),
            (-1, "", "Command not found: actionlint"),
        ):
            outcome = _run(Path(str(tmp_path)) / str(hash(result)), result)

            assert outcome.examined is None
