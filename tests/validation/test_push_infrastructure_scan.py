"""Pre-push security marker gate scores merge-base(origin/main, pushed SHA) (issue #6076).

Lefthook ``{push_files}`` diffed a new branch against the local ``main`` ref.
When local ``main`` was stale, main's own infrastructure changes counted as the
branch's and ``detect_infrastructure.py --require-security-review`` blocked the
push for files the branch never touched. ``check_push_refs`` now runs the gate
per pushed ref from immutable SHAs. Every test drives ``main(argv)`` against a
real clone of a local bare ``origin``, so the hook's own ``git fetch`` runs.
"""

from __future__ import annotations

import io
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.validation import git_hook_policy as policy

REPO_ROOT = Path(__file__).resolve().parents[2]
DETECTOR = ".claude/skills/security-detection/detect_infrastructure.py"
MARKER_VALIDATOR = "scripts/validation/validate_review_marker.py"
ZERO = "0" * 40
WORKFLOW = ".github/workflows/ci.yml"


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(  # subprocess-encoding: strict-ok
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    )
    return result.stdout.strip()


def _configure(repo: Path, hooks: Path) -> None:
    _git(repo, "config", "user.name", "Test User")
    _git(repo, "config", "user.email", "user@example.com")
    _git(repo, "config", "commit.gpgsign", "false")
    _git(repo, "config", "core.hooksPath", str(hooks))


def _commit(repo: Path, relative_path: str, content: str) -> str:
    path = repo / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content.encode("utf-8"))
    _git(repo, "add", "--", relative_path)
    _git(repo, "commit", "-qm", f"test: {relative_path}")
    return _git(repo, "rev-parse", "HEAD")


def _marker(repo: Path) -> str:
    parent = _git(repo, "rev-parse", "HEAD")
    _git(
        repo,
        "commit",
        "-q",
        "--allow-empty",
        "-m",
        "review: /review PASS marker",
        "--trailer",
        f"Reviewed-By: /review@analyst,security on {parent}",
    )
    return _git(repo, "rev-parse", "HEAD")


def _install_scripts(repo: Path, *, detector: bool = True) -> None:
    """Place the scripts the hook runs by repo-relative path, untracked."""
    names = [MARKER_VALIDATOR, *([DETECTOR] if detector else [])]
    for name in names:
        target = repo / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(REPO_ROOT / name, target)
    exclude = repo / ".git/info/exclude"
    exclude.write_text("scripts/\n.claude/\n", encoding="utf-8")


class Origin:
    """A bare ``origin`` plus a seed clone that advances ``main`` on it."""

    def __init__(self, tmp_path: Path) -> None:
        self.hooks = tmp_path / "no-hooks"
        self.hooks.mkdir()
        self.bare = tmp_path / "origin.git"
        subprocess.run(
            ["git", "init", "-q", "--bare", "-b", "main", str(self.bare)],
            check=True,
            capture_output=True,
        )
        self.seed = tmp_path / "seed"
        self.clone(self.seed)
        _commit(self.seed, "README.md", "base\n")
        _git(self.seed, "push", "-q", "origin", "HEAD:main")

    def clone(self, target: Path) -> Path:
        subprocess.run(
            ["git", "clone", "-q", str(self.bare), str(target)],
            check=True,
            capture_output=True,
        )
        _configure(target, self.hooks)
        return target

    def advance_main(self, relative_path: str) -> str:
        _git(self.seed, "pull", "-q", "--ff-only", "origin", "main")
        sha = _commit(self.seed, relative_path, f"{relative_path}\n")
        _git(self.seed, "push", "-q", "origin", "HEAD:main")
        return sha


@pytest.fixture
def origin(tmp_path: Path) -> Origin:
    return Origin(tmp_path)


def _work(origin: Origin, tmp_path: Path, *, detector: bool = True) -> Path:
    work = origin.clone(tmp_path / "work")
    _install_scripts(work, detector=detector)
    return work


def _pre_push(repo: Path, payload: str, monkeypatch: pytest.MonkeyPatch) -> int:
    monkeypatch.setattr("sys.stdin", io.StringIO(payload))
    return policy.main(["--repo-root", str(repo), "pre-push"])


def _new_branch_line(branch: str, sha: str) -> str:
    return f"refs/heads/{branch} {sha} refs/heads/{branch} {ZERO}\n"


def test_stale_local_main_scores_only_the_branch_files(
    origin: Origin,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """AC1: main's own workflow change must not count as the branch's."""
    work = _work(origin, tmp_path)
    stale_main = _git(work, "rev-parse", "main")
    origin.advance_main(WORKFLOW)
    _git(work, "fetch", "-q", "origin")
    _git(work, "checkout", "-q", "-b", "feature/docs", "origin/main")
    head = _commit(work, "docs/note.md", "note\n")
    assert _git(work, "rev-parse", "main") == stale_main

    # Negative control: the old input, a two-dot diff against local `main`,
    # carries the workflow the branch never touched, and the detector blocks it.
    old_files = _git(work, "diff", "--name-only", "main", head).splitlines()
    assert WORKFLOW in old_files
    old = subprocess.run(  # subprocess-encoding: strict-ok
        [
            sys.executable,
            str(work / DETECTOR),
            "--require-security-review",
            "--repo-root",
            str(work),
            "--files",
            *old_files,
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    assert old.returncode == 1, old.stdout + old.stderr

    result = _pre_push(work, _new_branch_line("feature/docs", head), monkeypatch)

    err = capsys.readouterr().err
    assert result == 0, err
    assert "refs/heads/feature/docs scores 1 file(s)" in err


def test_fresh_branch_with_workflow_change_and_no_marker_is_blocked(
    origin: Origin,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """AC2 and AC6: the branch's own CRITICAL file still requires a marker."""
    work = _work(origin, tmp_path)
    _git(work, "checkout", "-q", "-b", "feature/ci")
    head = _commit(work, WORKFLOW, "on: push\n")

    result = _pre_push(work, _new_branch_line("feature/ci", head), monkeypatch)

    captured = capsys.readouterr()
    assert result == 1, captured.err
    assert "scores 1 file(s)" in captured.err
    assert "CRITICAL change without a security review marker" in captured.err
    assert WORKFLOW in captured.out


def test_marker_is_read_from_the_pushed_sha_not_checked_out_head(
    origin: Origin,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """AC7: a reviewed branch pushed from another checkout passes on its own marker."""
    work = _work(origin, tmp_path)
    _git(work, "checkout", "-q", "-b", "feature/ci")
    _commit(work, WORKFLOW, "on: push\n")
    marker = _marker(work)
    _git(work, "checkout", "-q", "-b", "other", "origin/main")
    line = _new_branch_line("feature/ci", marker)

    reviewed = _pre_push(work, line, monkeypatch)
    reviewed_err = capsys.readouterr().err
    _git(work, "checkout", "-q", "feature/ci")
    unreviewed = _commit(work, "docs/after.md", "after\n")
    _git(work, "checkout", "-q", "other")
    stale = _pre_push(work, _new_branch_line("feature/ci", unreviewed), monkeypatch)

    assert reviewed == 0, reviewed_err
    assert "scores 1 file(s)" in reviewed_err
    assert stale == 1


def test_incremental_push_after_merging_main_scores_only_branch_files(
    origin: Origin,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """AC3: an existing remote branch that merged main is not charged for main."""
    work = _work(origin, tmp_path)
    _git(work, "checkout", "-q", "-b", "feature/docs")
    pushed = _commit(work, "docs/one.md", "one\n")
    _git(work, "push", "-q", "origin", "feature/docs")
    origin.advance_main(WORKFLOW)
    _git(work, "fetch", "-q", "origin")
    _git(work, "merge", "-q", "--no-edit", "origin/main")
    head = _commit(work, "docs/two.md", "two\n")
    # The remote tip to HEAD range, which lefthook uses for an existing
    # branch, carries main's workflow in through the merge.
    assert WORKFLOW in _git(work, "diff", "--name-only", pushed, head).splitlines()
    line = f"refs/heads/feature/docs {head} refs/heads/feature/docs {pushed}\n"

    result = _pre_push(work, line, monkeypatch)

    err = capsys.readouterr().err
    assert result == 0, err
    assert "refs/heads/feature/docs scores 2 file(s)" in err


def test_incremental_push_rescans_files_from_earlier_pushes(
    origin: Origin,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """AC3: a new commit moves the branch off its marker, so the marker dies."""
    work = _work(origin, tmp_path)
    _git(work, "checkout", "-q", "-b", "feature/ci")
    _commit(work, WORKFLOW, "on: push\n")
    pushed = _marker(work)
    _git(work, "push", "-q", "origin", "feature/ci")
    head = _commit(work, "docs/later.md", "later\n")
    line = f"refs/heads/feature/ci {head} refs/heads/feature/ci {pushed}\n"

    result = _pre_push(work, line, monkeypatch)

    err = capsys.readouterr().err
    assert result == 1, err
    assert "scores 2 file(s)" in err


def test_deletion_only_push_scores_nothing_and_says_so(
    origin: Origin,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """AC4: a deletion carries no commits, and the skip is reported, not silent."""
    work = _work(origin, tmp_path)
    _git(work, "checkout", "-q", "-b", "feature/gone")
    old = _commit(work, WORKFLOW, "on: push\n")
    line = f"(delete) {ZERO} refs/heads/feature/gone {old}\n"

    result = _pre_push(work, line, monkeypatch)

    err = capsys.readouterr().err
    assert result == 0, err
    assert "Infrastructure scan: skipped, no branch ref in this push carries commits" in err


def test_missing_origin_main_fails_loud_instead_of_using_local_main(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """AC5: no origin/main means no base; local main is not a substitute."""
    hooks = tmp_path / "no-hooks"
    hooks.mkdir()
    work = tmp_path / "work"
    work.mkdir()
    _git(work, "init", "-q", "-b", "main")
    _configure(work, hooks)
    _install_scripts(work)
    _commit(work, "README.md", "base\n")
    _git(work, "checkout", "-q", "-b", "feature/docs")
    head = _commit(work, "docs/note.md", "note\n")

    result = _pre_push(work, _new_branch_line("feature/docs", head), monkeypatch)

    err = capsys.readouterr().err
    assert result == 2, err
    assert "could not resolve merge-base(origin/main" in err
    assert "scores" not in err


def test_unrelated_history_fails_loud_instead_of_scoring_the_whole_tree(
    origin: Origin,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """AC5: no merge-base means no base; the empty tree is not a substitute."""
    work = _work(origin, tmp_path)
    _git(work, "checkout", "-q", "--orphan", "feature/orphan")
    _git(work, "rm", "-rq", "--cached", ".")
    head = _commit(work, "docs/orphan.md", "orphan\n")

    result = _pre_push(work, _new_branch_line("feature/orphan", head), monkeypatch)

    err = capsys.readouterr().err
    assert result == 2, err
    assert "could not resolve merge-base(origin/main" in err


def test_missing_detector_fails_the_push(
    origin: Origin,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A detector that cannot run is not a detector that found nothing."""
    work = _work(origin, tmp_path, detector=False)
    _git(work, "checkout", "-q", "-b", "feature/docs")
    head = _commit(work, "docs/note.md", "note\n")

    result = _pre_push(work, _new_branch_line("feature/docs", head), monkeypatch)

    assert result != 0, capsys.readouterr().err


def test_push_with_no_changed_files_skips_the_detector_and_reports_zero(
    origin: Origin,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A branch at origin/main scores zero files, reported, without the detector."""
    work = _work(origin, tmp_path, detector=False)
    _git(work, "checkout", "-q", "-b", "feature/empty", "origin/main")
    head = _git(work, "rev-parse", "HEAD")

    result = _pre_push(work, _new_branch_line("feature/empty", head), monkeypatch)

    err = capsys.readouterr().err
    assert result == 0, err
    assert "refs/heads/feature/empty scores 0 file(s)" in err


def test_failed_diff_fails_loud(
    origin: Origin,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """AC5: a diff git cannot produce is a config error, not an empty file list."""
    work = _work(origin, tmp_path)
    _git(work, "checkout", "-q", "-b", "feature/docs")
    head = _commit(work, "docs/note.md", "note\n")
    real_run_git = policy._run_git

    def failing_scan_diff(repo_root: Path, args: list[str]) -> subprocess.CompletedProcess[str]:
        if args[:4] == ["diff", "--name-only", "-z", "--no-renames"]:
            return subprocess.CompletedProcess(args, 128, "", "fatal: bad object\n")
        return real_run_git(repo_root, args)

    monkeypatch.setattr(policy, "_run_git", failing_scan_diff)

    result = _pre_push(work, _new_branch_line("feature/docs", head), monkeypatch)

    err = capsys.readouterr().err
    assert result == 2, err
    assert "could not diff" in err
    assert "scores" not in err


def test_branch_policy_failure_returns_before_the_scan(
    origin: Origin,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The scan runs only after the per-update branch policies pass."""
    work = _work(origin, tmp_path)
    _git(work, "checkout", "-q", "-b", "feature/docs")
    head = _commit(work, "docs/note.md", "note\n")
    scanned: list[object] = []
    monkeypatch.setattr(policy, "_check_push_updates", lambda *_args: 1)
    monkeypatch.setattr(
        policy, "check_pushed_infrastructure", lambda *args: scanned.append(args) or 0
    )

    result = _pre_push(work, _new_branch_line("feature/docs", head), monkeypatch)

    assert result == 1
    assert scanned == []
