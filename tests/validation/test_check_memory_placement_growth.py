"""Term-growth rule for check_memory_placement.py (issue #6506, review-gates-13).

A file already normative at the base fails when it gains normative terms.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from tests.validation._placement_fixtures import NORMATIVE_HEADING
from tests.validation._placement_repo import MEMORIES, commit_all, git, make_repo, write

_VALIDATION_DIR = Path(__file__).resolve().parents[2] / "scripts" / "validation"
if str(_VALIDATION_DIR) not in sys.path:
    sys.path.insert(0, str(_VALIDATION_DIR))
import check_memory_placement as checker

OLD = f"{MEMORIES}/old.md"
NEW = f"{MEMORIES}/moved/new.md"


@pytest.fixture
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    make_repo(tmp_path)
    monkeypatch.chdir(tmp_path)
    return tmp_path


# --- term growth rule: an already normative file cannot add rules (#6506) ----

MUST_LINE = "The agent MUST do this.\n"


def test_normative_file_that_gains_must_lines_fails(repo, capsys):
    write(repo, OLD, NORMATIVE_HEADING)
    commit_all(repo, "grandfathered")
    write(repo, OLD, NORMATIVE_HEADING + MUST_LINE * 3)
    git(repo, "add", OLD)

    assert checker.main(["--ci", "--staged", "--base", "HEAD", OLD]) == 1
    assert "[normative terms grew from 0]" in capsys.readouterr().out


def test_normative_file_that_gains_a_single_term_fails(repo):
    write(repo, OLD, NORMATIVE_HEADING + MUST_LINE)
    commit_all(repo, "grandfathered")
    write(repo, OLD, NORMATIVE_HEADING + MUST_LINE * 2)

    assert checker.main(["--ci", OLD]) == 1


def test_normative_file_that_drops_or_keeps_terms_passes(repo):
    write(repo, OLD, NORMATIVE_HEADING + MUST_LINE * 3)
    commit_all(repo, "grandfathered")
    write(repo, OLD, NORMATIVE_HEADING + MUST_LINE * 2)
    assert checker.main(["--ci", OLD]) == 0
    write(repo, OLD, NORMATIVE_HEADING + MUST_LINE * 3 + "Plain prose added.\n")
    assert checker.main(["--ci", OLD]) == 0


def test_terms_inside_a_fence_do_not_count_as_growth(repo):
    write(repo, OLD, NORMATIVE_HEADING)
    commit_all(repo, "grandfathered")
    write(repo, OLD, NORMATIVE_HEADING + "```\nMUST MUST MUST\n```\n")

    assert checker.main(["--ci", OLD]) == 0


def test_renamed_normative_file_that_gains_terms_fails(repo):
    write(repo, OLD, NORMATIVE_HEADING)
    commit_all(repo, "grandfathered")
    (repo / NEW).parent.mkdir(parents=True)
    git(repo, "mv", OLD, NEW)
    write(repo, NEW, NORMATIVE_HEADING + MUST_LINE)
    git(repo, "add", NEW)

    assert checker.main(["--ci", "--staged", "--base", "HEAD", NEW]) == 1


def test_term_growth_is_reported_in_json(repo, capsys):
    write(repo, OLD, NORMATIVE_HEADING)
    commit_all(repo, "grandfathered")
    write(repo, OLD, NORMATIVE_HEADING + MUST_LINE)

    code = checker.main(["--ci", "--json", OLD])

    finding = json.loads(capsys.readouterr().out)["findings"][0]
    assert code == 1
    assert finding["grew"] is True
    assert finding["rose"] is False
    assert finding["base_terms"] == 0
