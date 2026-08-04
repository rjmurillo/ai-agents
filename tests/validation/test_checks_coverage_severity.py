"""Severity tokens the review-marker gate forwards must match its verdict.

Issue #4315: ``validate_review_marker`` is advisory by default and returns
True on a missing or stale marker, but it forwarded the wrapped script's
``[FAIL]`` line verbatim first. A passing check therefore printed a line
byte-identical in shape to a blocking failure, and the reader had to reconcile
it against the ``RESULT:`` count at the bottom of a long pre-push log.

These tests drive the real wrapped script against a real git repository rather
than a mocked subprocess, so they observe the token a contributor actually
sees.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

import pytest

from scripts.validation.checks_coverage import (
    _as_advisory,
    _print_output,
    validate_review_marker,
)

_REPO_ROOT = Path(__file__).resolve().parents[2]


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


def _repo(tmp_path: Path, *, with_script: bool) -> Path:
    """Build a repository whose HEAD changes files and carries no marker."""
    repo = tmp_path / "repo"
    repo.mkdir()
    if with_script:
        dest = repo / "scripts" / "validation"
        dest.mkdir(parents=True)
        source = _REPO_ROOT / "scripts" / "validation" / "validate_review_marker.py"
        (dest / "validate_review_marker.py").write_text(
            source.read_text(encoding="utf-8"), encoding="utf-8"
        )

    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "t@example.com")
    _git(repo, "config", "user.name", "Tester")
    _git(repo, "config", "commit.gpgsign", "false")
    (repo / "a.txt").write_text("x\n", encoding="utf-8")
    _git(repo, "add", "a.txt")
    _git(repo, "commit", "-q", "-m", "feat: one")
    (repo / "b.txt").write_text("y\n", encoding="utf-8")
    _git(repo, "add", "b.txt")
    _git(repo, "commit", "-q", "-m", "feat: two")
    return repo


def test_advisory_failure_prints_warn_and_never_fail(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: Any,  # noqa: ANN401
) -> None:
    repo = _repo(tmp_path, with_script=True)
    monkeypatch.delenv("REVIEW_MARKER_ENFORCED", raising=False)

    passed = validate_review_marker(repo)

    captured = capsys.readouterr().out
    assert passed is True
    assert "[FAIL]" not in captured
    assert "[WARN]" in captured
    assert "a review marker must be an empty commit" in captured


def test_enforced_failure_keeps_the_fail_token(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: Any,  # noqa: ANN401
) -> None:
    repo = _repo(tmp_path, with_script=True)
    monkeypatch.setenv("REVIEW_MARKER_ENFORCED", "1")

    passed = validate_review_marker(repo)

    captured = capsys.readouterr().out
    assert passed is False
    assert "[FAIL]" in captured


def test_missing_script_advisory_still_warns(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: Any,  # noqa: ANN401
) -> None:
    repo = _repo(tmp_path, with_script=False)
    monkeypatch.delenv("REVIEW_MARKER_ENFORCED", raising=False)

    passed = validate_review_marker(repo)

    captured = capsys.readouterr().out
    assert passed is True
    assert "[WARN] validate_review_marker.py not found (advisory skip)" in captured
    assert "[FAIL]" not in captured


def test_as_advisory_downgrades_a_leading_token_and_keeps_indent() -> None:
    assert _as_advisory("[FAIL] no marker") == "[WARN] no marker"
    assert _as_advisory("  [FAIL] no marker") == "  [WARN] no marker"


def test_as_advisory_leaves_a_non_leading_token_alone() -> None:
    line = "grep for [FAIL] in the log"

    assert _as_advisory(line) == line


def test_as_advisory_leaves_unrelated_lines_alone() -> None:
    assert _as_advisory("[OK] marker binds HEAD") == "[OK] marker binds HEAD"
    assert _as_advisory("") == ""


def _marker_line_count(captured: str) -> int:
    """Count how many times the wrapped script's verdict line was forwarded."""
    return sum(
        1 for line in captured.splitlines() if "a review marker must be an empty commit" in line
    )


def test_advisory_failure_forwards_each_line_once(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: Any,  # noqa: ANN401
) -> None:
    """The verdict line is printed on the exit path only, never twice.

    An earlier revision printed the wrapped output unconditionally before the
    verdict was known, and then again from the branch that knew it. Both copies
    were correct in isolation, so a severity-only assertion cannot see the
    duplicate.
    """
    repo = _repo(tmp_path, with_script=True)
    monkeypatch.delenv("REVIEW_MARKER_ENFORCED", raising=False)

    validate_review_marker(repo)

    assert _marker_line_count(capsys.readouterr().out) == 1


def test_enforced_failure_forwards_each_line_once(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: Any,  # noqa: ANN401
) -> None:
    repo = _repo(tmp_path, with_script=True)
    monkeypatch.setenv("REVIEW_MARKER_ENFORCED", "1")

    validate_review_marker(repo)

    assert _marker_line_count(capsys.readouterr().out) == 1


def test_print_output_downgrade_spares_a_non_leading_token(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Forwarding must reuse the leading-token rule, not a bare substring swap.

    ``_as_advisory`` is unit-tested for this, but that proves nothing about the
    forwarder unless the forwarder actually calls it. A ``str.replace`` here
    passes every other test in this file and still rewrites a ``[FAIL]`` that
    the wrapped script printed as content rather than as a verdict.
    """
    line = "grep for [FAIL] in the log"

    _print_output(line, rewrite_fail_to_warn=True)

    assert capsys.readouterr().out.strip() == line


def test_print_output_downgrade_still_rewrites_a_leading_token(
    capsys: pytest.CaptureFixture[str],
) -> None:
    _print_output("[FAIL] no marker", rewrite_fail_to_warn=True)

    assert capsys.readouterr().out.strip() == "[WARN] no marker"
