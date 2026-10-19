"""A scan that cannot see every rule file, or misreads one, does not pass (issue #6506).

Covers the three silent-skip paths in ``check_rule_adr_citations.py``: an ADR with
an empty status, a tracked file the scan skipped, and a code fence that never closes.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_VALIDATION = _REPO_ROOT / "scripts" / "validation"
if str(_VALIDATION) not in sys.path:
    sys.path.insert(0, str(_VALIDATION))

import check_rule_adr_citations as gate
from check_rule_adr_citations import EXIT_CONFIG, EXIT_OK, EXIT_REGRESSION, citations_in

from tests.validation.test_check_rule_adr_citations import (
    BAD,
    GOOD,
    STATUSES,
    _baseline,
    _git,
    _make_repo,
    _run,
)

# --- ADR status -------------------------------------------------------------


def test_adr_with_an_empty_status_is_counted_not_treated_as_accepted() -> None:
    unknown: set[int] = set()
    found = citations_in("f.md", "Authors MUST comply with ADR-55.\n", {55: ""}, unknown)
    assert found == []
    assert unknown == {55}


def test_adr_with_an_accepted_status_is_not_counted_as_unknown() -> None:
    unknown: set[int] = set()
    citations_in("f.md", "Authors MUST comply with ADR-42.\n", STATUSES, unknown)
    assert unknown == set()


# --- skipped tracked files --------------------------------------------------


def _repo_with_outside_symlink(tmp_path: Path) -> Path:
    outside = tmp_path / "outside.md"
    outside.write_text(GOOD, encoding="utf-8")
    repo = tmp_path / "repo"
    repo.mkdir()
    _make_repo(repo, {"CLAUDE.md": GOOD})
    (repo / "AGENTS.md").symlink_to(outside)
    _git(repo, "add", "--force", "--", "AGENTS.md")
    return repo


def test_a_skipped_tracked_file_is_listed_and_fails_the_run(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = _repo_with_outside_symlink(tmp_path)

    assert _run(repo, _baseline(tmp_path, [])) == EXIT_CONFIG

    err = capsys.readouterr().err
    assert "AGENTS.md: [rule-adr-citation] tracked file is not a regular file" in err
    assert "skipped 1 of 2 tracked rule file(s)" in err


def test_an_in_repo_symlink_to_a_regular_file_is_scanned_not_reported(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = _make_repo(tmp_path, {"CLAUDE.md": GOOD, "notes.md": GOOD})
    (repo / "AGENTS.md").symlink_to(repo / "notes.md")
    _git(repo, "add", "--force", "--", "AGENTS.md")

    assert _run(repo, _baseline(tmp_path, [])) == EXIT_OK
    assert "not a regular file" not in capsys.readouterr().err


# --- unterminated fences ----------------------------------------------------


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("plain text\n", None),
        ("```\ncode\n```\ntext\n", None),
        ("~~~\ncode\n~~~\n", None),
        ("```\ncode\n```", None),
        ("text\n```\nnever closed\nMUST comply with ADR-078.\n", 2),
        ("```python\nopen\n", 1),
        ("~~~\nopen ```\n", 1),
        ("```\nok\n```\n\n~~~\nopen\n", 5),
        ("---\ntitle: x\n---\n```\nopen\n", 4),
    ],
)
def test_unterminated_fence_line(text: str, expected: int | None) -> None:
    assert gate.unterminated_fence_line(text) == expected


def test_unterminated_fence_fails_the_run_and_names_the_line(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The masked tail holds a binding citation the gate would otherwise never see."""
    repo = _make_repo(tmp_path, {"CLAUDE.md": "Intro.\n```\nopen\n" + BAD})

    assert _run(repo, _baseline(tmp_path, [])) == EXIT_REGRESSION

    err = capsys.readouterr().err
    assert "CLAUDE.md:2: [rule-adr-citation] code fence is never closed" in err
    assert "1 unterminated fence(s)" in err


def test_terminated_fence_does_not_fail_the_run(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path, {"CLAUDE.md": "```\ncode\n```\n" + GOOD})
    assert _run(repo, _baseline(tmp_path, [])) == EXIT_OK
