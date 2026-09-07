"""A PASS may not name a revision that does not exist (issue #5646 item 2).

``validate_session_end`` discarded the exit code of ``git rev-parse HEAD`` and
substituted the literal string ``"INVALID_HEAD"`` when stdout came back empty.
``CheckOutcome._check_pass_evidence`` rejects only an empty or whitespace
revision, so the placeholder satisfied it and the gate reported PASS naming a
commit nobody can check out.

That defeats the single invariant the whole contract rests on. ``evidence.py``
says a PASS "cannot be constructed without naming the revision and scope it ran
against"; a placeholder names a revision the reader cannot falsify, which is
indistinguishable from naming nothing.

The subprocess fake dispatches on ``argv`` rather than on call order, per
``.claude/rules/testing.md`` SHOULD 11: ``validate_session_end`` issues its diff
and its rev-parse from two different branches, and a positional list would hand
the rev-parse response to the diff the moment either branch changed.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import patch

from scripts.validation.evidence import (
    REASON_DIFF_FAILED,
    REASON_INCOMPLETE_EVIDENCE,
    REASON_TIMEOUT,
    EvidenceState,
    default_pre_pr_policy,
)
from scripts.validation.pre_pr import validate_session_end

_HEAD_SHA = "4d9f1c0a2b3e5f6789abcdef0123456789abcdef"


def _git_fake(
    *, rev_parse: tuple[int, str, str], diff: tuple[int, str, str] = (0, "", "")
) -> Any:
    """Return a ``_run_subprocess`` replacement keyed on the git subcommand."""

    def run(args: list[str], **_kwargs: Any) -> tuple[int, str, str]:
        if "rev-parse" in args:
            return rev_parse
        if "diff" in args:
            return diff
        raise AssertionError(f"unstubbed command: {args}")

    return run


def _run(repo_root: Path, runner: Any) -> Any:
    """Drive the real validator with a resolvable base ref and no changed logs."""
    with patch("checks_tooling._resolve_branch_base_ref", return_value="origin/main"):
        with patch("checks_tooling._run_subprocess", side_effect=runner):
            return validate_session_end(repo_root)


class TestSessionEndRevision:
    """The revision on a PASS has to be one the reader can look up."""

    def test_a_readable_head_passes_and_names_the_real_sha(self, tmp_path: Path) -> None:
        """Positive control for the four failure cases below."""
        outcome = _run(tmp_path, _git_fake(rev_parse=(0, f"{_HEAD_SHA}\n", "")))

        assert outcome.state is EvidenceState.PASS
        assert outcome.revision == _HEAD_SHA
        assert outcome.examined == 0

    def test_a_failed_rev_parse_reports_unknown(self, tmp_path: Path) -> None:
        """The discriminating case: this was a PASS naming INVALID_HEAD."""
        outcome = _run(
            tmp_path,
            _git_fake(rev_parse=(128, "", "fatal: ambiguous argument 'HEAD'")),
        )

        assert outcome.state is EvidenceState.UNKNOWN
        assert outcome.reason == REASON_INCOMPLETE_EVIDENCE

    def test_a_timed_out_rev_parse_reports_the_timeout(self, tmp_path: Path) -> None:
        """Edge: the two ways rev-parse fails have different remedies.

        ``_run_subprocess`` reports a timeout and an ordinary git error with the
        same non-zero shape, and telling the reader "evidence incomplete" when
        the real finding is a hung git costs them the first diagnostic step.
        """
        outcome = _run(
            tmp_path,
            _git_fake(rev_parse=(-1, "", "Command timed out after 30s")),
        )

        assert outcome.state is EvidenceState.UNKNOWN
        assert outcome.reason == REASON_TIMEOUT

    def test_an_empty_rev_parse_stdout_reports_unknown(self, tmp_path: Path) -> None:
        """Edge: exit 0 with no output still names no revision.

        Reading only the exit code would let a zero-exit empty read through,
        which is the same placeholder defect reached from the other side.
        """
        outcome = _run(tmp_path, _git_fake(rev_parse=(0, "   \n", "")))

        assert outcome.state is EvidenceState.UNKNOWN

    def test_no_outcome_ever_carries_the_placeholder(self, tmp_path: Path) -> None:
        """The literal that made the defect possible must not survive anywhere.

        Asserting the state alone would still pass if some later branch
        reintroduced the sentinel, so this pins the string itself across every
        field a reader or a summary consumer can see.
        """
        for rev_parse in (
            (128, "", "fatal: not a git repository"),
            (0, "", ""),
            (-1, "", "Command timed out after 30s"),
        ):
            outcome = _run(tmp_path, _git_fake(rev_parse=rev_parse))

            assert "INVALID_HEAD" not in outcome.to_dict().values()
            assert "INVALID_HEAD" not in outcome.summary_line()

    def test_an_unreadable_head_is_not_licensed_by_the_pre_pr_policy(
        self, tmp_path: Path
    ) -> None:
        """UNKNOWN blocks. The policy licenses SKIP and two named BLOCKED rows.

        A licence here would restore the fail-open with extra steps: the gate
        would report a state it could not prove and the push would go through
        anyway.
        """
        outcome = _run(tmp_path, _git_fake(rev_parse=(128, "", "fatal:")))

        assert not default_pre_pr_policy().accepts(outcome)

    def test_the_scope_still_names_the_base_ref_it_compared_against(
        self, tmp_path: Path
    ) -> None:
        """A no-evidence state still has to say what it was trying to check."""
        outcome = _run(tmp_path, _git_fake(rev_parse=(128, "", "fatal:")))

        assert "origin/main" in outcome.scope

    def test_a_failed_diff_still_reports_its_own_reason(self, tmp_path: Path) -> None:
        """Edge: the diff is read first, so its failure short-circuits.

        The new rev-parse guard sits below the diff guard. Without this case, a
        change that hoisted it above would hand the reader ``evidence.incomplete``
        for a run whose real finding is a diff that would not resolve, and every
        other test here would still pass.
        """
        outcome = _run(
            tmp_path,
            _git_fake(
                diff=(128, "", "fatal: bad revision"),
                rev_parse=(0, f"{_HEAD_SHA}\n", ""),
            ),
        )

        assert outcome.state is EvidenceState.UNKNOWN
        assert outcome.reason == REASON_DIFF_FAILED
        assert outcome.revision == "origin/main...HEAD"
