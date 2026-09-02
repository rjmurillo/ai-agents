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

import os
import subprocess
from pathlib import Path

import pytest

from scripts.validation import check_index_line_endings as checker
from scripts.validation import index_line_endings_record as record
from tests.validation.index_line_endings_helpers import (
    _commit,
    _git,
    _repo_with_crlf_blob,
    _repo_with_undecodable_crlf_blob,
    _staged_against_head,
    posix_only_paths,
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


def test_non_ascii_paths_are_reported_raw_not_c_quoted(tmp_path: Path) -> None:
    """Under core.quotePath git would print \\346..., naming a nonexistent file."""
    repo = _repo_with_crlf_blob(tmp_path, name="ハンドオフ.md")
    _git(repo, "config", "core.quotePath", "true")

    violations, _ = checker.check_repository(repo)

    assert [v.path for v in violations] == ["ハンドオフ.md"]


@posix_only_paths
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


@posix_only_paths
def test_an_undecodable_filename_is_still_printable(tmp_path: Path, capsys) -> None:
    """Surrogates cannot be written to a UTF-8 stream; the report must not raise.

    Reporting is the gate's whole output path, so a crash here turns a
    detected violation into an unhandled traceback.
    """
    repo, _raw_name = _repo_with_undecodable_crlf_blob(tmp_path)

    assert checker.validate_index_line_endings(repo) is False

    out = capsys.readouterr().out
    assert "bad\\xff.md" in out


@posix_only_paths
def test_the_paste_command_for_an_undecodable_path_actually_remediates_it(
    tmp_path: Path, capsys
) -> None:
    """The command is printed for every path, and this one is run to prove it.

    `shlex.quote` cannot express a byte with no text spelling: quoting the
    escaped display form `bad\\xff.md` names a file the repository does not
    hold. bash and zsh can, through `$'...'`, so that is what gets printed and
    what this test executes. Running the printed command is the only assertion
    that distinguishes a command from a plausible string.
    """
    repo, _raw_name = _repo_with_undecodable_crlf_blob(tmp_path)

    assert checker.validate_index_line_endings(repo) is False

    command = next(
        line.strip()
        for line in capsys.readouterr().out.split("\n")
        if line.strip().startswith("git add --renormalize --")
    )
    assert "$'bad\\xff.md'" in command
    subprocess.run(
        ["bash", "-c", command],
        cwd=repo,
        check=True,
        capture_output=True,
        timeout=60,
        env={k: v for k, v in os.environ.items() if not k.upper().startswith("GIT_")},
    )

    violations, _ = checker.check_repository(repo)
    assert violations == []  # the printed command cleared the gate


@posix_only_paths
def test_the_paste_command_names_the_shells_its_second_form_needs(
    tmp_path: Path, capsys
) -> None:
    """POSIX sh has no escape for those bytes, so the note is not decoration."""
    repo, _raw_name = _repo_with_undecodable_crlf_blob(tmp_path)

    assert checker.validate_index_line_endings(repo) is False

    out = capsys.readouterr().out
    assert "1 of 1 path(s) carry bytes with no text spelling" in out
    assert "bash and zsh" in out


def test_the_paste_command_stays_plain_when_every_path_is_spellable(
    tmp_path: Path, capsys
) -> None:
    """Control: an ordinary name must not acquire a shell-specific spelling."""
    repo = _repo_with_crlf_blob(tmp_path, name="a handoff.md")

    assert checker.validate_index_line_endings(repo) is False

    out = capsys.readouterr().out
    assert "git add --renormalize -- 'a handoff.md'" in out
    assert "$'" not in out
    assert "bash and zsh" not in out


@posix_only_paths
def test_a_newline_in_a_path_cannot_forge_a_log_line(tmp_path: Path, capsys) -> None:
    """CWE-117: a contributor picks the filename, and this output is a CI log.

    A tracked path may legally contain a newline on POSIX. Printed unchanged
    it splits one report line into two, and the second one is whatever the
    contributor wrote.
    """
    forged = "  index-line-endings: 0 violation(s)"
    repo = _repo_with_crlf_blob(tmp_path, name=f"handoff.md\n{forged}")

    assert checker.validate_index_line_endings(repo) is False

    out = capsys.readouterr().out
    assert f"\n{forged}\n" not in out
    assert "handoff.md\\n" in out
    # The command carries the same path, and must not un-escape it there: the
    # `$'...'` body is where the newline would otherwise become a real one.
    assert "$'handoff.md\\x0a" in out


def test_a_bidi_override_in_a_path_cannot_disguise_it(tmp_path: Path, capsys) -> None:
    """CWE-451: U+202E reverses what follows, so the log names a different file.

    It is not a control character, so an ASCII-only escape class lets it
    through into the same required CI log.
    """
    repo = _repo_with_crlf_blob(tmp_path, name="handoff\u202edm.txt")

    assert checker.validate_index_line_endings(repo) is False

    out = capsys.readouterr().out
    assert "\u202e" not in out
    assert "handoff\\u202edm.txt" in out
    # Escaped in the command too, as the UTF-8 bytes of U+202E.
    assert "$'handoff\\xe2\\x80\\xaedm.txt'" in out


@posix_only_paths
def test_an_escape_sequence_in_a_path_cannot_repaint_the_terminal(
    tmp_path: Path, capsys
) -> None:
    """The other half of CWE-117: ESC rewrites what the reader sees."""
    repo = _repo_with_crlf_blob(tmp_path, name="handoff\x1b[2K.md")

    assert checker.validate_index_line_endings(repo) is False

    out = capsys.readouterr().out
    assert "\x1b" not in out
    assert "handoff\\x1b[2K.md" in out


@posix_only_paths
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
    """Control: escaping applies to bytes with no safe text spelling, nothing else."""
    assert record.display_path("docs/café.md") == "docs/café.md"
    assert record.display_path("a;$(id).md") == "a;$(id).md"
    assert record.is_spellable("docs/café.md")
    assert record.is_spellable("a;$(id).md")


def test_display_path_escapes_every_unsafe_category() -> None:
    """Cc, Cf, Zl and Zp all reach a log looking like something else.

    Cc forges or repaints a line. Cf is invisible, and the bidi controls
    reorder what follows, so the reader sees a filename the repository does
    not hold (CWE-451). Zl and Zp break the line without being Cc.
    """
    for path, expected in (
        ("a\nb", "a\\nb"),  # Cc
        ("a\tb", "a\\tb"),  # Cc
        ("a\rb", "a\\rb"),  # Cc
        ("a\x1bb", "a\\x1bb"),  # Cc, ESC
        ("a\x7fb", "a\\x7fb"),  # Cc, DEL
        ("a\x9bb", "a\\x9bb"),  # Cc, C1
        ("a\u202eb", "a\\u202eb"),  # Cf, right-to-left override
        ("a\u200bb", "a\\u200bb"),  # Cf, zero-width space
        ("a\ufeffb", "a\\ufeffb"),  # Cf, byte order mark
        ("a\u2028b", "a\\u2028b"),  # Zl
        ("a\u2029b", "a\\u2029b"),  # Zp
    ):
        assert record.display_path(path) == expected
        assert not record.is_spellable(path)
