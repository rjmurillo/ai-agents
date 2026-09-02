"""Everything the gate reads that is not a blob: environment, git, attributes.

Split from `test_check_index_line_endings_repo.py` at the 500-line `file-size`
ceiling, along the seam the gate itself has. The sibling module asks whether a
tracked blob contradicts its attributes. This one asks whether the gate is
looking at the repository it was given, judging by the attributes that repository
stores, on a git that can answer at all.

Every test here builds a real repository, because none of these failures exist
against a mock.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from scripts.validation import check_index_line_endings as checker
from scripts.validation import index_line_endings_git as gitmod
from tests.validation.index_line_endings_helpers import (
    _commit,
    _git,
    _porcelain,
    _repo_with_crlf_blob,
    _staged_against_head,
)

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

    assert _staged_against_head(subject) == ["handoff.md"]  # written here,
    assert _staged_against_head(decoy) == []  # and not there
    assert _porcelain(decoy) == ""


def _loose_objects(repo: Path) -> int:
    """Count the loose objects in `repo`'s own object store.

    `git rev-parse --git-path objects` answers relative to the git invocation's
    working directory, which is `repo`. Resolving it against this process's
    directory instead counts the ai-agents checkout, and the before/after
    comparison then cannot fail no matter what the scan writes.
    """
    objects = repo / Path(_git(repo, "rev-parse", "--git-path", "objects").stdout.strip())
    return sum(1 for path in objects.resolve().rglob("*") if path.is_file())


def test_a_read_only_scan_writes_nothing_into_the_repository(tmp_path: Path) -> None:
    """The index scope builds a tree, and MUST-7 says not into the target.

    `_index_env` has to make git read attributes from the index, and read-only
    mode runs before any worktree-identity check, so it must do that without
    writing. It points `GIT_WORK_TREE` at an empty directory rather than
    building a tree object. The index here differs from HEAD, which is when a
    `write-tree` mechanism would have had something new to store.
    """
    repo = _repo_with_crlf_blob(tmp_path)
    _commit(repo, "plant a CRLF blob")
    (repo / "later.md").write_text("added after the commit\n", newline="\n")
    _git(repo, "add", "later.md")
    before = _loose_objects(repo)

    violations, _ = checker.check_repository(repo)

    assert [v.scope for v in violations] == ["HEAD"]  # the scan still answered
    assert _loose_objects(repo) == before


def test_the_index_scope_answers_the_same_way_twice(tmp_path: Path) -> None:
    """A second scan must not go quiet, which is the safe-looking failure.

    The rejected mechanism for this scope, `git write-tree` into a scratch
    object directory, records a cache-tree in the index. The next run returns
    that id without writing the object, `GIT_ATTR_SOURCE` cannot resolve it,
    and every blob reports as exempt. Two identical scans is the cheapest way
    to catch a scope that answers correctly once.
    """
    repo = _repo_with_crlf_blob(tmp_path)
    (repo / ".gitattributes").write_text(
        "* text=auto eol=lf\n*.md text\nhandoff.md -text\n", newline="\n"
    )

    first, _ = checker.check_repository(repo)
    second, _ = checker.check_repository(repo)

    assert [(v.path, v.scope) for v in first] == [("handoff.md", "index")]
    assert [(v.path, v.scope) for v in second] == [("handoff.md", "index")]


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
    monkeypatch.setattr(gitmod, "git_version", lambda _repo_root: (2, 40))

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
    monkeypatch.setattr(gitmod, "git_version", lambda _repo_root: (2, 41))

    assert checker.main(["--repo-root", str(repo)]) == 1  # violations, not a config error


def test_git_version_reads_the_distributor_spellings(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Apple and Git for Windows both append their own build to the version."""
    captured = {"stdout": ""}

    def fake_git(_repo_root: Path, args: list[str], env: dict[str, str] | None = None):
        return subprocess.CompletedProcess(args, 0, stdout=captured["stdout"], stderr="")

    monkeypatch.setattr(gitmod, "run_git", fake_git)

    for text, expected in (
        ("git version 2.51.0", (2, 51)),
        ("git version 2.39.5 (Apple Git-154)", (2, 39)),
        ("git version 2.45.1.windows.1", (2, 45)),
    ):
        captured["stdout"] = text
        assert gitmod.git_version(tmp_path) == expected

    captured["stdout"] = "not a version at all"
    with pytest.raises(RuntimeError, match="could not read a version"):
        gitmod.git_version(tmp_path)


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


# --- a failed git call is output too (CWE-117/CWE-451) ---------------------


def test_a_git_failure_message_escapes_the_path_it_names(tmp_path: Path) -> None:
    """The error reaches the same terminal the report does, so it escapes too.

    `--fix` hands git the tracked path, and git echoes it back in stderr. A
    newline in that name forges a line in the maintainer's terminal and in the
    CI log exactly as it would in the report.
    """
    repo = _repo_with_crlf_blob(tmp_path)
    forged = "  index-line-endings: 0 violation(s)"

    with pytest.raises(RuntimeError) as failure:
        gitmod.run_git(repo, ["cat-file", "-e", f"missing.md\n{forged}"])

    message = str(failure.value)
    assert f"\n{forged}" not in message
    assert "missing.md\\n" in message


def test_a_git_failure_message_escapes_a_bidi_control(tmp_path: Path) -> None:
    """The other half: U+202E reorders the message around the name."""
    repo = _repo_with_crlf_blob(tmp_path)

    with pytest.raises(RuntimeError) as failure:
        gitmod.run_git(repo, ["cat-file", "-e", "missing\u202edm.txt"])

    message = str(failure.value)
    assert "\u202e" not in message
    assert "missing\\u202edm.txt" in message


def test_a_bytes_mode_git_failure_escapes_the_same_way(tmp_path: Path) -> None:
    """`run_git_paths` decodes its own stderr, so it needs the same treatment."""
    repo = _repo_with_crlf_blob(tmp_path)

    with pytest.raises(RuntimeError) as failure:
        gitmod.run_git_paths(repo, ["cat-file", "-e", "missing.md\nforged"])

    assert "missing.md\\nforged" in str(failure.value)


# --- attribute sources the pinned one does not outrank ---------------------


def _info_attributes(repo: Path) -> Path:
    """Where git actually reads `info/attributes` for `repo`.

    Asked with `--git-path`, not assembled: in a linked worktree that file
    lives in the common directory while `--absolute-git-dir` names the
    worktree-private one.
    """
    path = repo / Path(_git(repo, "rev-parse", "--git-path", "info/attributes").stdout.strip())
    path.parent.mkdir(parents=True, exist_ok=True)
    return path.resolve()


def test_a_local_info_attributes_file_stops_the_scan(tmp_path: Path, capsys) -> None:
    """It outranks `GIT_ATTR_SOURCE`, so answering would answer a changed question.

    Measured on git 2.51.0: with `GIT_ATTR_SOURCE=HEAD` alone the planted blob
    reports `attr/text eol=lf` and is a violation; adding `handoff.md -text` to
    `.git/info/attributes` turns the row into `attr/-text` and it disappears.
    That file is local and unversioned, so pre-push would report clean on a
    blob a fresh CI clone still fails.
    """
    repo = _repo_with_crlf_blob(tmp_path)
    _commit(repo, "plant a CRLF blob")
    _info_attributes(repo).write_text("handoff.md -text\n", newline="\n")

    assert checker.main(["--repo-root", str(repo)]) == 2

    assert "outranks the attribute source" in capsys.readouterr().err


def test_an_empty_info_attributes_file_is_allowed(tmp_path: Path) -> None:
    """Control: an empty file changes no attribute, so it must not block."""
    repo = _repo_with_crlf_blob(tmp_path)
    _commit(repo, "plant a CRLF blob")
    _info_attributes(repo).write_text("", newline="\n")

    assert checker.main(["--repo-root", str(repo)]) == 1  # the violation, not a refusal


def test_a_global_attributes_file_cannot_invent_a_violation(tmp_path: Path) -> None:
    """`core.attributesFile` is redirected at an empty file for both scopes.

    It is lower precedence than the pinned tree source, so it cannot hide a
    violation the tree states. It can invent one where the tree is silent, and
    the verdict must be a function of the repository alone either way.
    """
    repo = _repo_with_crlf_blob(tmp_path)
    _git(repo, "config", "core.attributesFile", str(tmp_path / "globalattrs"))
    (tmp_path / "globalattrs").write_text("* eol=lf\n", newline="\n")
    (repo / ".gitattributes").write_text("", newline="\n")
    _git(repo, "add", ".gitattributes")
    _commit(repo, "no attributes of its own")

    violations, _ = checker.check_repository(repo)

    assert violations == []


def test_a_linked_worktree_finds_the_attributes_file_git_reads(tmp_path: Path) -> None:
    """`info/attributes` is a common-directory path, not a worktree-private one.

    Measured in this repository's own worktree: `--absolute-git-dir` returns
    `.git/worktrees/<name>` while `--git-path info/attributes` returns the main
    checkout's `.git/info/attributes`. A check built on the first would never
    find the file git reads, in exactly the setup this repository works in.
    """
    main = _repo_with_crlf_blob(tmp_path)
    _commit(main, "plant a CRLF blob")
    linked = tmp_path / "linked"
    _git(main, "worktree", "add", "--quiet", "--detach", str(linked))
    _info_attributes(main).write_text("handoff.md -text\n", newline="\n")

    private = Path(_git(linked, "rev-parse", "--absolute-git-dir").stdout.strip())
    assert not (private / "info" / "attributes").is_file()  # the wrong place is empty

    with pytest.raises(RuntimeError, match="outranks the attribute source"):
        checker.check_repository(linked)


# --- HEAD that does not resolve is three repositories, not one -------------


def test_an_unborn_repository_still_scans_its_index(tmp_path: Path) -> None:
    """The one state where skipping the HEAD scope is correct."""
    repo = _repo_with_crlf_blob(tmp_path)

    violations, _ = checker.check_repository(repo)

    assert [(v.path, v.scope) for v in violations] == [("handoff.md", "index")]


def test_a_head_pointing_at_a_deleted_branch_fails_closed(tmp_path: Path) -> None:
    """Same `rev-parse` answer as an unborn branch, opposite correct verdict.

    Treating it as unborn skips the committed scope on a repository that does
    have commits, which halves the gate and reports the rest clean.
    """
    repo = _repo_with_crlf_blob(tmp_path)
    _commit(repo, "plant a CRLF blob")
    _git(repo, "symbolic-ref", "HEAD", "refs/heads/gone")

    with pytest.raises(RuntimeError, match="the repository has refs"):
        checker.check_repository(repo)


def test_a_repository_whose_refs_were_removed_fails_closed(tmp_path: Path) -> None:
    """No refs either, but the object database still holds the commits."""
    repo = _repo_with_crlf_blob(tmp_path)
    _commit(repo, "plant a CRLF blob")
    git_dir = Path(_git(repo, "rev-parse", "--absolute-git-dir").stdout.strip())
    _git(repo, "symbolic-ref", "HEAD", "refs/heads/gone")
    # Read the git directory before removing anything: git stops answering
    # `--absolute-git-dir` once `refs/` is gone.
    for name in ("logs",):
        if (git_dir / name).is_dir():
            shutil.rmtree(git_dir / name)
    (git_dir / "packed-refs").unlink(missing_ok=True)
    for entry in (git_dir / "refs").rglob("*"):
        if entry.is_file():
            entry.unlink()

    with pytest.raises(RuntimeError, match="object database still holds commits"):
        checker.check_repository(repo)
