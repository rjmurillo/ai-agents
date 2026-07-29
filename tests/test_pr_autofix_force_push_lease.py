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

import os
import re
import subprocess
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


# ---------------------------------------------------------------------------
# Concurrency regression (issue #3413 acceptance criterion)
#
# "A concurrency regression proves only one of two same-user agents can mutate
# a PR branch." These two tests are the two-sided control: the bare lease loses
# a sibling's commit, the pinned lease refuses the identical push.
# ---------------------------------------------------------------------------


def _git(args: list[str], cwd: Path, check: bool = True):
    env = os.environ.copy()
    env["LC_ALL"] = "C"
    return subprocess.run(
        # init.defaultBranch is pinned to "master" on purpose. A stock runner
        # ships that default, and pinning it here means these tests keep
        # exercising the hostile configuration rather than whatever the
        # developer happens to have set. Remove --initial-branch=main below and
        # this pin turns the setup red again.
        ["git", "-c", "init.defaultBranch=master", *args],
        cwd=cwd,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        env=env,
        check=check,
    )


def _identify(clone: Path, who: str) -> None:
    _git(["config", "user.email", f"{who}@example.invalid"], clone)
    _git(["config", "user.name", who], clone)


@pytest.fixture
def two_agents(tmp_path: Path):
    """One shared remote and two clones racing to mutate the same branch.

    Returns ``(agent_a, agent_b, origin, observed_sha)`` where ``observed_sha``
    is the branch tip agent B last reasoned about, exactly the value the
    pr-autofix instructions read from ``get_pr_context.py``.
    """
    origin = tmp_path / "origin.git"
    # --initial-branch is load-bearing, not decoration. Without it the bare
    # repo's HEAD follows init.defaultBranch, which is "master" on a stock
    # runner. Agent A then pushes "main", leaving origin's HEAD pointing at an
    # unborn ref, and agent B's clone lands on an unborn HEAD where
    # "rev-parse HEAD" exits 128.
    _git(["init", "--quiet", "--bare", "--initial-branch=main", str(origin)], tmp_path)

    agent_a = tmp_path / "agent_a"
    _git(["clone", "--quiet", str(origin), str(agent_a)], tmp_path)
    _identify(agent_a, "agent-a")
    (agent_a / "f.txt").write_text("base\n")
    _git(["add", "f.txt"], agent_a)
    _git(["commit", "--quiet", "-m", "base"], agent_a)
    _git(["branch", "-M", "main"], agent_a)
    _git(["push", "--quiet", "origin", "main"], agent_a)

    agent_b = tmp_path / "agent_b"
    _git(["clone", "--quiet", str(origin), str(agent_b)], tmp_path)
    _identify(agent_b, "agent-b")
    observed_sha = _git(["rev-parse", "HEAD"], agent_b).stdout.strip()

    # Agent A lands work that agent B has not seen.
    (agent_a / "f.txt").write_text("base\nagent-a work\n")
    _git(["commit", "--quiet", "-am", "agent-a work"], agent_a)
    _git(["push", "--quiet", "origin", "main"], agent_a)

    # Agent B builds a divergent commit, then something fetches. This is the
    # documented defeat condition: B's origin/main now points at A's commit.
    (agent_b / "f.txt").write_text("base\nagent-b work\n")
    _git(["commit", "--quiet", "-am", "agent-b work"], agent_b)
    _git(["fetch", "--quiet", "origin"], agent_b)

    return agent_a, agent_b, origin, observed_sha


def _remote_tip(cwd: Path) -> str:
    out = _git(["ls-remote", "origin", "main"], cwd).stdout
    return out.split("\t")[0].strip()


def test_bare_lease_lets_one_agent_destroy_another(two_agents):
    """Hazard control. Without this passing, the fix has nothing to prevent.

    Pushes to the remote *name*, not a URL. Bare ``--force-with-lease`` reads its
    expected value from ``refs/remotes/origin/main``; pushing to a bare path has
    no tracking ref, so git refuses for an unrelated reason and the hazard would
    never reproduce. The real pr-autofix command pushes to ``origin``.
    """
    agent_a, agent_b, _origin, _ = two_agents
    victim = _git(["rev-parse", "HEAD"], agent_a).stdout.strip()
    pushed = _git(["rev-parse", "HEAD"], agent_b).stdout.strip()

    result = _git(
        ["push", "--force-with-lease", "origin", f"{pushed}:refs/heads/main"],
        agent_b,
        check=False,
    )

    assert result.returncode == 0, "bare lease unexpectedly blocked; re-derive the hazard"
    assert _remote_tip(agent_b) != victim, (
        "bare --force-with-lease overwrote the sibling's commit, which is the "
        "hazard this guard exists to prevent (issues #3653, #3413)"
    )


def test_pinned_lease_refuses_to_destroy_another_agents_commit(two_agents):
    """The fix. Identical push, lease pinned to the SHA agent B observed."""
    agent_a, agent_b, _origin, observed_sha = two_agents
    victim = _git(["rev-parse", "HEAD"], agent_a).stdout.strip()
    pushed = _git(["rev-parse", "HEAD"], agent_b).stdout.strip()

    result = _git(
        [
            "push",
            f"--force-with-lease=refs/heads/main:{observed_sha}",
            "origin",
            f"{pushed}:refs/heads/main",
        ],
        agent_b,
        check=False,
    )

    assert result.returncode != 0, "pinned lease should have rejected a stale push"
    assert "stale info" in (result.stderr + result.stdout).lower()
    assert _remote_tip(agent_b) == victim, "the sibling's commit must survive"
