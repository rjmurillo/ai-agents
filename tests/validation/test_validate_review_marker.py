"""Tests for ``scripts/validation/validate_review_marker.py``.

Locks the SHA-bound review-marker contract that ``/ship`` depends on (Issue
#1938). The marker format is::

    Reviewed-By: /review@<axes> on <sha>

Pure parsing (``parse_marker``, ``select_marker_for_sha``) is tested directly.
The end-to-end ``validate_ref`` path and the CLI ``main`` are tested against
real temporary git repositories, so the git trailer mechanism is exercised for
real rather than mocked: the I/O boundary is git itself, and a mock there would
re-encode the same assumption the test is supposed to verify.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPT_PATH = REPO_ROOT / "scripts" / "validation" / "validate_review_marker.py"


def _load_module():
    """Load the script as a module under a stable name."""
    spec = importlib.util.spec_from_file_location(
        "validate_review_marker",
        SCRIPT_PATH,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


vrm = _load_module()


# --- git repo fixture ------------------------------------------------------


def _git(repo: Path, *args: str, message_stdin: str | None = None) -> str:
    """Run a git command in ``repo`` and return stripped stdout."""
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        input=message_stdin,
        check=True,
    )
    return result.stdout.strip()


@pytest.fixture()
def git_repo(tmp_path: Path) -> Path:
    """Initialize a real git repo with two code commits and isolated identity.

    Two commits (not one) so HEAD always has a parent; the marker contract is a
    parent-binding check, and a root commit (no parent) is its own edge case
    covered separately by ``test_validate_ref_fails_on_root_commit``.
    """
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Test User")
    _git(repo, "config", "commit.gpgsign", "false")
    (repo / "a.txt").write_text("hello\n", encoding="utf-8")
    _git(repo, "add", "a.txt")
    _git(repo, "commit", "-q", "-m", "feat: initial commit")
    (repo / "b.txt").write_text("world\n", encoding="utf-8")
    _git(repo, "add", "b.txt")
    _git(repo, "commit", "-q", "-m", "feat: second commit")
    return repo


def _write_marker_commit(repo: Path, axes: str) -> tuple[str, str]:
    """Write an empty marker commit on top of HEAD, naming the reviewed tip.

    Mirrors what the /review skill does on a PASS verdict: review the tip, then
    create an empty commit whose ``Reviewed-By`` trailer names that tip (the
    reviewed code state). Returns (reviewed_tip_sha, marker_head_sha).
    """
    reviewed_tip = _git(repo, "rev-parse", "HEAD")
    _git(
        repo,
        "commit",
        "-q",
        "--allow-empty",
        "-m",
        "review: /review PASS marker",
        "--trailer",
        f"Reviewed-By: /review@{axes} on {reviewed_tip}",
    )
    return reviewed_tip, _git(repo, "rev-parse", "HEAD")


# --- parse_marker: positive ------------------------------------------------


def test_parse_single_axis_marker() -> None:
    """A single-axis marker parses into one axis and the SHA."""
    sha = "a" * 40
    marker = vrm.parse_marker(f"/review@analyst on {sha}")
    assert marker is not None
    assert marker.axes == ("analyst",)
    assert marker.sha == sha


def test_parse_multi_axis_marker() -> None:
    """A comma-separated axis list parses into a tuple of axes."""
    sha = "b" * 40
    marker = vrm.parse_marker(f"/review@analyst,security,qa on {sha}")
    assert marker is not None
    assert marker.axes == ("analyst", "security", "qa")
    assert marker.sha == sha


def test_parse_sha256_marker() -> None:
    """A 64-hex sha256 object name is accepted."""
    sha = "c" * 64
    marker = vrm.parse_marker(f"/review@analyst on {sha}")
    assert marker is not None
    assert marker.sha == sha


def test_parse_tolerates_surrounding_whitespace() -> None:
    """Leading and trailing whitespace on the trailer value is stripped."""
    sha = "d" * 40
    marker = vrm.parse_marker(f"  /review@analyst on {sha}  ")
    assert marker is not None
    assert marker.sha == sha


# --- parse_marker: negative ------------------------------------------------


def test_parse_rejects_empty_string() -> None:
    """An empty value is not a marker."""
    assert vrm.parse_marker("") is None


def test_parse_rejects_wrong_prefix() -> None:
    """A trailer that is not a /review marker is rejected."""
    assert vrm.parse_marker(f"Co-authored-by: Someone on {'a' * 40}") is None


def test_parse_rejects_empty_axis_list() -> None:
    """A marker with no axes (``/review@ on <sha>``) is malformed."""
    assert vrm.parse_marker(f"/review@ on {'a' * 40}") is None


def test_parse_rejects_missing_sha() -> None:
    """A marker with no SHA is malformed."""
    assert vrm.parse_marker("/review@analyst on ") is None


def test_parse_rejects_short_sha() -> None:
    """An abbreviated SHA (not 40 or 64 hex) is rejected; binding needs the full name."""
    assert vrm.parse_marker(f"/review@analyst on {'a' * 12}") is None


def test_parse_rejects_non_hex_sha() -> None:
    """A SHA with non-hex characters is rejected."""
    assert vrm.parse_marker(f"/review@analyst on {'g' * 40}") is None


def test_parse_rejects_trailing_axis_comma() -> None:
    """A dangling comma in the axis list is malformed."""
    assert vrm.parse_marker(f"/review@analyst, on {'a' * 40}") is None


# --- select_marker_for_sha -------------------------------------------------


def test_select_returns_marker_when_sha_matches() -> None:
    """A valid marker whose SHA matches the expected SHA is selected."""
    sha = "a" * 40
    marker = vrm.select_marker_for_sha([f"/review@analyst on {sha}"], sha)
    assert marker is not None
    assert marker.sha == sha


def test_select_rejects_marker_for_different_sha() -> None:
    """A marker that reviewed a different commit does not bind the expected SHA."""
    reviewed = "a" * 40
    shipped = "b" * 40
    assert vrm.select_marker_for_sha([f"/review@analyst on {reviewed}"], shipped) is None


def test_select_skips_malformed_and_finds_valid() -> None:
    """Among several trailer values, the valid SHA-matching one wins."""
    sha = "a" * 40
    values = [
        "garbage",
        f"/review@ on {sha}",  # malformed axis list
        f"/review@security on {sha}",  # valid match
    ]
    marker = vrm.select_marker_for_sha(values, sha)
    assert marker is not None
    assert marker.axes == ("security",)


def test_select_returns_none_for_empty_values() -> None:
    """No trailer values means no binding marker."""
    assert vrm.select_marker_for_sha([], "a" * 40) is None


# --- validate_ref: real git, positive --------------------------------------


def test_validate_ref_passes_when_marker_binds_reviewed_tip(git_repo: Path) -> None:
    """An empty marker commit naming its parent (the reviewed tip) validates."""
    reviewed_tip, _ = _write_marker_commit(git_repo, "analyst,security")
    outcome = vrm.validate_ref("HEAD", git_repo)
    assert outcome.ok is True
    assert outcome.exit_code == 0
    assert reviewed_tip[:12] in outcome.message


# --- validate_ref: real git, negative --------------------------------------


def test_validate_ref_fails_when_no_marker(git_repo: Path) -> None:
    """A code commit (HEAD has a parent) with no Reviewed-By trailer fails (exit 1)."""
    outcome = vrm.validate_ref("HEAD", git_repo)
    assert outcome.ok is False
    assert outcome.exit_code == 1
    assert "no" in outcome.message.lower()


def test_validate_ref_fails_when_marker_names_stale_sha(git_repo: Path) -> None:
    """A marker on HEAD naming a SHA other than HEAD's parent fails (stale review).

    Simulates a marker commit whose recorded SHA is not the reviewed tip it
    sits on: the review covered a different commit, so it must not ship.
    """
    stale_sha = "f" * 40
    _git(
        git_repo,
        "commit",
        "-q",
        "--allow-empty",
        "-m",
        "review: stale marker",
        "--trailer",
        f"Reviewed-By: /review@analyst on {stale_sha}",
    )
    outcome = vrm.validate_ref("HEAD", git_repo)
    assert outcome.ok is False
    assert outcome.exit_code == 1
    assert "does not bind" in outcome.message


def test_validate_ref_fails_when_code_lands_after_marker(git_repo: Path) -> None:
    """A new code commit on top of a valid marker invalidates the review.

    review -> marker -> new code. HEAD is now the code commit; its parent is the
    marker, not the reviewed tip, so binding fails. This is the core anti-stale
    guarantee: you cannot ship code that landed after the review.
    """
    _write_marker_commit(git_repo, "analyst,security")
    (git_repo / "c.txt").write_text("new code\n", encoding="utf-8")
    _git(git_repo, "add", "c.txt")
    _git(git_repo, "commit", "-q", "-m", "feat: code after review")
    outcome = vrm.validate_ref("HEAD", git_repo)
    assert outcome.ok is False
    assert outcome.exit_code == 1


def test_validate_ref_fails_when_code_commit_carries_matching_marker(git_repo: Path) -> None:
    """A non-empty code commit cannot serve as the review marker."""
    reviewed_tip = _git(git_repo, "rev-parse", "HEAD")
    (git_repo / "c.txt").write_text("new code with trailer\n", encoding="utf-8")
    _git(git_repo, "add", "c.txt")
    _git(
        git_repo,
        "commit",
        "-q",
        "-m",
        "feat: code with forged review marker",
        "--trailer",
        f"Reviewed-By: /review@analyst on {reviewed_tip}",
    )
    outcome = vrm.validate_ref("HEAD", git_repo)
    assert outcome.ok is False
    assert outcome.exit_code == 1
    assert "empty commit" in outcome.message


def test_validate_ref_fails_for_unknown_ref(git_repo: Path) -> None:
    """An unresolvable ref is a config error (exit 2)."""
    outcome = vrm.validate_ref("no-such-ref", git_repo)
    assert outcome.ok is False
    assert outcome.exit_code == 2
    assert "could not resolve" in outcome.message


def test_validate_ref_fails_for_option_like_ref(git_repo: Path) -> None:
    """A ref starting with '-' is rejected before invoking git."""
    outcome = vrm.validate_ref("--abbrev-ref", git_repo)
    assert outcome.ok is False
    assert outcome.exit_code == 2
    assert "must not start with '-'" in outcome.message


def test_resolve_sha_rejects_option_like_ref(git_repo: Path) -> None:
    """resolve_sha rejects values git would parse as command options."""
    assert vrm.resolve_sha("--abbrev-ref", git_repo) is None


def test_read_marker_values_rejects_option_like_ref(git_repo: Path) -> None:
    """read_marker_values rejects values git would parse as command options."""
    assert vrm.read_marker_values("--format=%H", git_repo) is None


def test_validate_ref_reports_git_missing(monkeypatch: pytest.MonkeyPatch, git_repo: Path) -> None:
    """A missing git binary reports an actionable config error."""
    monkeypatch.setattr(vrm.shutil, "which", lambda _: None)
    outcome = vrm.validate_ref("HEAD", git_repo)
    assert outcome.ok is False
    assert outcome.exit_code == 2
    assert outcome.message == "git not found on PATH"


def test_validate_ref_fails_when_marker_commit_has_multiple_parents(git_repo: Path) -> None:
    """A merge commit cannot serve as the review marker."""
    reviewed_tip = _git(git_repo, "rev-parse", "HEAD")
    original_branch = _git(git_repo, "branch", "--show-current")
    _git(git_repo, "checkout", "-q", "-b", "side")
    _git(git_repo, "commit", "-q", "--allow-empty", "-m", "feat: side empty")
    _git(git_repo, "checkout", "-q", original_branch)
    _git(git_repo, "merge", "-q", "--no-ff", "side", "-m", "review: merge marker")
    _git(
        git_repo,
        "commit",
        "-q",
        "--amend",
        "--no-edit",
        "--trailer",
        f"Reviewed-By: /review@analyst on {reviewed_tip}",
    )
    outcome = vrm.validate_ref("HEAD", git_repo)
    assert outcome.ok is False
    assert outcome.exit_code == 1
    assert "single-parent" in outcome.message


# --- validate_ref: edge -----------------------------------------------------


def test_validate_ref_passes_with_extra_unrelated_trailers(git_repo: Path) -> None:
    """A Co-authored-by trailer alongside the marker does not break binding."""
    reviewed_tip = _git(git_repo, "rev-parse", "HEAD")
    _git(
        git_repo,
        "commit",
        "-q",
        "--allow-empty",
        "-m",
        "review: marker with extra trailer",
        "--trailer",
        "Co-authored-by: Someone <s@example.com>",
        "--trailer",
        f"Reviewed-By: /review@qa on {reviewed_tip}",
    )
    outcome = vrm.validate_ref("HEAD", git_repo)
    assert outcome.ok is True
    assert outcome.exit_code == 0


def test_validate_ref_fails_on_root_commit(tmp_path: Path) -> None:
    """A root commit (no parent) cannot be a marker; fails with exit 1.

    A marker is an empty commit on top of the reviewed tip, so a parent must
    exist. The first commit in a repo has none.
    """
    repo = tmp_path / "rootrepo"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Test User")
    _git(repo, "config", "commit.gpgsign", "false")
    (repo / "a.txt").write_text("hi\n", encoding="utf-8")
    _git(repo, "add", "a.txt")
    _git(repo, "commit", "-q", "-m", "feat: root")
    outcome = vrm.validate_ref("HEAD", repo)
    assert outcome.ok is False
    assert outcome.exit_code == 1
    assert "no parent" in outcome.message


# --- CLI main ---------------------------------------------------------------


def test_main_returns_zero_on_valid_marker(git_repo: Path) -> None:
    """CLI ``main`` returns 0 when HEAD carries a binding marker."""
    _write_marker_commit(git_repo, "analyst")
    rc = vrm.main(["--repo-root", str(git_repo)])
    assert rc == 0


def test_main_returns_one_when_no_marker(git_repo: Path) -> None:
    """CLI ``main`` returns 1 when HEAD has no marker."""
    rc = vrm.main(["--repo-root", str(git_repo)])
    assert rc == 1


def test_main_returns_two_on_invalid_repo_root(tmp_path: Path) -> None:
    """CLI ``main`` returns 2 when --repo-root is not a directory."""
    rc = vrm.main(["--repo-root", str(tmp_path / "does-not-exist")])
    assert rc == 2


def test_main_returns_two_on_unknown_ref(git_repo: Path) -> None:
    """CLI ``main`` returns 2 when the ref cannot be resolved."""
    rc = vrm.main(["--repo-root", str(git_repo), "--ref", "no-such-ref"])
    assert rc == 2
