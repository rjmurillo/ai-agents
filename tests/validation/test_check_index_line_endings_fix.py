"""Remediation and path encoding for the line-ending gate (issue #5475).

Split from `test_check_index_line_endings.py` at the 500-line `file-size`
ceiling. These two concerns share a subject: the exact bytes of a tracked path.
`--fix` has to hand git the path git gave, and the report has to render that
path for a human without changing it, which is why a filename carrying shell
syntax, a leading dash, a non-ASCII name under `core.quotePath`, and a byte
sequence that is not valid UTF-8 all land in one module.

The write-target guard is here for the same reason: it is the precondition on
the only code path in the gate that writes anything. The path bytes themselves
moved to `test_check_index_line_endings_paths.py` at the file-size ceiling.
"""

from __future__ import annotations

from pathlib import Path

from scripts.validation import check_index_line_endings as checker
from scripts.validation.check_index_line_endings import REMEDIATION
from tests.validation.index_line_endings_helpers import (
    _commit,
    _git,
    _repo_with_crlf_blob,
    _staged_against_head,
)


def test_remediation_command_quotes_paths_with_spaces(tmp_path: Path, capsys) -> None:
    """An unquoted join would print a command that renormalizes the wrong files."""
    repo = _repo_with_crlf_blob(tmp_path, name="a handoff.md")

    assert checker.validate_index_line_endings(repo) is False

    out = capsys.readouterr().out
    assert "git add --renormalize -- 'a handoff.md'" in out


# --- --fix mode (review thread on the advertised command, CWE-78) ----------


def test_fix_mode_renormalizes_without_building_a_shell_string(
    tmp_path: Path, monkeypatch
) -> None:
    """A filename carrying shell syntax must be inert, not executed.

    `--fix` passes paths to git as argv entries, so the quoting of the printed
    command is never load-bearing for anyone who uses it.
    """
    repo = _repo_with_crlf_blob(tmp_path, name="a;$(touch pwned).md")
    _commit(repo, "plant a CRLF blob under a hostile name")
    monkeypatch.chdir(repo)

    assert checker.main(["--repo-root", str(repo), "--fix"]) == 1

    assert not (repo / "pwned").exists()
    assert _staged_against_head(repo) == ["a;$(touch pwned).md"]  # the blob was renormalized


def test_fix_mode_renormalizes_a_leading_dash_filename(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    """The `--` terminator is the only thing this case depends on.

    `--intent-to-add` is a real `git add` option, so without the terminator
    git rejects the argument as an unknown option and the run exits 2 with the
    violating blob untouched. The printed command carries the terminator for
    the same reason: pasted without it, it does not remediate either.
    """
    repo = _repo_with_crlf_blob(tmp_path, name="--intent-to-add.md")
    _commit(repo, "plant a CRLF blob under a leading-dash name")
    monkeypatch.chdir(repo)

    assert checker.main(["--repo-root", str(repo), "--fix"]) == 1

    assert "git add --renormalize -- --intent-to-add.md" in capsys.readouterr().out
    assert _staged_against_head(repo) == ["--intent-to-add.md"]  # the blob was renormalized


def test_fix_refuses_to_claim_a_renormalize_the_working_tree_prevented(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    """`git add` reads the working tree; this gate judges by the staged index.

    Measured on git 2.51.0 with `*.md text` staged and an unstaged
    `handoff.md -text` on disk: the gate reports the staged CRLF blob,
    `git add --renormalize` exits 0, and the index blob is still `i/crlf`.
    Printing "renormalized 1 path(s); commit the result" over that is worse
    than offering no `--fix` at all, because the operator commits and pushes
    believing it is fixed.
    """
    repo = _repo_with_crlf_blob(tmp_path)
    (repo / ".gitattributes").write_text(
        "* text=auto eol=lf\n*.md text\nhandoff.md -text\n", newline="\n"
    )
    monkeypatch.chdir(repo)

    assert checker.main(["--repo-root", str(repo), "--fix"]) == 2

    err = capsys.readouterr().err
    assert "still contradicting their staged attributes" in err
    assert "handoff.md" in err


def test_fix_reports_success_only_when_the_blob_actually_changed(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    """Control: with the attributes agreeing, the success line is earned."""
    repo = _repo_with_crlf_blob(tmp_path)
    _commit(repo, "plant a CRLF blob")
    monkeypatch.chdir(repo)

    assert checker.main(["--repo-root", str(repo), "--fix"]) == 1

    assert "renormalized 1 path(s); commit the result" in capsys.readouterr().out
    assert _staged_against_head(repo) == ["handoff.md"]


def test_a_scan_started_from_a_subdirectory_still_sees_the_whole_tree(
    tmp_path: Path, monkeypatch
) -> None:
    """`git ls-files` lists the subtree under its working directory.

    Measured on git 2.51.0 against a repository holding one bad blob under
    `other/`: `git ls-files --eol` returns 2 rows from the top level and 0 from
    `sub/`. With `--repo-root` defaulting to `.`, running the CLI from anywhere
    but the root would exit 0 over a repository this gate exists to fail.
    """
    repo = _repo_with_crlf_blob(tmp_path, name="other/bad.md")
    # Committed, so the HEAD scope runs. The index scope is already immune:
    # it points `GIT_DIR` at the repository and runs git from an empty
    # directory outside it, so no working directory scopes it.
    _commit(repo, "plant a CRLF blob under other/")
    subdirectory = repo / "sub"
    subdirectory.mkdir()
    monkeypatch.chdir(subdirectory)

    violations, _ = checker.check_repository(Path.cwd())

    assert [(v.path, v.scope) for v in violations] == [("other/bad.md", "HEAD")]
    assert checker.main(["--repo-root", "."]) == 1


def test_fix_refuses_to_stage_an_unrelated_working_tree_edit(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    """`git add --renormalize` stages the working copy, not a cleaned blob.

    Measured on git 2.51.0: with an unstaged line added to a violating file,
    `--fix` exited 0 and the staged blob then contained that line. The
    operator asked for a line-ending fix and got someone's uncommitted work
    staged with it.
    """
    repo = _repo_with_crlf_blob(tmp_path)
    _commit(repo, "plant a CRLF blob")
    (repo / "handoff.md").write_bytes(b"line one\r\nline two\r\nUNRELATED EDIT\r\n")
    monkeypatch.chdir(repo)

    assert checker.main(["--repo-root", str(repo), "--fix"]) == 2

    err = capsys.readouterr().err
    assert "uncommitted working-tree changes beyond line endings" in err
    assert "handoff.md" in err
    assert _staged_against_head(repo) == []  # nothing was staged


def test_fix_refuses_when_the_violating_file_was_deleted_locally(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    """The same guard covers the case git would have failed on outright.

    Measured on git 2.51.0: `git add --renormalize` on a locally deleted file
    exits 128 with `unable to stat`. A named refusal beats git's error.
    """
    repo = _repo_with_crlf_blob(tmp_path)
    _commit(repo, "plant a CRLF blob")
    (repo / "handoff.md").unlink()
    monkeypatch.chdir(repo)

    assert checker.main(["--repo-root", str(repo), "--fix"]) == 2

    assert "uncommitted working-tree changes beyond line endings" in capsys.readouterr().err


def test_fix_still_runs_when_only_line_endings_differ(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    """Control, and the reason `--name-only` is the wrong predicate.

    Every legitimate target of this gate has a working copy that differs from
    the index by CR at end of line, so a guard that fired on that would block
    the fix it exists to protect.
    """
    repo = _repo_with_crlf_blob(tmp_path)
    _commit(repo, "plant a CRLF blob")
    monkeypatch.chdir(repo)

    assert checker.main(["--repo-root", str(repo), "--fix"]) == 1

    assert "renormalized 1 path(s); commit the result" in capsys.readouterr().out


def test_fix_mode_then_commit_clears_the_gate(tmp_path: Path, monkeypatch) -> None:
    repo = _repo_with_crlf_blob(tmp_path)
    _commit(repo, "plant a CRLF blob")
    monkeypatch.chdir(repo)

    assert checker.main(["--repo-root", str(repo), "--fix"]) == 1
    _commit(repo, "renormalize")

    assert checker.main(["--repo-root", str(repo)]) == 0


def test_fix_skips_a_head_only_path_the_index_no_longer_holds(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    """A staged deletion clears the gate on commit; `git add` cannot help it.

    Measured on git 2.51.0: `git add --renormalize -- h.md` on a path staged
    for deletion exits 128 with `fatal: pathspec 'h.md' did not match any
    files`. Passing the reported violations to git therefore fails both
    advertised remediations on a repository whose staged removal would have
    cleared the gate on its own.
    """
    repo = _repo_with_crlf_blob(tmp_path)
    _commit(repo, "plant a CRLF blob")
    _git(repo, "rm", "--quiet", "--cached", "handoff.md")
    (repo / "handoff.md").unlink()
    monkeypatch.chdir(repo)

    assert checker.main(["--repo-root", str(repo), "--fix"]) == 1  # HEAD still bad

    out = capsys.readouterr().out
    assert "[CRLF] handoff.md: HEAD blob is i/crlf" in out
    assert "renormalized" not in out  # nothing to add, so nothing is claimed
    # The printed command has the same limit as `--fix`: `git add` would fail
    # with `pathspec ... did not match any files` on a path the index dropped.
    assert "git add --renormalize --" not in out
    assert "1 path(s) are wrong in HEAD only" in out
    assert "commit the staged result" in out
    # And no contradicting advice alongside it: renormalizing is a no-op here.
    assert REMEDIATION not in out
    assert "re-run this check with --fix" not in out


def test_fix_mode_on_a_clean_repository_is_a_no_op(tmp_path: Path, monkeypatch) -> None:
    repo = _repo_with_crlf_blob(tmp_path)
    _git(repo, "add", "--renormalize", "handoff.md")
    _commit(repo, "clean from the start")
    monkeypatch.chdir(repo)

    assert checker.main(["--repo-root", str(repo), "--fix"]) == 0


def test_fix_refuses_to_write_a_repo_the_process_is_not_inside(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    """ci-scripts.md MUST-7: confirm cwd is inside the root before writing.

    Otherwise a mistyped --repo-root stages changes in a checkout nobody was
    looking at and leaves them for someone else to find.
    """
    repo = _repo_with_crlf_blob(tmp_path)
    _commit(repo, "plant a CRLF blob")
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)

    assert checker.main(["--repo-root", str(repo), "--fix"]) == 2

    assert "Refusing to renormalize" in capsys.readouterr().err
    # The refusal must land before the first write, not after a partial one.
    # A violation-scope assertion cannot say that: `check_repository` reports a
    # path bad in both scopes once under HEAD, which is also what it reports
    # after a renormalize. An empty staged diff is the write itself, absent.
    assert _staged_against_head(repo) == []


def test_fix_refuses_when_core_worktree_redirects_git_elsewhere(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    """`--repo-root` is a claim about the tree; `--show-toplevel` is the answer.

    A repository-local `core.worktree` redirects git while the typed root still
    looks right, so a guard that compares the current directory to `--repo-root`
    passes and `--fix` stages into a checkout the operator is not standing in.
    Measured on git 2.51.0: with `core.worktree` set to a sibling directory,
    `git rev-parse --show-toplevel` run from inside the checkout returns the
    sibling.
    """
    repo = _repo_with_crlf_blob(tmp_path)
    _commit(repo, "plant a CRLF blob")
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    _git(repo, "config", "core.worktree", str(elsewhere))
    monkeypatch.chdir(repo)  # standing in the root the operator typed

    assert checker.main(["--repo-root", str(repo), "--fix"]) == 2

    err = capsys.readouterr().err
    assert "Refusing to renormalize" in err
    assert str(elsewhere) in err  # the tree git chose, not the one typed
    assert _staged_against_head(repo) == []


def test_read_only_mode_still_works_from_outside_the_repo(tmp_path: Path, monkeypatch) -> None:
    """The guard covers --fix only; reporting from anywhere stays allowed."""
    repo = _repo_with_crlf_blob(tmp_path)
    _commit(repo, "plant a CRLF blob")
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)

    assert checker.main(["--repo-root", str(repo)]) == 1
