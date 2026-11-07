"""CLI contract of prepare_pr_body.py: --help, --base, and usage errors."""

from __future__ import annotations

import importlib.util
import subprocess
from pathlib import Path

import pytest

_SCRIPT = (
    Path(__file__).resolve().parents[1]
    / ".claude"
    / "skills"
    / "github"
    / "scripts"
    / "pr"
    / "prepare_pr_body.py"
)
_SPEC = importlib.util.spec_from_file_location("prepare_pr_body_cli", _SCRIPT)
assert _SPEC and _SPEC.loader
_MODULE = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_MODULE)


@pytest.fixture(autouse=True)
def _git_repo_with_base(tmp_path: Path) -> None:
    """Make tmp_path a repo whose origin/main exists, so the seed read succeeds."""
    for args in (
        ("init", "-q", "-b", "main"),
        (
            "-c",
            "user.name=t",
            "-c",
            "user.email=t@example.com",
            "commit",
            "-q",
            "--allow-empty",
            "-m",
            "base",
        ),
        ("update-ref", "refs/remotes/origin/main", "HEAD"),
    ):
        subprocess.run(["git", "-C", str(tmp_path), *args], check=True, capture_output=True)


def test_help_documents_exit_codes_and_creates_no_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(tmp_path)

    rc = _MODULE.main(["--help"])

    out = capsys.readouterr().out
    assert rc == 0
    assert "exit codes" in out
    assert "example" in out
    assert not (tmp_path / ".project-toolkit").exists()


def test_unknown_flag_exits_two_and_creates_no_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(tmp_path)

    rc = _MODULE.main(["--bogus"])

    captured = capsys.readouterr()
    assert rc == 2
    assert captured.out == ""
    assert "unrecognized arguments" in captured.err
    assert not (tmp_path / ".project-toolkit").exists()


def test_main_prints_the_created_path_on_stdout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(tmp_path)

    rc = _MODULE.main([])

    printed = capsys.readouterr().out.strip()
    assert rc == 0
    assert (tmp_path / printed).is_file()


def test_base_flag_is_passed_to_prepare_pr_body(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    seen: list[str | None] = []

    def fake(_root: Path, base_ref: str | None = None) -> Path:
        seen.append(base_ref)
        return Path(".project-toolkit/scratch/pr-body-x.md")

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(_MODULE, "prepare_pr_body", fake)

    assert _MODULE.main(["--base", "origin/develop"]) == 0
    assert _MODULE.main([]) == 0
    assert seen == ["origin/develop", None]
    assert capsys.readouterr().out.count("pr-body-x.md") == 2


def test_base_flag_without_a_value_exits_two(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(tmp_path)

    assert _MODULE.main(["--base"]) == 2
    assert capsys.readouterr().out == ""
    assert not (tmp_path / ".project-toolkit").exists()
