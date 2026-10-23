"""Real ``git push`` through the installed pre-push hook (issue #6734, AC3).

Each test builds a throwaway repository and a bare ``origin``, installs the
pre-push shim that runs the policy jobs from the repository's own
``lefthook.yml`` (see ``hook_repo``), then pushes with plain ``git push``. A
clean push must land on the remote. A failing push must be refused, leave the
remote refs untouched, and leave the local HEAD, refs, index and worktree as
they were.

Cases: first push, outgoing ref and range handling (protected destination, ref
deletion from a ``main`` checkout, several refs, a pushed ref that is not the
checked-out one), and security failures.

Lefthook computes the pre-push file list as ``git diff --name-only HEAD
@{push}`` and skips every job when that list is empty. A test that needs the
hook to run therefore keeps the checked-out HEAD ahead of its push base.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from tests.integration.hook_repo import (
    LEFTHOOK,
    HookRepo,
    build_hook_repo,
    commit_without_hooks,
)

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(LEFTHOOK is None, reason="requires the lefthook binary"),
    pytest.mark.skipif(sys.platform == "win32", reason="hook fixture is verified on POSIX only"),
]

# Built at runtime so this file holds no suppression marker itself.
SUPPRESSED = "VALUE = 1  # no" + "sec\n"


@pytest.fixture
def hook_repo(tmp_path: Path) -> HookRepo:
    """A clone on ``feature/work`` with one unpushed commit and the hooks installed."""
    fixture = build_hook_repo(tmp_path)
    fixture.write("src/mod.py", "VALUE = 1\n")
    fixture.commit_all("feat: add module")
    # Verbose output names every job lefthook runs, so a push that succeeds
    # because the hook was skipped cannot pass for the wrong reason.
    fixture.env["LEFTHOOK_VERBOSE"] = "1"
    return fixture


_RAN_POLICY = "git_hook_policy.py pre-push"
_RAN_SUPPRESSIONS = "git_hook_policy.py security-suppressions-push"
_SUPPRESSION_ERROR = "security suppression comments detected in pushed commits"


def _landed(repo: HookRepo, *push_args: str) -> None:
    """Push, require success, and require that the push gates actually ran."""
    result = repo.git("push", *push_args, check=False)
    output = result.stdout + result.stderr
    assert result.returncode == 0, output
    assert _RAN_POLICY in output
    assert _RAN_SUPPRESSIONS in output


def _refused(repo: HookRepo, *push_args: str) -> str:
    """Push, require refusal, and require that nothing local changed."""
    before = repo.snapshot()
    result = repo.git("push", *push_args, check=False)
    assert result.returncode != 0, result.stdout + result.stderr
    assert repo.snapshot() == before
    return result.stdout + result.stderr


def test_first_push_of_a_new_branch_lands_on_the_remote(hook_repo: HookRepo) -> None:
    before = hook_repo.snapshot()

    _landed(hook_repo, "origin", "HEAD")

    assert hook_repo.remote_ref("refs/heads/feature/work") == hook_repo.out("rev-parse", "HEAD")
    assert hook_repo.snapshot().checkout_state() == before.checkout_state()


def test_docs_only_push_runs_the_ref_gates_and_no_python_gate(hook_repo: HookRepo) -> None:
    hook_repo.git("checkout", "-q", "-b", "feature/docs", "origin/main")
    hook_repo.write("docs/my notes.md", "# Notes\n\nplain text\n")
    hook_repo.commit_all("docs: add notes")
    before = hook_repo.snapshot()

    result = hook_repo.git("push", "origin", "HEAD", check=False)

    output = result.stdout + result.stderr
    assert result.returncode == 0, output
    assert _RAN_POLICY in output
    assert _RAN_SUPPRESSIONS in output
    assert "report_advisory_result.py" not in output
    assert hook_repo.remote_ref("refs/heads/feature/docs") == hook_repo.out("rev-parse", "HEAD")
    assert hook_repo.snapshot().checkout_state() == before.checkout_state()


def test_python_push_runs_the_python_gate(hook_repo: HookRepo) -> None:
    result = hook_repo.git("push", "origin", "HEAD", check=False)

    assert result.returncode == 0, result.stdout + result.stderr
    assert "report_advisory_result.py" in result.stdout + result.stderr


def test_update_of_main_from_a_feature_checkout_is_refused(hook_repo: HookRepo) -> None:
    main_before = hook_repo.remote_ref("refs/heads/main")

    output = _refused(hook_repo, "origin", "HEAD:refs/heads/main")

    assert "cannot delete or update protected branch 'main'" in output
    assert hook_repo.remote_ref("refs/heads/main") == main_before


def test_deleting_main_from_a_feature_checkout_is_refused(hook_repo: HookRepo) -> None:
    main_before = hook_repo.remote_ref("refs/heads/main")

    output = _refused(hook_repo, "origin", "--delete", "main")

    assert "cannot delete or update protected branch 'main'" in output
    assert hook_repo.remote_ref("refs/heads/main") == main_before


def test_a_main_checkout_may_delete_a_feature_branch_on_the_remote(hook_repo: HookRepo) -> None:
    """Issue #6671: the guard keys on the pushed ref, not on the checked-out branch."""
    hook_repo.git("push", "-q", "origin", "HEAD:refs/heads/feature/old")
    assert hook_repo.remote_ref("refs/heads/feature/old")
    # A main checkout that holds an unpushed commit, so lefthook has push files
    # and the hook runs instead of being skipped for an empty file list.
    hook_repo.git("checkout", "-q", "main")
    hook_repo.git("merge", "-q", "--ff-only", "feature/work")
    assert hook_repo.out("symbolic-ref", "--short", "HEAD") == "main"
    before = hook_repo.snapshot()

    _landed(hook_repo, "origin", "--delete", "feature/old")

    assert hook_repo.remote_ref("refs/heads/feature/old") == ""
    # The delete also prunes the remote-tracking ref, so refs may differ by that one.
    assert hook_repo.snapshot().checkout_state() == before.checkout_state()


def test_a_main_checkout_still_may_not_delete_main(hook_repo: HookRepo) -> None:
    hook_repo.git("checkout", "-q", "main")
    hook_repo.git("merge", "-q", "--ff-only", "feature/work")
    main_before = hook_repo.remote_ref("refs/heads/main")

    output = _refused(hook_repo, "origin", "--delete", "main")

    assert "cannot delete or update protected branch 'main'" in output
    assert hook_repo.remote_ref("refs/heads/main") == main_before


def test_a_push_of_several_feature_refs_lands_every_ref(hook_repo: HookRepo) -> None:
    hook_repo.git("branch", "feature/second")

    _landed(hook_repo, "origin", "feature/work", "feature/second")

    head = hook_repo.out("rev-parse", "HEAD")
    assert hook_repo.remote_ref("refs/heads/feature/work") == head
    assert hook_repo.remote_ref("refs/heads/feature/second") == head


@pytest.mark.parametrize("main_first", [True, False], ids=["main-first", "main-last"])
def test_one_protected_ref_refuses_the_whole_multi_ref_push(
    hook_repo: HookRepo,
    main_first: bool,
) -> None:
    hook_repo.git("branch", "feature/second")
    main_before = hook_repo.remote_ref("refs/heads/main")
    refs = ["HEAD:refs/heads/main", "feature/second:refs/heads/feature/second"]
    if not main_first:
        refs.reverse()

    output = _refused(hook_repo, "origin", *refs)

    assert "cannot delete or update protected branch 'main'" in output
    assert hook_repo.remote_ref("refs/heads/main") == main_before
    assert hook_repo.remote_ref("refs/heads/feature/second") == ""


def test_security_suppression_in_the_pushed_range_is_refused(hook_repo: HookRepo) -> None:
    commit_without_hooks(hook_repo, "src/mod.py", SUPPRESSED, "feat: suppress scanner")

    output = _refused(hook_repo, "origin", "HEAD")

    assert _SUPPRESSION_ERROR in output
    assert "src/mod.py" in output
    assert hook_repo.remote_ref("refs/heads/feature/work") == ""


def test_security_suppression_added_to_an_existing_remote_branch_is_refused(
    hook_repo: HookRepo,
) -> None:
    """The range is remote_sha..local_sha, so a later commit is checked on its own."""
    _landed(hook_repo, "origin", "HEAD")
    pushed = hook_repo.remote_ref("refs/heads/feature/work")
    commit_without_hooks(hook_repo, "src/mod.py", SUPPRESSED, "feat: suppress scanner")

    output = _refused(hook_repo, "origin", "HEAD")

    assert _SUPPRESSION_ERROR in output
    assert hook_repo.remote_ref("refs/heads/feature/work") == pushed


@pytest.mark.parametrize("bad_first", [True, False], ids=["bad-first", "bad-last"])
def test_one_suppressed_ref_refuses_the_whole_multi_ref_push(
    hook_repo: HookRepo,
    bad_first: bool,
) -> None:
    hook_repo.git("branch", "feature/clean")
    hook_repo.git("checkout", "-q", "-b", "feature/bad")
    commit_without_hooks(hook_repo, "src/bad.py", SUPPRESSED, "feat: suppress scanner")
    hook_repo.git("checkout", "-q", "feature/work")
    refs = ["feature/bad", "feature/clean"]
    if not bad_first:
        refs.reverse()

    output = _refused(hook_repo, "origin", *refs)

    assert _SUPPRESSION_ERROR in output
    assert hook_repo.remote_ref("refs/heads/feature/bad") == ""
    assert hook_repo.remote_ref("refs/heads/feature/clean") == ""


def test_the_pushed_ref_decides_the_range_not_the_checked_out_branch(
    hook_repo: HookRepo,
) -> None:
    """A suppression on another local branch is caught when that branch is pushed."""
    hook_repo.git("checkout", "-q", "-b", "feature/bad")
    commit_without_hooks(hook_repo, "src/bad.py", SUPPRESSED, "feat: suppress scanner")
    hook_repo.git("checkout", "-q", "feature/work")

    output = _refused(hook_repo, "origin", "feature/bad")

    assert _SUPPRESSION_ERROR in output
    assert "src/bad.py" in output
    assert hook_repo.remote_ref("refs/heads/feature/bad") == ""


def test_a_suppression_on_the_checked_out_branch_does_not_block_a_clean_ref(
    hook_repo: HookRepo,
) -> None:
    hook_repo.git("branch", "feature/clean")
    commit_without_hooks(hook_repo, "src/bad.py", SUPPRESSED, "feat: suppress scanner")

    _landed(hook_repo, "origin", "feature/clean")

    assert hook_repo.remote_ref("refs/heads/feature/clean") != ""
    assert hook_repo.remote_ref("refs/heads/feature/work") == ""


_SKIPPED_WHEN_LEVEL = pytest.mark.xfail(
    strict=True,
    reason="#6884: lefthook skips every pre-push job when HEAD is level with its push base",
)


@_SKIPPED_WHEN_LEVEL
def test_a_branch_level_with_its_upstream_cannot_update_main(hook_repo: HookRepo) -> None:
    hook_repo.git("push", "-q", "-u", "origin", "HEAD")
    main_before = hook_repo.remote_ref("refs/heads/main")

    output = _refused(hook_repo, "origin", "HEAD:refs/heads/main")

    assert "cannot delete or update protected branch 'main'" in output
    assert hook_repo.remote_ref("refs/heads/main") == main_before


@_SKIPPED_WHEN_LEVEL
def test_a_branch_level_with_its_upstream_cannot_push_another_ref_with_a_suppression(
    hook_repo: HookRepo,
) -> None:
    hook_repo.git("push", "-q", "-u", "origin", "HEAD")
    hook_repo.git("checkout", "-q", "-b", "feature/bad")
    commit_without_hooks(hook_repo, "src/bad.py", SUPPRESSED, "feat: suppress scanner")
    hook_repo.git("checkout", "-q", "feature/work")

    output = _refused(hook_repo, "origin", "feature/bad")

    assert _SUPPRESSION_ERROR in output
    assert hook_repo.remote_ref("refs/heads/feature/bad") == ""
