"""Warning-failure reporting tests for new_pr.py validations (issue #4764).

Validation 4 runs ``validate_pr_description.py`` in warning mode: a non-zero
exit does not block PR creation. That policy is deliberate and this module does
not change it. What it pins is the SUMMARY the script prints afterwards.

Measured on the merged tree at ``5cd72a7dad`` with a stub validator that
printed ``ERROR: invalid PR description`` on stderr and exited 1:

    [4/6] Validating PR description...
    ...
    Trusted pre-creation validations passed. 3 repository-local check(s) did
    not run: ...

The validator failed, its error reached the terminal, and the script still
reported that the trusted validations passed. The two lines contradict each
other, and the summary is the line a reader scans. A warning that is announced
as a pass is not a warning; it is a silent failure with extra output.

The fix tracks warning-level failures and reports completion WITH WARNINGS,
while still exiting 0 so the warning-only policy is preserved.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / ".claude/skills/github/scripts/pr"))

from new_pr import run_validations

PASS_SUMMARY = "Trusted pre-creation validations passed."
WARNING_SUMMARY = "Trusted pre-creation validations completed with warnings."


def _completed(
    stdout: str = "",
    stderr: str = "",
    rc: int = 0,
) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(args=[], returncode=rc, stdout=stdout, stderr=stderr)


def _dispatcher(*, validator_rc: int, validator_stderr: str = ""):
    """Dispatch on the argument vector, never on call order.

    ``.claude/rules/testing.md`` SHOULD 11 requires this: a positional
    ``side_effect`` list silently shifts when a branch skips a call, and three
    such lists in ``tests/test_new_pr.py`` broke for exactly that reason.
    """

    def run(cmd, **_kwargs) -> subprocess.CompletedProcess[str]:
        argv = [str(part) for part in cmd]
        if argv[:3] == ["git", "diff", "--name-only"]:
            return _completed(stdout="src/main.py\n", rc=0)
        if any(part.endswith("validate_pr_description.py") for part in argv):
            return _completed(stderr=validator_stderr, rc=validator_rc)
        if argv[:1] == ["git"]:
            return _completed(rc=0)
        raise AssertionError(f"unstubbed subprocess call: {argv}")

    return run


def test_failing_description_validator_is_reported_as_a_warning(tmp_path, capsys) -> None:
    """A warning-mode failure must not print the unqualified pass summary.

    This is the reported regression. The validator exits 1, its message reaches
    stderr, and the merged tree still printed
    ``Trusted pre-creation validations passed.``
    """
    with patch(
        "subprocess.run",
        side_effect=_dispatcher(
            validator_rc=1,
            validator_stderr="ERROR: invalid PR description\n",
        ),
    ):
        run_validations(str(tmp_path), "main", "feat/branch", title="feat: x", body="body")

    captured = capsys.readouterr()

    assert PASS_SUMMARY not in captured.out, (
        "a failing warning-mode validator still reported an unqualified pass"
    )
    assert WARNING_SUMMARY in captured.out
    assert "ERROR: invalid PR description" in captured.err


def test_failing_description_validator_still_does_not_block(tmp_path) -> None:
    """The warning-only policy is preserved: no SystemExit on validator failure.

    This is the inverse control for the test above. Reporting the failure
    honestly must not turn Validation 4 into a blocking gate, which would be a
    behavior change nobody asked for and would break every PR whose description
    the CI-side validator merely warns about.
    """
    with patch(
        "subprocess.run",
        side_effect=_dispatcher(validator_rc=1, validator_stderr="ERROR: invalid\n"),
    ):
        run_validations(str(tmp_path), "main", "feat/branch", title="feat: x", body="body")


def test_passing_description_validator_keeps_the_pass_summary(tmp_path, capsys) -> None:
    """A clean run still reports a clean pass.

    Without this, changing the summary to always say "with warnings" would pass
    the test above while destroying the signal.
    """
    with patch("subprocess.run", side_effect=_dispatcher(validator_rc=0)):
        run_validations(str(tmp_path), "main", "feat/branch", title="feat: x", body="body")

    captured = capsys.readouterr()

    assert PASS_SUMMARY in captured.out
    assert WARNING_SUMMARY not in captured.out


def test_legacy_markdown_session_log_warning_is_tracked(tmp_path, capsys) -> None:
    """Every warning path feeds the same counter, not only Validation 4.

    A staged legacy ``.md`` session log (unvalidated, since only JSON is
    checked) prints a WARNING and was equally invisible in the summary.
    Fixing one warning path and leaving the others is the partial-guard
    failure mode. Session log creation is discontinued, so the sibling
    "no session log at all" case this test covered previously no longer
    warns: absence is now the expected state, not a gap to flag.
    """

    def run(cmd, **_kwargs) -> subprocess.CompletedProcess[str]:
        argv = [str(part) for part in cmd]
        if argv[:3] == ["git", "diff", "--name-only"]:
            return _completed(
                stdout=".agents/sessions/2026-08-21-session-1.md\n", rc=0
            )
        if any(part.endswith("validate_pr_description.py") for part in argv):
            return _completed(rc=0)
        return _completed(rc=0)

    with patch("subprocess.run", side_effect=run):
        run_validations(str(tmp_path), "main", "feat/branch", title="feat: x", body="body")

    captured = capsys.readouterr()

    assert "legacy .md session log(s) staged" in captured.err
    assert PASS_SUMMARY not in captured.out
    assert WARNING_SUMMARY in captured.out


def test_failed_git_diff_is_tracked_as_a_warning(tmp_path, capsys) -> None:
    """A failed ``git diff`` already printed a WARNING; the summary must say so.

    The changed-file set being unknown means Validations 1 and 2 measured
    nothing. Announcing that as a pass is the scope-measurement failure named in
    ``.claude/rules/testing.md`` MUST 10: a zero-finding result whose examined
    count is unknown.
    """

    def run(cmd, **_kwargs) -> subprocess.CompletedProcess[str]:
        argv = [str(part) for part in cmd]
        if argv[:3] == ["git", "diff", "--name-only"]:
            return _completed(stderr="fatal: bad revision\n", rc=128)
        return _completed(rc=0)

    with patch("subprocess.run", side_effect=run):
        run_validations(str(tmp_path), "main", "feat/branch", title="feat: x", body="body")

    captured = capsys.readouterr()

    assert "the changed-file set is unknown" in captured.err
    assert PASS_SUMMARY not in captured.out
    assert WARNING_SUMMARY in captured.out


def test_dash_violation_still_blocks(tmp_path) -> None:
    """Warning tracking must not soften the one CRITICAL validation.

    Validation 5 blocks on em/en-dashes. If the warning refactor converted it
    into a warning, this test fails and the regression is named.
    """
    with patch("subprocess.run", side_effect=_dispatcher(validator_rc=0)):
        with pytest.raises(SystemExit) as excinfo:
            run_validations(
                str(tmp_path),
                "main",
                "feat/branch",
                title="feat: x\u2014y",
                body="body",
            )

    assert excinfo.value.code == 1


def test_legacy_md_session_log_is_tracked_as_a_warning(tmp_path, capsys) -> None:
    """A legacy .md session log leaves nothing validated, so the summary must say so.

    ``_extract_validatable_session_logs`` prints ``WARNING: legacy .md session
    log(s) staged``, then the caller took the branch that records nothing: it
    neither validated a JSON log nor logged a warning, and the run closed with
    the unqualified pass headline. That is the same shape as the Validation 4
    defect this module was written for, one branch over, and it is why the
    warning log is checked here rather than only where it was first missing.
    """

    def run(cmd, **_kwargs) -> subprocess.CompletedProcess[str]:
        argv = [str(part) for part in cmd]
        if argv[:3] == ["git", "diff", "--name-only"]:
            return _completed(stdout=".agents/sessions/2026-01-01-session-01.md\n", rc=0)
        return _completed(rc=0)

    with patch("subprocess.run", side_effect=run):
        run_validations(str(tmp_path), "main", "feat/branch", title="feat: x", body="body")

    captured = capsys.readouterr()

    assert "legacy .md session log(s) staged" in captured.err
    assert PASS_SUMMARY not in captured.out
    assert WARNING_SUMMARY in captured.out


def test_validated_json_session_log_keeps_the_pass_summary(tmp_path, capsys) -> None:
    """Inverse control: a JSON session log is the case that should stay a pass.

    Without this, recording the legacy case could be satisfied by warning on
    every ``.agents/`` change, which would make the summary meaningless.
    """

    def run(cmd, **_kwargs) -> subprocess.CompletedProcess[str]:
        argv = [str(part) for part in cmd]
        if argv[:3] == ["git", "diff", "--name-only"]:
            return _completed(stdout=".agents/sessions/2026-01-01-session-01.json\n", rc=0)
        return _completed(rc=0)

    with patch("subprocess.run", side_effect=run):
        run_validations(str(tmp_path), "main", "feat/branch", title="feat: x", body="body")

    captured = capsys.readouterr()

    assert "legacy .md session log(s) staged" not in captured.err
    assert WARNING_SUMMARY not in captured.out
    assert PASS_SUMMARY in captured.out
