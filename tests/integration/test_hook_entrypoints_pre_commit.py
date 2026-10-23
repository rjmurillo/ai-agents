"""Real ``git commit`` through the installed pre-commit hook (issue #6734, AC3).

Each test builds a throwaway repository whose pre-commit shim runs the cheap
policy jobs from the repository's own ``lefthook.yml`` (see ``hook_repo``), then
commits with plain ``git commit``. A clean input must commit exactly the staged
content and leave every unstaged edit alone. A failing input must be refused
and leave HEAD, refs, index, stash and every worktree byte as they were.

Cases: partial staging, docs-only changes, and security failures.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from tests.integration.hook_repo import LEFTHOOK, HookRepo, build_hook_repo

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(LEFTHOOK is None, reason="requires the lefthook binary"),
    pytest.mark.skipif(sys.platform == "win32", reason="hook fixture is verified on POSIX only"),
]

# Built at runtime so this file holds neither a dash nor a suppression marker itself.
EM_DASH = chr(0x2014)
SUPPRESSION = "# no" + "sec"


@pytest.fixture
def hook_repo(tmp_path: Path) -> HookRepo:
    return build_hook_repo(tmp_path)


def _committed(repo: HookRepo, path: str) -> str:
    return repo.out("show", f"HEAD:{path}")


def _unstaged_diff(repo: HookRepo) -> str:
    return repo.out("diff")


def test_partial_staging_commits_the_staged_fix_and_keeps_the_unstaged_edit(
    hook_repo: HookRepo,
) -> None:
    """python-autofix rewrites the staged copy only (lefthook stage_fixed)."""
    hook_repo.write("src/app.py", "VALUE = 1\n")
    hook_repo.commit_all("feat: add app")
    hook_repo.write("src/app.py", "import os\nVALUE = 1\n")
    hook_repo.stage("src/app.py")
    hook_repo.write("src/app.py", "import os\nVALUE = 1\nUNSTAGED = 2\n")

    result = hook_repo.git("commit", "-q", "-m", "feat: stage one hunk", check=False)

    assert result.returncode == 0, result.stdout + result.stderr
    assert _committed(hook_repo, "src/app.py") == "VALUE = 1"
    assert (hook_repo.repo / "src/app.py").read_text(encoding="utf-8") == (
        "VALUE = 1\nUNSTAGED = 2\n"
    )
    assert "+UNSTAGED = 2" in _unstaged_diff(hook_repo)
    assert hook_repo.out("diff", "--cached") == ""
    assert hook_repo.out("stash", "list") == ""


def test_partial_staging_refuses_a_staged_violation_and_changes_nothing(
    hook_repo: HookRepo,
) -> None:
    hook_repo.write("docs/guide.md", "# Guide\n\none\ntwo\n")
    hook_repo.commit_all("docs: add guide")
    hook_repo.write("docs/guide.md", f"# Guide\n\none {EM_DASH} bad\ntwo\n")
    hook_repo.stage("docs/guide.md")
    hook_repo.write("docs/guide.md", f"# Guide\n\none {EM_DASH} bad\ntwo edited\n")
    before = hook_repo.snapshot()

    result = hook_repo.git("commit", "-q", "-m", "docs: dash", check=False)

    assert result.returncode != 0
    assert "docs/guide.md" in result.stdout + result.stderr
    assert hook_repo.snapshot() == before
    assert not (hook_repo.repo / ".git/index.lock").exists()


def test_partial_staging_ignores_a_violation_that_exists_only_in_the_worktree(
    hook_repo: HookRepo,
) -> None:
    """The gate reads the index, so an unstaged violation neither blocks nor lands."""
    hook_repo.write("docs/guide.md", "# Guide\n\none\ntwo\n")
    hook_repo.commit_all("docs: add guide")
    hook_repo.write("docs/guide.md", "# Guide\n\none clean\ntwo\n")
    hook_repo.stage("docs/guide.md")
    unstaged = f"# Guide\n\none clean\ntwo {EM_DASH}\n"
    hook_repo.write("docs/guide.md", unstaged)

    result = hook_repo.git("commit", "-q", "-m", "docs: clean half", check=False)

    assert result.returncode == 0, result.stdout + result.stderr
    assert _committed(hook_repo, "docs/guide.md") == "# Guide\n\none clean\ntwo"
    assert (hook_repo.repo / "docs/guide.md").read_text(encoding="utf-8") == unstaged
    assert EM_DASH in _unstaged_diff(hook_repo)


def test_docs_only_commit_runs_no_python_gate(hook_repo: HookRepo) -> None:
    hook_repo.env["LEFTHOOK_VERBOSE"] = "1"
    hook_repo.write("docs/my notes.md", "# Notes\n\nplain text\n")
    hook_repo.stage("docs/my notes.md")

    result = hook_repo.git("commit", "-q", "-m", "docs: add notes", check=False)

    output = result.stdout + result.stderr
    assert result.returncode == 0, output
    assert _committed(hook_repo, "docs/my notes.md") == "# Notes\n\nplain text"
    assert "git_hook_policy.py staged-dashes 'docs/my notes.md'" in output
    assert "report_advisory_result.py" not in output
    assert "ruff" not in output
    assert hook_repo.out("status", "--porcelain") == ""


def test_docs_only_commit_refuses_a_dash_and_changes_nothing(hook_repo: HookRepo) -> None:
    hook_repo.write("docs/my notes.md", f"# Notes\n\nbad {EM_DASH} text\n")
    hook_repo.stage("docs/my notes.md")
    hook_repo.write("README.md", "# Fixture\n\nunstaged note\n")
    before = hook_repo.snapshot()

    result = hook_repo.git("commit", "-q", "-m", "docs: dash", check=False)

    assert result.returncode != 0
    assert "docs/my notes.md" in result.stdout + result.stderr
    assert hook_repo.snapshot() == before


@pytest.mark.parametrize("worktree_reverted", [False, True], ids=["kept", "reverted-after-staging"])
def test_staged_security_suppression_is_refused_and_changes_nothing(
    hook_repo: HookRepo,
    worktree_reverted: bool,
) -> None:
    """Silencing a scanner is refused from the index, not from the worktree copy."""
    hook_repo.write("src/mod.py", "VALUE = 1\n")
    hook_repo.commit_all("feat: add module")
    hook_repo.write("src/mod.py", f"VALUE = 1  {SUPPRESSION}\n")
    hook_repo.stage("src/mod.py")
    if worktree_reverted:
        hook_repo.write("src/mod.py", "VALUE = 1\n")
    before = hook_repo.snapshot()

    result = hook_repo.git("commit", "-q", "-m", "feat: suppress", check=False)

    assert result.returncode != 0
    assert "security suppression comments detected" in result.stdout + result.stderr
    assert hook_repo.snapshot() == before


def test_conflict_markers_in_a_partially_staged_python_file_change_nothing(
    hook_repo: HookRepo,
) -> None:
    """python-autofix runs first on the same file and must not disturb the refusal."""
    hook_repo.write("src/mod.py", "VALUE = 1\n")
    hook_repo.commit_all("feat: add module")
    marked = "<<<<<<< ours\nVALUE = 2\n=======\nVALUE = 3\n>>>>>>> theirs\n"
    hook_repo.write("src/mod.py", marked)
    hook_repo.stage("src/mod.py")
    hook_repo.write("src/mod.py", marked + "UNSTAGED = 2\n")
    before = hook_repo.snapshot()

    result = hook_repo.git("commit", "-q", "-m", "feat: markers", check=False)

    assert result.returncode != 0
    assert "git conflict markers" in result.stdout + result.stderr
    assert hook_repo.snapshot() == before
