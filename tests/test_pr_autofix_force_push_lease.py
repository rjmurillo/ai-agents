"""Agent-facing force-push instructions must pin the lease to an explicit SHA.

Bare ``--force-with-lease`` takes its expected value from
``refs/remotes/origin/<branch>``. Any concurrent ``git fetch`` advances that
tracking ref to the competing agent's commit, after which the lease passes and
the push destroys that agent's work.

Reproduced on a two-clone repo with a fetch between the two pushes: the bare
form overwrote the sibling's commit, while
``--force-with-lease=refs/heads/<branch>:<observed-sha>`` rejected the identical
push with ``stale info``.

See: issues #3653, #3413. ``.github/scripts/safe_push_pr_branch.py`` already
refuses ``--force-with-lease`` without ``--expected-remote-sha``; these tests
hold the hand-written command paths to the same contract.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]

# Every agent-facing document that hands out a force-push command.
GUARDED_DOCS = (
    ".claude/commands/pr-autofix.md",
    "docs/autonomous-pr-monitor.md",
    "src/copilot-cli/skills/pr-autofix/SKILL.md",
)

_REFSPEC_PUSH = re.compile(r"\bgit\s+push\b[^\n]*refs/heads/")
_BARE_LEASE = re.compile(r"--force-with-lease(?![=\w])")


def _join_continuations(text: str) -> str:
    """Collapse shell backslash-newline continuations onto one line.

    The guarded command wraps across two lines, so a naive per-line scan would
    see the ``git push`` and the ``--force-with-lease=`` separately and report a
    false positive.
    """
    return re.sub(r"\\\n\s*", " ", text)


def find_unpinned_force_pushes(text: str) -> list[str]:
    """Return refspec push commands that use ``--force-with-lease`` bare.

    Only lines that push an explicit ``refs/heads/`` refspec are considered.
    Prose that merely names the flag, and ordinary branch-name pushes covered by
    the git-advanced-workflows guidance, are out of scope for this guard.
    """
    offenders: list[str] = []
    for line in _join_continuations(text).splitlines():
        if _REFSPEC_PUSH.search(line) and _BARE_LEASE.search(line):
            offenders.append(line.strip())
    return offenders


class TestTheDetectorItself:
    """Isolating negative controls: prove the guard is not vacuous."""

    def test_a_bare_lease_on_a_refspec_push_is_caught(self):
        bad = 'git push origin "${SHA}:refs/heads/${BRANCH}" --force-with-lease --no-verify'
        assert find_unpinned_force_pushes(bad) == [bad]

    def test_a_pinned_lease_on_a_refspec_push_is_clean(self):
        good = (
            'git push origin "${SHA}:refs/heads/${BRANCH}" '
            '--force-with-lease="refs/heads/${BRANCH}:${EXPECTED_REMOTE_SHA}" --no-verify'
        )
        assert find_unpinned_force_pushes(good) == []

    def test_a_pinned_lease_split_across_a_continuation_is_clean(self):
        """The real command wraps; a per-line scan would false-positive here."""
        wrapped = (
            'git push origin "${SHA}:refs/heads/${BRANCH}" \\\n'
            '  --force-with-lease="refs/heads/${BRANCH}:${EXPECTED_REMOTE_SHA}" --no-verify'
        )
        assert find_unpinned_force_pushes(wrapped) == []

    def test_a_bare_lease_split_across_a_continuation_is_still_caught(self):
        """Two-sided control for the continuation handling above."""
        wrapped = (
            'git push origin "${SHA}:refs/heads/${BRANCH}" \\\n'
            "  --force-with-lease --no-verify"
        )
        assert len(find_unpinned_force_pushes(wrapped)) == 1

    def test_prose_naming_the_flag_is_not_a_push_command(self):
        prose = "Always use `--force-with-lease` when rewriting refs/heads/ history."
        assert find_unpinned_force_pushes(prose) == []

    def test_a_plain_branch_push_is_out_of_scope(self):
        """No refspec, so this guard stays silent by design."""
        other = "git push --force-with-lease origin feature/user-auth"
        assert find_unpinned_force_pushes(other) == []


@pytest.mark.parametrize("rel", GUARDED_DOCS)
def test_guarded_doc_pins_every_force_push_lease(rel: str):
    path = REPO_ROOT / rel
    assert path.is_file(), f"{rel} is missing; update GUARDED_DOCS"
    offenders = find_unpinned_force_pushes(path.read_text(encoding="utf-8"))
    assert not offenders, (
        f"{rel} hands agents a force-push whose lease is not pinned to an "
        f"explicit SHA: {offenders}. A concurrent fetch defeats the bare form "
        f"and the push destroys a sibling agent's commits (issues #3653, #3413)."
    )


@pytest.mark.parametrize("rel", GUARDED_DOCS)
def test_guarded_doc_actually_contains_a_force_push(rel: str):
    """Negative control: the guard above passes vacuously on a doc with no push."""
    text = (REPO_ROOT / rel).read_text(encoding="utf-8")
    assert _REFSPEC_PUSH.search(_join_continuations(text)), (
        f"{rel} no longer contains a refspec push, so the lease guard for it is "
        f"passing vacuously. Remove it from GUARDED_DOCS or restore the command."
    )
