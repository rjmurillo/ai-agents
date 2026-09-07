"""Applicability outranks tool absence in ``validate_workflow_yaml``.

Split out of ``test_workflow_checks.py``, which crossed the 500-line taste
ceiling when this class was added. The concern is cohesive on its own: BLOCKED
and SKIP are not interchangeable, and the case that distinguishes them is the
one where BOTH the workflow tree and actionlint are absent.

The two single-axis tests in the sibling file each hold the other condition
favorable, so both passed while the combination returned the wrong state.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from scripts.validation.evidence import (
    REASON_TOOL_ABSENT,
    REASON_TREE_ABSENT,
    EvidenceState,
)


class TestWorkflowApplicabilityOutranksToolAbsence:
    """No workflow tree means SKIP, whether or not actionlint is installed.

    The two single-axis tests above each hold the other condition favorable:
    one has the tree and no tool, the other has the tool and no tree. Both
    passed while the combination of BOTH absent returned BLOCKED
    ``tool.absent``, because the tool probe ran before the applicability
    check. A downstream install with neither then read "install actionlint"
    for a gate that did not apply to it at all. Found by review on PR #5641.

    BLOCKED and SKIP are not interchangeable here: BLOCKED means a precondition
    we needed was missing, SKIP means there was nothing to examine. Reporting
    the first when the second is true sends the reader to fix a tool they do
    not need.
    """

    def test_neither_tree_nor_tool_reports_skip(self, tmp_path: Path) -> None:
        """The discriminating case: BLOCKED tool.absent before the fix."""
        from scripts.validation.pre_pr import validate_workflow_yaml

        with patch("checks_tooling.shutil.which", return_value=None):
            outcome = validate_workflow_yaml(tmp_path)

        assert outcome.state is EvidenceState.SKIP
        assert outcome.reason == REASON_TREE_ABSENT

    def test_a_present_tree_without_the_tool_still_reports_blocked(
        self, tmp_path: Path
    ) -> None:
        """Negative control: the reorder must not swallow real tool absence.

        Without this, moving the applicability check first could have turned
        every missing-actionlint run into SKIP, which would silently retire
        the tool.absent diagnosis the pre-PR policy licenses by name.
        """
        from scripts.validation.pre_pr import validate_workflow_yaml

        (tmp_path / ".github" / "workflows").mkdir(parents=True)
        with patch("checks_tooling.shutil.which", return_value=None):
            outcome = validate_workflow_yaml(tmp_path)

        assert outcome.state is EvidenceState.BLOCKED
        assert outcome.reason == REASON_TOOL_ABSENT
