"""CLI contract tests for scripts/metrics_writer.py: argv, stdin, and exit codes.

The append, locking, and symlink behavior of ``safe_append_tally`` is covered in
``tests/test_metrics_writer.py``. This module covers the command line: a line
that starts with ``-`` is data, never a flag, and no argument is positional.
"""

from __future__ import annotations

import io
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import metrics_writer

_TALLY = "2026-06-03T00:00:00Z | pass | none | none"


def _symlink_or_skip(link: Path, target: Path) -> None:
    try:
        link.symlink_to(target)
    except (OSError, NotImplementedError):
        pytest.skip("symlink creation unavailable on this platform; PR #2354 tracks coverage")


# --- CLI argv exit-code contract ---------------------------------------------

_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "metrics_writer.py"

# Text that argparse reads as a flag when it arrives as a positional value.
_FLAG_LIKE_LINES = ["-h", "--help", "--", "-", "--line", "-x"]


class _UndecodableStdin:
    """Stdin whose bytes are not UTF-8, as a binary pipe can deliver."""

    def read(self) -> str:
        raise UnicodeDecodeError("utf-8", b"\xff", 0, 1, "invalid start byte")


class _StdinMustNotBeRead:
    """Stdin that fails the test if the CLI touches it."""

    def read(self) -> str:
        raise AssertionError("--line must not read stdin")


def test_cli_appends_and_exits_zero(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    target = Path("metrics.md")

    rc = metrics_writer.main(["--path", str(target), "--line", _TALLY])

    assert rc == 0
    assert (tmp_path / target).read_text(encoding="utf-8") == _TALLY + "\n"


def test_cli_rejects_symlink_with_exit_one(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    secret = tmp_path / "secret.txt"
    secret.write_text("x", encoding="utf-8")
    link = tmp_path / "metrics.md"
    _symlink_or_skip(link, secret)

    rc = metrics_writer.main(["--path", link.name, "--line", _TALLY])

    assert rc == 1
    assert secret.read_text(encoding="utf-8") == "x"


def test_cli_rejects_absolute_path_outside_cwd(tmp_path: Path, monkeypatch) -> None:
    cwd = tmp_path / "cwd"
    cwd.mkdir()
    outside = tmp_path / "outside" / "metrics.md"
    monkeypatch.chdir(cwd)

    rc = metrics_writer.main(["--path", str(outside), "--line", _TALLY])

    assert rc == 1
    assert not outside.exists()


@pytest.mark.parametrize(
    "argv",
    [
        [],
        ["--path", "tally.md"],
        ["--line", _TALLY],
        ["--stdin"],
        ["--path", "tally.md", "--line", _TALLY, "--stdin"],
    ],
    ids=["no-args", "no-line-source", "no-path", "stdin-without-path", "line-and-stdin"],
)
def test_cli_incomplete_or_conflicting_args_exit_two(argv: list[str], capsys) -> None:
    assert metrics_writer.main(argv) == 2
    assert "usage:" in capsys.readouterr().err


@pytest.mark.parametrize(
    "argv",
    [
        ["tally.md", _TALLY],
        ["--path", "tally.md", _TALLY],
        ["--path", "tally.md", "--line", "a", "extra"],
    ],
    ids=["old-two-positionals", "stray-positional-line", "extra-positional"],
)
def test_cli_rejects_positional_arguments(argv: list[str], tmp_path: Path, monkeypatch) -> None:
    """The old `PATH LINE` form is gone: no positional can be read as a flag."""
    monkeypatch.chdir(tmp_path)

    assert metrics_writer.main(argv) == 2
    assert not (tmp_path / "tally.md").exists()


def test_main_reads_sys_argv_when_argv_none(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        sys, "argv", ["metrics_writer.py", "--path", "metrics.md", "--line", _TALLY]
    )

    assert metrics_writer.main() == 0
    assert (tmp_path / "metrics.md").read_text(encoding="utf-8") == _TALLY + "\n"


def test_cli_help_lists_examples_and_exit_codes(capsys) -> None:
    rc = metrics_writer.main(["--help"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "usage: metrics_writer.py" in out
    assert "--path" in out
    assert "--line" in out
    assert "--stdin" in out
    assert "examples:" in out
    assert "exit codes" in out


def test_cli_unknown_flag_exits_two_on_stderr(capsys) -> None:
    assert metrics_writer.main(["--nope", "x", "y"]) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "invalid arguments" in captured.err


def test_usage_error_never_echoes_argument_values(capsys) -> None:
    secret = "ghp_exampleSecretValue1234567890"

    assert metrics_writer.main(["--path", "a", "--line", "b", secret]) == 2

    assert secret not in capsys.readouterr().err


def test_abbreviated_flags_are_not_accepted(capsys) -> None:
    assert metrics_writer.main(["--path", "tally.md", "--li", "x"]) == 2
    assert capsys.readouterr().out == ""


# --- a dash-led line is data, never a flag ------------------------------------


@pytest.mark.parametrize("line", _FLAG_LIKE_LINES)
def test_flag_like_line_via_equals_form_is_appended_as_data(
    line: str, tmp_path: Path, monkeypatch, capsys
) -> None:
    monkeypatch.chdir(tmp_path)

    rc = metrics_writer.main(["--path", "tally.md", f"--line={line}"])

    assert rc == 0
    assert (tmp_path / "tally.md").read_text(encoding="utf-8") == line + "\n"
    assert capsys.readouterr().out == "", "help text must not print for data"


@pytest.mark.parametrize("line", _FLAG_LIKE_LINES)
def test_flag_like_line_via_stdin_is_appended_as_data(
    line: str, tmp_path: Path, monkeypatch, capsys
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "stdin", io.StringIO(line + "\n"))

    rc = metrics_writer.main(["--path", "tally.md", "--stdin"])

    assert rc == 0
    assert (tmp_path / "tally.md").read_text(encoding="utf-8") == line + "\n"
    assert capsys.readouterr().out == "", "help text must not print for data"


@pytest.mark.parametrize("line", ["-h", "--help"])
def test_flag_like_line_in_separate_argv_slot_is_a_usage_error_not_help(
    line: str, tmp_path: Path, monkeypatch, capsys
) -> None:
    """`--line -h` cannot name data; it must fail closed, never print help and exit 0."""
    monkeypatch.chdir(tmp_path)

    rc = metrics_writer.main(["--path", "tally.md", "--line", line])

    captured = capsys.readouterr()
    assert rc == 2
    assert "Append one tally line" not in captured.out
    assert not (tmp_path / "tally.md").exists()


def test_bare_help_flag_still_prints_help(capsys) -> None:
    assert metrics_writer.main(["-h"]) == 0
    assert "usage: metrics_writer.py" in capsys.readouterr().out


def test_line_with_leading_space_before_dash_is_appended_via_separate_slot(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.chdir(tmp_path)

    rc = metrics_writer.main(["--path", "tally.md", "--line", "- a hyphen line"])

    assert rc == 0
    assert (tmp_path / "tally.md").read_text(encoding="utf-8") == "- a hyphen line\n"


# --- stdin source --------------------------------------------------------------


def test_stdin_line_without_trailing_newline_gets_one(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "stdin", io.StringIO(_TALLY))

    assert metrics_writer.main(["--path", "tally.md", "--stdin"]) == 0
    assert (tmp_path / "tally.md").read_text(encoding="utf-8") == _TALLY + "\n"


def test_empty_stdin_exits_two_and_writes_nothing(tmp_path: Path, monkeypatch, capsys) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "stdin", io.StringIO(""))

    assert metrics_writer.main(["--path", "tally.md", "--stdin"]) == 2
    assert "no line on stdin" in capsys.readouterr().err
    assert not (tmp_path / "tally.md").exists()


def test_undecodable_stdin_exits_two_and_writes_nothing(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "stdin", _UndecodableStdin())

    assert metrics_writer.main(["--path", "tally.md", "--stdin"]) == 2
    assert "not valid UTF-8" in capsys.readouterr().err
    assert not (tmp_path / "tally.md").exists()


def test_line_flag_never_reads_stdin(tmp_path: Path, monkeypatch) -> None:
    """An open pipe on stdin must not block or feed a `--line` call."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "stdin", _StdinMustNotBeRead())

    assert metrics_writer.main(["--path", "tally.md", "--line", _TALLY]) == 0


def test_stdin_source_still_honors_symlink_rejection(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    secret = tmp_path / "secret.txt"
    secret.write_text("x", encoding="utf-8")
    link = tmp_path / "metrics.md"
    _symlink_or_skip(link, secret)
    monkeypatch.setattr(sys, "stdin", io.StringIO(_TALLY))

    assert metrics_writer.main(["--path", link.name, "--stdin"]) == 1
    assert secret.read_text(encoding="utf-8") == "x"


# --- real process boundary ------------------------------------------------------


def _run_script(args: list[str], cwd: Path, stdin: str | None = None):
    return subprocess.run(
        [sys.executable, str(_SCRIPT), *args],
        cwd=cwd,
        input=stdin if stdin is not None else "",
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )


@pytest.mark.parametrize("line", ["-h", "--help"])
def test_subprocess_stdin_flag_like_line_is_data(line: str, tmp_path: Path) -> None:
    result = _run_script(["--path", "tally.md", "--stdin"], tmp_path, stdin=line + "\n")

    assert result.returncode == 0, result.stderr
    assert result.stdout == ""
    assert (tmp_path / "tally.md").read_text(encoding="utf-8") == line + "\n"


@pytest.mark.parametrize("line", ["-h", "--help"])
def test_subprocess_equals_form_flag_like_line_is_data(line: str, tmp_path: Path) -> None:
    result = _run_script(["--path", "tally.md", f"--line={line}"], tmp_path)

    assert result.returncode == 0, result.stderr
    assert result.stdout == ""
    assert (tmp_path / "tally.md").read_text(encoding="utf-8") == line + "\n"
