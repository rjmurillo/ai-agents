"""Remediation and path encoding for the line-ending gate (issue #5475).

Split from `test_check_index_line_endings.py` at the 500-line `file-size`
ceiling. These two concerns share a subject: the exact bytes of a tracked path.
`--fix` has to hand git the path git gave, and the report has to render that
path for a human without changing it, which is why a filename carrying shell
syntax, a leading dash, a non-ASCII name under `core.quotePath`, and a byte
sequence that is not valid UTF-8 all land in one module.

The write-target guard is here for the same reason: it is the precondition on
the only code path in the gate that writes anything.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.validation import check_index_line_endings as checker
from tests.validation.index_line_endings_helpers import (
    _commit,
    _git,
    _repo_with_crlf_blob,
    _repo_with_undecodable_crlf_blob,
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
    violations, _ = checker.check_repository(repo)
    assert [v.scope for v in violations] == ["HEAD"]  # index fixed, HEAD awaits commit


def test_fix_mode_then_commit_clears_the_gate(tmp_path: Path, monkeypatch) -> None:
    repo = _repo_with_crlf_blob(tmp_path)
    _commit(repo, "plant a CRLF blob")
    monkeypatch.chdir(repo)

    assert checker.main(["--repo-root", str(repo), "--fix"]) == 1
    _commit(repo, "renormalize")

    assert checker.main(["--repo-root", str(repo)]) == 0


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
    # The refusal must happen before the first write, not after a partial one.
    violations, _ = checker.check_repository(repo)
    assert [v.scope for v in violations] == ["HEAD"]


def test_read_only_mode_still_works_from_outside_the_repo(tmp_path: Path, monkeypatch) -> None:
    """The guard covers --fix only; reporting from anywhere stays allowed."""
    repo = _repo_with_crlf_blob(tmp_path)
    _commit(repo, "plant a CRLF blob")
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)

    assert checker.main(["--repo-root", str(repo)]) == 1


def test_non_ascii_paths_are_reported_raw_not_c_quoted(tmp_path: Path) -> None:
    """Under core.quotePath git would print \\346..., naming a nonexistent file."""
    repo = _repo_with_crlf_blob(tmp_path, name="ハンドオフ.md")
    _git(repo, "config", "core.quotePath", "true")

    violations, _ = checker.check_repository(repo)

    assert [v.path for v in violations] == ["ハンドオフ.md"]


def test_an_undecodable_filename_is_reported_as_the_byte_sequence_git_gave(
    tmp_path: Path,
) -> None:
    """`errors="replace"` would map the bad byte to U+FFFD, irreversibly.

    The gate would then name a file the repository does not hold. Decoding the
    path stream with `surrogateescape` keeps the bytes recoverable, which is
    what lets the reported path still identify the tracked file.
    """
    repo, raw_name = _repo_with_undecodable_crlf_blob(tmp_path)

    violations, _ = checker.check_repository(repo)

    assert len(violations) == 1
    assert violations[0].path.encode("utf-8", "surrogateescape") == raw_name
    assert "�" not in violations[0].path


def test_an_undecodable_filename_is_still_printable(tmp_path: Path, capsys) -> None:
    """Surrogates cannot be written to a UTF-8 stream; the report must not raise.

    Reporting is the gate's whole output path, so a crash here turns a
    detected violation into an unhandled traceback.
    """
    repo, _raw_name = _repo_with_undecodable_crlf_blob(tmp_path)

    assert checker.validate_index_line_endings(repo) is False

    out = capsys.readouterr().out
    assert "bad\\xff.md" in out
    assert "git add --renormalize --" in out


def test_fix_renormalizes_an_undecodable_filename(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The end the display escaping must not reach: what git actually receives.

    `--fix` passes the surrogate-escaped path, and Python re-encodes argv with
    `os.fsencode`, so git gets the original bytes back. A displayed
    `bad\\xff.md` handed to git would name nothing and the violation would
    survive its own remediation.
    """
    repo, _raw_name = _repo_with_undecodable_crlf_blob(tmp_path)
    monkeypatch.chdir(repo)

    assert checker.main(["--repo-root", str(repo), "--fix"]) == 1

    violations, _ = checker.check_repository(repo)
    assert violations == []


def test_display_path_leaves_ordinary_names_alone() -> None:
    """Control: escaping applies to bytes with no text spelling, nothing else."""
    assert checker.display_path("docs/café.md") == "docs/café.md"
    assert checker.display_path("a;$(id).md") == "a;$(id).md"
