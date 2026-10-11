"""CLI tests for the CLI smoke path filter (REQ-047 AC10).

``main`` writes ``run=true`` or ``run=false`` to ``GITHUB_OUTPUT`` and fails
closed when the diff cannot be computed.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.validation import cli_smoke_paths as paths

_SHA_A = "a" * 40
_SHA_B = "b" * 40


Capsys = pytest.CaptureFixture[str]
_PR = ["--event-name", "pull_request", "--base", _SHA_A, "--head", _SHA_B]


def _main_with_diff(monkeypatch: pytest.MonkeyPatch, changed: list[str]) -> int:
    monkeypatch.setattr(paths, "changed_files", lambda *_a: changed)
    return paths.main(_PR)


def test_main_dispatch_writes_true_without_git(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: Capsys
) -> None:
    out = tmp_path / "out.txt"
    monkeypatch.setenv("GITHUB_OUTPUT", str(out))
    monkeypatch.setattr(paths, "changed_files", lambda *_a: pytest.fail("git must not run"))

    assert paths.main(["--event-name", "workflow_dispatch"]) == paths.EXIT_OK
    assert out.read_text(encoding="utf-8") == "run=true\n"
    assert "run=true" in capsys.readouterr().out


@pytest.mark.parametrize(
    ("changed", "expected"),
    [(["src/claude/skills/x.md"], "true"), (["README.md"], "false"), ([], "false")],
)
def test_main_writes_the_decision(
    changed: list[str], expected: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    out = tmp_path / "out.txt"
    monkeypatch.setenv("GITHUB_OUTPUT", str(out))

    assert _main_with_diff(monkeypatch, changed) == paths.EXIT_OK
    assert out.read_text(encoding="utf-8") == f"run={expected}\n"


def test_main_fails_closed_when_the_diff_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: Capsys
) -> None:
    out = tmp_path / "out.txt"
    monkeypatch.setenv("GITHUB_OUTPUT", str(out))

    def boom(*_a: object) -> list[str]:
        raise paths.DiffError("bad object")

    monkeypatch.setattr(paths, "changed_files", boom)

    assert paths.main(_PR) == paths.EXIT_LOGIC
    assert not out.exists()
    assert "bad object" in capsys.readouterr().err


@pytest.mark.parametrize(
    "argv",
    [
        ["--event-name", "pull_request", "--base", _SHA_A],
        ["--event-name", "pull_request", "--head", _SHA_B],
        ["--event-name", "pull_request"],
        ["--event-name", "pull_request", "--base", "", "--head", ""],
        ["--event-name", "push", "--base", _SHA_A, "--head", _SHA_B],
        ["--event-name", "schedule"],
        [],
    ],
)
def test_main_rejects_missing_arguments_and_unknown_events(argv: list[str]) -> None:
    with pytest.raises(SystemExit) as exc:
        paths.main(argv)
    assert exc.value.code == paths.EXIT_USAGE


@pytest.mark.parametrize(
    ("changed", "present", "absent"),
    [
        ([], ["run=false"], []),
        (["README.md"], ["run=false"], ["match the smoke path filter"]),
        (["README.md", "src/claude/x.md"], ["1 changed path(s) match", "run=true"], ["README.md"]),
    ],
    ids=["empty", "no-match", "match"],
)
def test_main_prints_the_report_without_github_output(
    changed: list[str],
    present: list[str],
    absent: list[str],
    monkeypatch: pytest.MonkeyPatch,
    capsys: Capsys,
) -> None:
    monkeypatch.delenv("GITHUB_OUTPUT", raising=False)

    assert _main_with_diff(monkeypatch, changed) == paths.EXIT_OK
    out = capsys.readouterr().out
    assert all(text in out for text in present)
    assert not any(text in out for text in absent)
    if "src/claude/x.md" in changed:
        assert out.index("src/claude/x.md") < out.index("run=true")
