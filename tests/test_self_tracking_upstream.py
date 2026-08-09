"""Tests for self-tracking-upstream detection in scripts.validation.checks_common.

Covers the `_resolve_branch_base_ref` self-tracking-upstream regression
(issue #2571: `git push -u origin HEAD` makes `@{u}` resolve to the branch's
own tip, which pre_pr.py must not treat as a diff base) and
`_is_self_tracking_upstream` directly, including remotes other than `origin`.

`_gh_base_ref` probe/cache/reset tests live in `tests/test_gh_base_ref.py`;
the subprocess wrapper, remote-refresh helper, and build-script gate live in
`tests/test_checks_common.py`.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from scripts.validation.checks_common import (
    _is_self_tracking_upstream,
    _resolve_branch_base_ref,
)
from tests.gh_base_ref_test_helpers import _commit, _init_git_repo


class TestResolveBranchBaseRefSelfTracking:
    """Issue #2571: pre_pr.py missed changed workflow files that pre-push detected.

    When ``git push -u origin HEAD`` is used (the default workflow that VS Code,
    the GitHub CLI, and the documented contributor flow all rely on), the
    branch's upstream (``@{u}``) is the branch's own remote-tracking ref
    (e.g. ``origin/fix/2551-renovate-secret-guard``). After the push, that ref
    matches HEAD, so ``git diff --name-only @{u}...HEAD`` returns nothing and
    every gate that scoped itself to "changes since base" silently no-ops.

    The pre-push hook is unaffected because it computes the diff against the
    merge-base with ``origin/main`` directly from the push refs git provides on
    stdin, never the branch's configured upstream.

    The fix in ``_resolve_branch_base_ref`` is to skip ``@{u}`` when it
    resolves to the current branch's own remote-tracking ref and fall through
    to ``refs/remotes/origin/HEAD`` / ``origin/main``. Other ``@{u}`` values
    (e.g. a derivative branch tracking its parent feature branch) are still
    honoured.
    """

    def _make_clone_with_self_tracking_upstream(self, tmp_path: Path) -> Path:
        """Build a clone whose feature branch upstream is itself, post-push.

        Returns the local repo path. Layout:

          - ``remote/`` -- bare repo with one commit on ``main`` and a feature
            branch ``fix/2571-demo`` that already contains a workflow change.
          - ``local/`` -- clone of the bare remote with ``fix/2571-demo``
            checked out and configured to track ``origin/fix/2571-demo``.
        """
        remote_bare = tmp_path / "remote"
        remote_bare.mkdir()
        _init_git_repo(remote_bare, bare=True)

        seed = tmp_path / "seed"
        subprocess.run(
            ["git", "clone", str(remote_bare), str(seed)],
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Test User"],
            cwd=seed,
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.email", "test@example.com"],
            cwd=seed,
            check=True,
            capture_output=True,
        )
        _commit(seed, "README.md", "seed\n", "chore: seed")
        subprocess.run(
            ["git", "push", "origin", "main"],
            cwd=seed,
            check=True,
            capture_output=True,
        )

        # Branch off, change a workflow file, push -u (the default workflow).
        subprocess.run(
            ["git", "checkout", "-b", "fix/2571-demo"],
            cwd=seed,
            check=True,
            capture_output=True,
        )
        _commit(
            seed,
            ".github/workflows/dependabot-approve-and-auto-merge.yml",
            "name: demo\non: push\njobs: {}\n",
            "ci: add workflow",
        )
        subprocess.run(
            ["git", "push", "-u", "origin", "fix/2571-demo"],
            cwd=seed,
            check=True,
            capture_output=True,
        )

        # Now produce the working clone that contributors actually run pre_pr from.
        local = tmp_path / "local"
        subprocess.run(
            ["git", "clone", str(remote_bare), str(local)],
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Test User"],
            cwd=local,
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.email", "test@example.com"],
            cwd=local,
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "checkout", "-b", "fix/2571-demo", "origin/fix/2571-demo"],
            cwd=local,
            check=True,
            capture_output=True,
        )
        # ``checkout -b ... origin/<branch>`` already sets upstream to
        # origin/<branch>; assert that as a precondition for the test.
        upstream = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"],
            cwd=local,
            check=True,
            capture_output=True,
            encoding="utf-8",
        ).stdout.strip()
        assert upstream == "origin/fix/2571-demo", (
            f"precondition: branch must self-track, got {upstream!r}"
        )
        return local

    def test_falls_through_self_tracking_upstream_so_diff_sees_branch_changes(
        self, tmp_path: Path
    ) -> None:
        """RED for Issue #2571: a self-tracking upstream must not be the diff base.

        With the bug, ``_resolve_branch_base_ref`` returns ``@{u}`` even when
        ``@{u}`` is the branch's own ``origin/<branch>``, and the resulting
        ``git diff <base>...HEAD`` returns no files -- pre_pr's workflow gate
        false-PASSes the changed ``.github/workflows/*.yml`` file. The fix
        falls through to ``refs/remotes/origin/HEAD`` (which resolves to
        ``origin/main`` here) so the diff actually shows the workflow file.
        """
        local = self._make_clone_with_self_tracking_upstream(tmp_path)

        # Sanity: with the buggy resolution (@{u}=origin/fix/2571-demo) the
        # diff is empty. With the correct resolution it contains the workflow.
        diff_against_self = subprocess.run(
            ["git", "diff", "--name-only", "origin/fix/2571-demo...HEAD"],
            cwd=local,
            capture_output=True,
            encoding="utf-8",
            check=True,
        ).stdout.strip()
        assert diff_against_self == "", (
            "precondition: self-tracking diff is empty, so the gate that "
            "uses this base would falsely report no changes"
        )

        base_ref = _resolve_branch_base_ref(local)

        # The point of the fix: do not hand back the branch's own
        # origin/<branch> ref, because that produces a useless diff range
        # post-push. Either of the trunk-pointing fallbacks is acceptable.
        assert base_ref not in (
            "@{u}",
            "origin/fix/2571-demo",
        ), (
            f"_resolve_branch_base_ref returned a self-tracking upstream "
            f"({base_ref!r}); pre_pr would compute an empty diff and miss "
            "changed workflow files (Issue #2571)."
        )

        # Verify the resolved base produces a non-empty diff containing the
        # workflow file (the contract callers depend on).
        diff_against_resolved = (
            subprocess.run(
                ["git", "diff", "--name-only", f"{base_ref}...HEAD"],
                cwd=local,
                capture_output=True,
                encoding="utf-8",
                check=True,
            )
            .stdout.strip()
            .splitlines()
        )
        assert ".github/workflows/dependabot-approve-and-auto-merge.yml" in diff_against_resolved, (
            "Resolved base ref must yield a diff range that contains the "
            "changed workflow file; got: "
            f"{diff_against_resolved!r}"
        )

    def test_honours_non_self_tracking_upstream(self, tmp_path: Path) -> None:
        """Derivative branches tracking a parent feature branch must still use @{u}.

        Counter-test for the fix: if a branch's upstream is some OTHER ref
        (the parent feature branch in a derivative-PR workflow), the resolver
        must still return ``@{u}``. Falling all the way through to
        ``origin/main`` here would pull in the parent feature branch's
        commits as "changes" and false-PASS / false-FAIL downstream gates.
        """
        remote_bare = tmp_path / "remote"
        remote_bare.mkdir()
        _init_git_repo(remote_bare, bare=True)

        seed = tmp_path / "seed"
        subprocess.run(
            ["git", "clone", str(remote_bare), str(seed)],
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Test User"],
            cwd=seed,
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.email", "test@example.com"],
            cwd=seed,
            check=True,
            capture_output=True,
        )
        _commit(seed, "README.md", "seed\n", "chore: seed")
        subprocess.run(
            ["git", "push", "origin", "main"],
            cwd=seed,
            check=True,
            capture_output=True,
        )

        # Build a parent feature branch and a derivative branch off it.
        subprocess.run(
            ["git", "checkout", "-b", "feat/parent"],
            cwd=seed,
            check=True,
            capture_output=True,
        )
        _commit(seed, "parent.txt", "parent\n", "feat: parent work")
        subprocess.run(
            ["git", "push", "-u", "origin", "feat/parent"],
            cwd=seed,
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "checkout", "-b", "feat/derivative"],
            cwd=seed,
            check=True,
            capture_output=True,
        )
        _commit(seed, "derivative.txt", "derivative\n", "feat: derivative")
        # The derivative branch tracks feat/parent, NOT itself.
        subprocess.run(
            [
                "git",
                "branch",
                "--set-upstream-to=origin/feat/parent",
                "feat/derivative",
            ],
            cwd=seed,
            check=True,
            capture_output=True,
        )

        upstream = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"],
            cwd=seed,
            check=True,
            capture_output=True,
            encoding="utf-8",
        ).stdout.strip()
        assert upstream == "origin/feat/parent", (
            f"precondition: derivative branch must track parent feature, got {upstream!r}"
        )

        base_ref = _resolve_branch_base_ref(seed)
        assert base_ref == "@{u}", (
            f"Derivative branches with a non-self upstream must keep using "
            f"@{{u}}; got {base_ref!r}. Otherwise the parent feature branch's "
            "commits get counted as part of the derivative's diff."
        )


class TestIsSelfTrackingUpstreamAnyRemote:
    """``_is_self_tracking_upstream`` must not assume the remote is named
    ``origin``, and must not misparse branch names containing ``/`` by
    string-splitting the abbreviated ``@{u}`` output (which has no marked
    boundary between a remote name and a branch name once both can contain
    slashes). Detection instead compares ``branch.<branch>.merge`` (via
    ``_upstream_head_ref_name``) directly to the branch name.
    """

    @staticmethod
    def _push_new_branch(local: Path, remote_name: str, branch: str) -> None:
        subprocess.run(
            ["git", "push", "-u", remote_name, branch],
            cwd=local,
            check=True,
            capture_output=True,
        )

    def test_detects_self_tracking_on_a_non_origin_remote(self, tmp_path: Path) -> None:
        remote_bare = tmp_path / "remote"
        remote_bare.mkdir()
        _init_git_repo(remote_bare, bare=True)

        local = tmp_path / "local"
        local.mkdir()
        _init_git_repo(local)
        _commit(local, "a.txt", "a\n", "chore: seed")
        subprocess.run(
            ["git", "remote", "add", "upstream", str(remote_bare)],
            cwd=local,
            check=True,
            capture_output=True,
        )
        self._push_new_branch(local, "upstream", "main")

        # Precondition: the abbreviated @{u} names the non-origin remote,
        # proving this scenario would defeat a hardcoded "origin/" compare.
        upstream = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"],
            cwd=local,
            check=True,
            capture_output=True,
            encoding="utf-8",
        ).stdout.strip()
        assert upstream == "upstream/main", f"precondition failed, got {upstream!r}"

        assert _is_self_tracking_upstream(local) is True

    def test_detects_self_tracking_with_slashes_in_the_branch_name(self, tmp_path: Path) -> None:
        remote_bare = tmp_path / "remote"
        remote_bare.mkdir()
        _init_git_repo(remote_bare, bare=True)

        local = tmp_path / "local"
        local.mkdir()
        _init_git_repo(local)
        _commit(local, "a.txt", "a\n", "chore: seed")
        subprocess.run(
            ["git", "remote", "add", "upstream", str(remote_bare)],
            cwd=local,
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "checkout", "-b", "feature/sub/branch"],
            cwd=local,
            check=True,
            capture_output=True,
        )
        self._push_new_branch(local, "upstream", "feature/sub/branch")

        # Precondition: two slashes on each side of the abbreviated form --
        # string-splitting on "/" cannot tell where the remote name ends.
        upstream = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"],
            cwd=local,
            check=True,
            capture_output=True,
            encoding="utf-8",
        ).stdout.strip()
        assert upstream == "upstream/feature/sub/branch", f"precondition failed, got {upstream!r}"

        assert _is_self_tracking_upstream(local) is True

    def test_non_self_tracking_on_a_non_origin_remote_returns_false(self, tmp_path: Path) -> None:
        """A derivative branch tracking a differently named ref on a
        non-origin remote must not be misclassified as self-tracking."""
        remote_bare = tmp_path / "remote"
        remote_bare.mkdir()
        _init_git_repo(remote_bare, bare=True)

        local = tmp_path / "local"
        local.mkdir()
        _init_git_repo(local)
        _commit(local, "a.txt", "a\n", "chore: seed")
        subprocess.run(
            ["git", "remote", "add", "upstream", str(remote_bare)],
            cwd=local,
            check=True,
            capture_output=True,
        )
        self._push_new_branch(local, "upstream", "main")
        subprocess.run(
            ["git", "checkout", "-b", "feature/derivative"],
            cwd=local,
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "branch", "--set-upstream-to=upstream/main", "feature/derivative"],
            cwd=local,
            check=True,
            capture_output=True,
        )

        assert _is_self_tracking_upstream(local) is False
