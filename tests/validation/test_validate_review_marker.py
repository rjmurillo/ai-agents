"""Tests for the ``/review`` skill's review-marker validator.

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
        text=True, encoding="utf-8",
        input=message_stdin,
        check=True,
    )
    return result.stdout.strip()


def _git_bytes(repo: Path, *args: str, stdin: bytes | None = None) -> bytes:
    """Run a git command in ``repo`` with byte-level I/O."""
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        input=stdin,
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


def test_parse_uppercase_sha_marker_normalizes_to_lowercase() -> None:
    """A copied uppercase SHA is accepted and normalized."""
    sha = "A" * 40
    marker = vrm.parse_marker(f"/review@analyst on {sha}")
    assert marker is not None
    assert marker.sha == sha.lower()


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
    assert "empty commit" in outcome.message


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
    values, error = vrm.read_marker_values("--format=%H", git_repo)
    assert values is None
    assert error is not None and "must not start with '-'" in error


def test_validate_ref_reports_git_missing(monkeypatch: pytest.MonkeyPatch, git_repo: Path) -> None:
    """A missing git binary reports an actionable config error."""
    monkeypatch.setattr(vrm.shutil, "which", lambda _: None)
    outcome = vrm.validate_ref("HEAD", git_repo)
    assert outcome.ok is False
    assert outcome.exit_code == 2
    assert outcome.message == "git not found on PATH"


def test_validate_ref_reports_initial_git_failure(
    monkeypatch: pytest.MonkeyPatch, git_repo: Path
) -> None:
    """Initial ref resolution preserves git's actionable stderr."""

    def fail_git(args: list[str], repo_root: Path) -> tuple[int, str, str]:
        return -1, "", "git command timed out after 15s"

    monkeypatch.setattr(vrm, "_run_git", fail_git)
    outcome = vrm.validate_ref("HEAD", git_repo)
    assert outcome.ok is False
    assert outcome.exit_code == 2
    assert "git command timed out after 15s" in outcome.message


def test_read_marker_values_distinguishes_missing_git(
    monkeypatch: pytest.MonkeyPatch, git_repo: Path
) -> None:
    """Direct trailer reads preserve the missing-git diagnostic."""
    monkeypatch.setattr(vrm.shutil, "which", lambda _: None)
    values, error = vrm.read_marker_values("HEAD", git_repo)
    assert values is None
    assert error == "git not found on PATH"


def test_read_marker_values_distinguishes_nonzero_git_exit(git_repo: Path) -> None:
    """A real git lookup miss reports git's non-zero exit separately from I/O failures."""
    values, error = vrm.read_marker_values("no-such-ref", git_repo)
    assert values is None
    assert error is not None
    assert error.startswith("git log exited with ")
    assert "git output was not valid UTF-8" not in error
    assert "git command timed out" not in error


def test_validate_ref_reports_parent_read_timeout(
    monkeypatch: pytest.MonkeyPatch, git_repo: Path
) -> None:
    """Parent SHA reads preserve timeout diagnostics in the validation outcome."""
    head_sha = _git(git_repo, "rev-parse", "HEAD")

    def fail_parent_read(args: list[str], repo_root: Path) -> tuple[int, str, str]:
        if args[:3] == ["rev-parse", "--verify", "--quiet"]:
            return 0, f"{head_sha}\n", ""
        if args == ["show", "-s", "--format=%P", head_sha]:
            return -1, "", "git command timed out after 15s"
        return 1, "", "unexpected command"

    monkeypatch.setattr(vrm, "_run_git", fail_parent_read)
    outcome = vrm.validate_ref("HEAD", git_repo)
    assert outcome.ok is False
    assert outcome.exit_code == 2
    assert "git could not read parent commits" in outcome.message
    assert "git command timed out after 15s" in outcome.message


def test_validate_ref_reports_non_utf8_trailer_output(git_repo: Path) -> None:
    """A commit with non-UTF-8 trailer bytes reports the decode failure."""
    parent_sha = _git(git_repo, "rev-parse", "HEAD")
    tree_sha = _git(git_repo, "show", "-s", "--format=%T", "HEAD")
    commit_bytes = b"".join(
        [
            f"tree {tree_sha}\n".encode(),
            f"parent {parent_sha}\n".encode(),
            b"author Test User <test@example.com> 0 +0000\n",
            b"committer Test User <test@example.com> 0 +0000\n",
            b"\n",
            b"review: marker with latin-1 trailer\n\n",
            b"Reviewed-By: ",
            b"\xff",
            f"/review@analyst on {parent_sha}\n".encode(),
        ]
    )
    marker_sha = _git_bytes(
        git_repo,
        "hash-object",
        "-t",
        "commit",
        "-w",
        "--stdin",
        stdin=commit_bytes,
    )
    _git(git_repo, "update-ref", "HEAD", marker_sha.decode())

    outcome = vrm.validate_ref("HEAD", git_repo)
    assert outcome.ok is False
    assert outcome.exit_code == 2
    assert "git output was not valid UTF-8" in outcome.message


def test_validate_ref_fails_when_marker_commit_has_multiple_parents(git_repo: Path) -> None:
    """A merge commit cannot serve as the review marker."""
    original_branch = _git(git_repo, "branch", "--show-current")
    _git(git_repo, "checkout", "-q", "-b", "side")
    _git(git_repo, "commit", "-q", "--allow-empty", "-m", "feat: side empty")
    side_tip = _git(git_repo, "rev-parse", "HEAD")
    _git(git_repo, "checkout", "-q", original_branch)
    _git(git_repo, "merge", "-q", "--no-ff", "side", "-m", "review: merge marker")
    _git(
        git_repo,
        "commit",
        "-q",
        "--amend",
        "--no-edit",
        "--trailer",
        f"Reviewed-By: /review@analyst on {side_tip}",
    )
    outcome = vrm.validate_ref("HEAD", git_repo)
    assert outcome.ok is False
    assert outcome.exit_code == 1
    assert "single-parent" in outcome.message


def test_source_validator_cli_runs() -> None:
    """The source-repo validator still exposes the CLI."""
    result = subprocess.run(
        [sys.executable, str(SCRIPT_PATH), "--help"],
        capture_output=True,
        text=True, encoding="utf-8",
        check=False,
    )
    assert result.returncode == 0
    assert "Validate a SHA-bound" in result.stdout


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


def test_cli_defaults_repo_root_to_current_working_directory(git_repo: Path) -> None:
    """Vendored validator invocations validate the consumer repo by default."""
    _write_marker_commit(git_repo, "analyst")
    result = subprocess.run(
        [sys.executable, str(SCRIPT_PATH), "--ref", "HEAD"],
        cwd=git_repo,
        capture_output=True,
        text=True, encoding="utf-8",
        check=False,
    )
    assert result.returncode == 0
    assert "[PASS]" in result.stdout


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


# --- git diagnostics reach the developer -----------------------------------


class TestGitDiagnosticsAreNotFlattened:
    """Every reader in this gate must carry git's own reason to the outcome.

    `_run_git` produces specific text for its internal failure modes: a 15s
    timeout, git missing from PATH, and stdout that is not valid UTF-8. When a
    reader drops that text, `validate_ref` reports a generic "git could not
    read the commit". The developer runs the same command by hand, their
    terminal decodes leniently, the trailer looks fine, and the ship gate has
    blocked them while pointing at the wrong thing.

    `read_marker_values` is the highest-risk reader because its stdout is
    commit trailer text, so a commit authored under a latin-1 locale is enough
    to trip the strict decode. The other two read hex SHAs.
    """

    @staticmethod
    def _fail_with(monkeypatch, reason: str) -> None:
        monkeypatch.setattr(vrm, "_run_git", lambda *_a, **_k: (-1, "", reason))

    def test_read_marker_values_carries_the_reason(self, monkeypatch, git_repo: Path):
        self._fail_with(monkeypatch, "git output was not valid UTF-8")
        assert vrm.read_marker_values("HEAD", git_repo) == (
            None,
            "git output was not valid UTF-8",
        )

    def test_read_parent_shas_carries_the_reason(self, monkeypatch, git_repo: Path):
        self._fail_with(monkeypatch, "git command timed out after 15s")
        assert vrm.read_parent_shas("HEAD", git_repo) == (
            None,
            "git command timed out after 15s",
        )

    def test_resolve_tree_sha_carries_the_reason(self, monkeypatch, git_repo: Path):
        self._fail_with(monkeypatch, "git not found on PATH")
        assert vrm.resolve_tree_sha("HEAD", git_repo) == (
            None,
            "git not found on PATH",
        )

    def test_successful_reads_report_no_error(self, git_repo: Path):
        """Negative control: the error slot stays empty on the happy path."""
        parents, parent_error = vrm.read_parent_shas("HEAD", git_repo)
        values, values_error = vrm.read_marker_values("HEAD", git_repo)
        tree, tree_error = vrm.resolve_tree_sha("HEAD", git_repo)
        assert parents is not None and parent_error is None
        assert values is not None and values_error is None
        assert tree is not None and tree_error is None

    def test_validate_ref_surfaces_the_decode_failure(self, monkeypatch, git_repo: Path):
        """The motivating case: a latin-1 trailer must not read as a bad ref."""
        _write_marker_commit(git_repo, "analyst")
        monkeypatch.setattr(
            vrm,
            "read_marker_values",
            lambda *_a, **_k: (None, "git output was not valid UTF-8"),
        )
        outcome = vrm.validate_ref("HEAD", git_repo)
        assert outcome.ok is False
        assert outcome.exit_code == 2
        assert "git output was not valid UTF-8" in outcome.message

    def test_validate_ref_surfaces_a_parent_read_failure(self, monkeypatch, git_repo: Path):
        monkeypatch.setattr(
            vrm,
            "read_parent_shas",
            lambda *_a, **_k: (None, "git command timed out after 15s"),
        )
        outcome = vrm.validate_ref("HEAD", git_repo)
        assert outcome.exit_code == 2
        assert "git command timed out after 15s" in outcome.message

    def test_validate_ref_surfaces_a_tree_comparison_failure(self, monkeypatch, git_repo: Path):
        monkeypatch.setattr(
            vrm,
            "resolve_tree_sha",
            lambda *_a, **_k: (None, "git command timed out after 15s"),
        )
        outcome = vrm.validate_ref("HEAD", git_repo)
        assert outcome.exit_code == 2
        assert "git command timed out after 15s" in outcome.message

    def test_absent_reason_leaves_the_message_unchanged(self):
        """Edge: git can fail with empty stderr. No dangling colon."""
        assert vrm._with_reason("git could not read commit 'HEAD'", None) == (
            "git could not read commit 'HEAD'"
        )
        assert vrm._with_reason("base", "") == "base"

    def test_empty_stderr_reports_the_exit_code_without_inventing_a_reason(
        self, monkeypatch, git_repo: Path
    ):
        """Edge: git can fail with empty stderr. The exit code alone still carries."""
        monkeypatch.setattr(vrm, "_run_git", lambda *_a, **_k: (1, "", "   "))
        assert vrm.read_marker_values("HEAD", git_repo) == (
            None,
            "git log exited with 1",
        )
