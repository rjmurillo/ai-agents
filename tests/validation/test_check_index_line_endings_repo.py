"""The gate measured against real git repositories (issue #5475).

Split from `test_check_index_line_endings.py` at the 500-line `file-size`
ceiling, along the seam that matters: everything here builds or reads a real
repository, so it exercises what `git ls-files --eol` actually emits rather
than a string the test wrote. The parser's own contract is covered there, and
`--fix` plus path encoding in `test_check_index_line_endings_fix.py`.

Covered here: the negative control on a planted CRLF blob, the operator-visible
phantom modification and its disappearance, the two incident paths by name, the
HEAD and index scopes and their precedence, and the attribute source each scope
reads.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from scripts.validation import check_index_line_endings as checker
from tests.validation.index_line_endings_helpers import (
    INCIDENT_PATHS,
    REPO_ROOT,
    _commit,
    _git,
    _porcelain,
    _repo_with_crlf_blob,
)

# --- the live repository --------------------------------------------------


def test_this_repository_has_no_contradicting_blobs() -> None:
    """The regression guard: main must never carry one of these again."""
    violations, examined = checker.check_repository(REPO_ROOT)

    assert violations == [], [v.render() for v in violations]
    assert examined > 0


def test_git_ls_files_eol_still_emits_the_parsed_shape() -> None:
    """Pin the producer's format so a git change cannot silently blind the check."""
    result = subprocess.run(
        ["git", "ls-files", "--eol", "--", "README.md"],
        cwd=REPO_ROOT,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
        check=True,
    )

    line = result.stdout.splitlines()[0]
    assert "\t" in line
    head = line.split("\t", 1)[0].split()
    assert head[0].startswith("i/")
    assert head[1].startswith("w/")
    assert head[2].startswith("attr/")


def test_negative_control_gate_fails_on_a_real_crlf_blob(tmp_path: Path) -> None:
    """The control the manual pre-fix run stood in for, now executable.

    Without this the suite proves the gate passes on a clean tree and never
    proves it fails on a dirty one, which is the only claim that matters.
    """
    repo = _repo_with_crlf_blob(tmp_path)

    violations, examined = checker.check_repository(repo)

    assert [v.path for v in violations] == ["handoff.md"]
    assert violations[0].index_state == "i/crlf"
    assert examined >= 2
    assert checker.main(["--repo-root", str(repo)]) == 1


def test_negative_control_passes_after_renormalize(tmp_path: Path) -> None:
    """The documented fix must actually clear the gate, not just quiet it."""
    repo = _repo_with_crlf_blob(tmp_path)
    assert checker.main(["--repo-root", str(repo)]) == 1

    _git(repo, "add", "--renormalize", "handoff.md")

    violations, _ = checker.check_repository(repo)
    assert violations == []
    assert checker.main(["--repo-root", str(repo)]) == 0


def test_a_crlf_blob_reports_a_modification_nobody_made(tmp_path: Path) -> None:
    """The operator-visible symptom, reproduced and then shown fixed.

    A fresh checkout of the CRLF blob reads back through the clean filter as
    LF, so its hash never matches its own blob and git reports a modification
    nobody made. That is what aborts a merge touching the path. Renormalizing
    removes it, and the checkout stays clean even after the file is touched.
    """
    repo = _repo_with_crlf_blob(tmp_path)
    _git(repo, "config", "core.autocrlf", "input")
    _commit(repo, "plant a CRLF blob the way the API does")

    before = tmp_path / "before"
    _git(repo, "worktree", "add", "--detach", "--quiet", str(before), "HEAD")
    (before / "handoff.md").touch()
    assert "handoff.md" in _porcelain(before)

    _git(repo, "add", "--renormalize", "handoff.md")
    _commit(repo, "renormalize")

    after = tmp_path / "after"
    _git(repo, "worktree", "add", "--detach", "--quiet", str(after), "HEAD")
    assert _porcelain(after) == ""
    (after / "handoff.md").touch()
    assert _porcelain(after) == ""


@pytest.mark.parametrize("path", INCIDENT_PATHS)
def test_the_two_incident_handoffs_hold_lf_index_blobs(path: str) -> None:
    """Pin the exact paths that aborted merges, on this repository."""
    result = subprocess.run(
        ["git", "ls-files", "--eol", "--", path],
        cwd=REPO_ROOT,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
        check=True,
    )

    rows = result.stdout.splitlines()
    # An archived or renamed handoff is not a regression, but a tracked one
    # holding CRLF is exactly the defect, so only assert when it is present.
    if not rows:
        pytest.skip(f"{path} is no longer tracked")
    assert rows[0].split()[0] == "i/lf", rows[0]


# --- HEAD vs index scope (review thread on check_index_line_endings.py:65) --


def test_head_blob_is_reported_even_when_the_index_is_already_clean(
    tmp_path: Path,
) -> None:
    """Staging a fix does not make the pushed tree clean.

    `git ls-files` reads the mutable index. After `git add --renormalize` but
    before committing, the index says LF while HEAD still carries the CRLF blob
    that a push transmits, so an index-only scan would call this clean.
    """
    repo = _repo_with_crlf_blob(tmp_path)
    _commit(repo, "plant a CRLF blob")
    _git(repo, "add", "--renormalize", "handoff.md")

    violations, _ = checker.check_repository(repo)

    assert [(v.path, v.scope) for v in violations] == [("handoff.md", "HEAD")]
    assert checker.main(["--repo-root", str(repo)]) == 1


def test_staged_blob_is_reported_when_head_is_clean(tmp_path: Path) -> None:
    """The index scope still matters: it is what the next commit will store."""
    repo = _repo_with_crlf_blob(tmp_path)

    violations, _ = checker.check_repository(repo)

    assert [(v.path, v.scope) for v in violations] == [("handoff.md", "index")]


def test_a_path_bad_in_both_scopes_is_reported_once(tmp_path: Path) -> None:
    """One remediation fixes both, so two rows would be noise."""
    repo = _repo_with_crlf_blob(tmp_path)
    _commit(repo, "plant a CRLF blob")

    violations, _ = checker.check_repository(repo)

    assert [(v.path, v.scope) for v in violations] == [("handoff.md", "HEAD")]


def test_an_unborn_branch_scans_the_index_without_crashing(tmp_path: Path) -> None:
    """A repo with no commits has no HEAD to read; the index still counts."""
    repo = _repo_with_crlf_blob(tmp_path)

    violations, _ = checker.check_repository(repo)

    assert [v.scope for v in violations] == ["index"]


def test_head_scope_uses_head_attributes_not_the_working_tree(
    tmp_path: Path,
) -> None:
    """An uncommitted `-text` edit must not hide a committed violation.

    GIT_INDEX_FILE isolates the blobs, but git reads `.gitattributes` from the
    working tree unless GIT_ATTR_SOURCE pins it, so without that the HEAD scope
    would be judged by rules HEAD does not carry.
    """
    repo = _repo_with_crlf_blob(tmp_path)
    _commit(repo, "plant a CRLF blob")

    # Locally exempt the path without committing the exemption.
    (repo / ".gitattributes").write_text(
        "* text=auto eol=lf\n*.md text\nhandoff.md -text\n", newline="\n"
    )

    violations, _ = checker.check_repository(repo)

    assert [(v.path, v.scope) for v in violations] == [("handoff.md", "HEAD")]


def test_head_scope_honours_a_committed_exemption(tmp_path: Path) -> None:
    """The control for the test above: a committed `-text` really does exempt."""
    repo = _repo_with_crlf_blob(tmp_path)
    (repo / ".gitattributes").write_text(
        "* text=auto eol=lf\n*.md text\nhandoff.md -text\n", newline="\n"
    )
    _git(repo, "add", ".gitattributes")
    _commit(repo, "plant a CRLF blob under a committed exemption")

    violations, _ = checker.check_repository(repo)

    assert violations == []


# --- ambient GIT_* overrides (review thread on the git helpers) ------------
#
# Every test below plants the defect in one repository and points an ambient
# variable at a second, clean one. Without the stripping in `_git_environment`
# git answers about the decoy, so the gate reports a clean scan for a
# repository that is not clean, and `--fix` writes where nobody approved.


def _decoy_repo(tmp_path: Path) -> Path:
    """A second, clean repository for an ambient variable to point at."""
    decoy = tmp_path / "decoy"
    decoy.mkdir()
    _git(decoy, "init", "--quiet")
    (decoy / ".gitattributes").write_text("* text=auto eol=lf\n*.md text\n", newline="\n")
    _git(decoy, "add", ".gitattributes")
    _commit(decoy, "a repository with nothing wrong in it")
    return decoy


def _subject_with_crlf_blob(tmp_path: Path) -> Path:
    """The repository under test, in its own directory beside the decoy."""
    subject_root = tmp_path / "subject"
    subject_root.mkdir()
    return _repo_with_crlf_blob(subject_root)


def test_scan_ignores_an_ambient_git_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """`cwd=repo_root` does not win against an exported `GIT_DIR`.

    Both scopes would follow the variable: `read-tree HEAD` resolves the
    decoy's HEAD and the index pass lists the decoy's index. The subject's
    violation then goes unreported and the gate exits 0.
    """
    subject = _subject_with_crlf_blob(tmp_path)
    _commit(subject, "plant a CRLF blob")
    decoy = _decoy_repo(tmp_path)
    monkeypatch.setenv("GIT_DIR", str(decoy / ".git"))

    violations, _ = checker.check_repository(subject)

    assert [(v.path, v.scope) for v in violations] == [("handoff.md", "HEAD")]


def test_scan_ignores_an_ambient_git_index_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An ambient `GIT_INDEX_FILE` would replace the index scope's subject.

    The subject here has no commit, so only the index scope runs and the
    variable's effect on that scope is isolated.
    """
    subject = _subject_with_crlf_blob(tmp_path)
    decoy = _decoy_repo(tmp_path)
    monkeypatch.setenv("GIT_INDEX_FILE", str(decoy / ".git" / "index"))

    violations, _ = checker.check_repository(subject)

    assert [(v.path, v.scope) for v in violations] == [("handoff.md", "index")]


def test_fix_ignores_an_ambient_git_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The write half: `--fix` must stage into the root the guard approved.

    `refuses_write_from_outside` compares the current directory against
    `--repo-root` and passes here, because both name the subject. A leaked
    `GIT_DIR` makes git write somewhere neither of them names, which is the
    disagreement that guard exists to stop.
    """
    subject = _subject_with_crlf_blob(tmp_path)
    _commit(subject, "plant a CRLF blob")
    decoy = _decoy_repo(tmp_path)
    monkeypatch.chdir(subject)
    monkeypatch.setenv("GIT_DIR", str(decoy / ".git"))

    assert checker.main(["--repo-root", str(subject), "--fix"]) == 1

    violations, _ = checker.check_repository(subject)
    assert [v.scope for v in violations] == ["HEAD"]  # index fixed, HEAD awaits commit
    assert _porcelain(decoy) == ""


# --- the GIT_ATTR_SOURCE capability floor ---------------------------------


def test_a_git_without_attr_source_support_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    """An older git ignores `GIT_ATTR_SOURCE` silently, so the gate must not.

    Both scopes pin their attribute source with that variable. Ignored, the
    working tree's `.gitattributes` answers for a tree it does not describe,
    and the run reports the same way as a run that measured what it claimed.
    """
    repo = _repo_with_crlf_blob(tmp_path)
    _commit(repo, "plant a CRLF blob")
    monkeypatch.setattr(checker, "_git_version", lambda _repo_root: (2, 40))

    assert checker.main(["--repo-root", str(repo)]) == 2

    err = capsys.readouterr().err
    assert "git 2.40 predates GIT_ATTR_SOURCE" in err
    assert "git 2.41" in err
    assert checker.validate_index_line_endings(repo) is False


def test_the_supported_floor_itself_is_allowed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Control for the test above: 2.41 is the floor, not the first refusal."""
    repo = _repo_with_crlf_blob(tmp_path)
    monkeypatch.setattr(checker, "_git_version", lambda _repo_root: (2, 41))

    assert checker.main(["--repo-root", str(repo)]) == 1  # violations, not a config error


def test_git_version_reads_the_distributor_spellings(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Apple and Git for Windows both append their own build to the version."""
    captured = {"stdout": ""}

    def fake_git(_repo_root: Path, args: list[str], env: dict[str, str] | None = None):
        return subprocess.CompletedProcess(args, 0, stdout=captured["stdout"], stderr="")

    monkeypatch.setattr(checker, "_git", fake_git)

    for text, expected in (
        ("git version 2.51.0", (2, 51)),
        ("git version 2.39.5 (Apple Git-154)", (2, 39)),
        ("git version 2.45.1.windows.1", (2, 45)),
    ):
        captured["stdout"] = text
        assert checker._git_version(tmp_path) == expected

    captured["stdout"] = "not a version at all"
    with pytest.raises(RuntimeError, match="could not read a version"):
        checker._git_version(tmp_path)


# --- index scope: attributes as staged, not as edited ---------------------
#
# `_head_env` pins HEAD's attributes for the same reason. Without the matching
# pin on this scope, an uncommitted `.gitattributes` edit decides the verdict
# for blobs the next commit will store under the staged attributes instead.


def _stage_attributes(repo: Path, text: str) -> None:
    (repo / ".gitattributes").write_text(text, newline="\n")
    _git(repo, "add", ".gitattributes")


def test_index_scope_reads_staged_attributes_not_an_unstaged_exemption(
    tmp_path: Path,
) -> None:
    """An unstaged `-text` must not hide a blob the next commit stores as `eol=lf`."""
    repo = _repo_with_crlf_blob(tmp_path)
    # Edited on disk, deliberately not staged: the commit will carry `*.md text`.
    (repo / ".gitattributes").write_text(
        "* text=auto eol=lf\n*.md text\nhandoff.md -text\n", newline="\n"
    )

    violations, _ = checker.check_repository(repo)

    assert [(v.path, v.scope) for v in violations] == [("handoff.md", "index")]


def test_index_scope_honours_a_staged_exemption_over_an_unstaged_removal(
    tmp_path: Path,
) -> None:
    """The inverse: an unstaged removal must not invent a violation either."""
    repo = _repo_with_crlf_blob(tmp_path)
    _stage_attributes(repo, "* text=auto eol=lf\n*.md text\nhandoff.md -text\n")
    # The exemption is staged, so the next commit carries it. Removing it only
    # on disk changes nothing about what that commit will store.
    (repo / ".gitattributes").write_text("* text=auto eol=lf\n*.md text\n", newline="\n")

    violations, _ = checker.check_repository(repo)

    assert violations == []
