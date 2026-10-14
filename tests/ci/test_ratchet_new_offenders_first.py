"""A regression lists the violations the branch added before the existing ones.

``run`` caps the printed list at 40 lines and this repository carries several
hundred existing violations. Ordering by "files the branch touched" is not
enough: a branch that edits many already-failing files still buries the one
violation it added. ``new_offenders_first`` diffs the current list against the
list at the merge base, so the added entry leads whatever the scan order.

Git is the boundary under test and is not mocked. The end-to-end case drives
the real taste linter, because the defect lives in the seam between the lister
and the merge-base scan, which a fake lister cannot show.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from scripts.ci import base_derived_ratchet as brd
from scripts.ci import taste_count_ratchet
from tests.ci.count_ratchet_git_harness import commit_all, git, init_repo

needs_git = pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")

_LINTER_RELATIVE = Path(".claude/skills/taste-lints/scripts/taste_lints.py")
_MARKER = "scripts/ci/marker_ratchet.py"


# ---------------------------------------------------------------------------
# new_offenders_first: the pure half
# ---------------------------------------------------------------------------


def test_an_entry_absent_from_the_base_moves_to_the_front_marked_new():
    current = ["a.py: x", "b.py: x", "c.py: x"]

    ordered, fresh = brd.new_offenders_first(current, ["a.py: x", "b.py: x"])

    assert ordered == ["NEW c.py: x", "a.py: x", "b.py: x"]
    assert fresh == 1


def test_nothing_new_keeps_scan_order_and_marks_nothing():
    current = ["a.py: x", "b.py: x"]

    ordered, fresh = brd.new_offenders_first(current, ["b.py: x", "a.py: x"])

    assert ordered == current
    assert fresh == 0


def test_a_second_occurrence_of_one_identity_is_the_new_one():
    """Edge: two violations of one identity at the head, one at the base."""
    ordered, fresh = brd.new_offenders_first(["a.py: x", "a.py: x"], ["a.py: x"])

    assert ordered == ["NEW a.py: x", "a.py: x"]
    assert fresh == 1


def test_a_violation_fixed_since_the_base_does_not_hide_a_new_one():
    """Edge: the base held entries the branch removed."""
    ordered, fresh = brd.new_offenders_first(["a.py: x", "n.py: x"], ["gone.py: x", "a.py: x"])

    assert ordered == ["NEW n.py: x", "a.py: x"]
    assert fresh == 1


def test_an_empty_base_marks_every_entry_new():
    ordered, fresh = brd.new_offenders_first(["a.py: x", "b.py: x"], [])

    assert ordered == ["NEW a.py: x", "NEW b.py: x"]
    assert fresh == 2


def test_an_identity_function_decides_what_counts_as_the_same_violation():
    """A message embedding a measurement must not make a grown file look new."""
    current = ["a.py: [file-size] (600 lines)"]
    base = ["a.py: [file-size] (550 lines)"]

    by_line, fresh_by_line = brd.new_offenders_first(current, base)
    by_head, fresh_by_head = brd.new_offenders_first(
        current, base, taste_count_ratchet.violation_identity
    )

    assert fresh_by_line == 1, "the control: the rendered line alone calls the grown file new"
    assert by_line == ["NEW a.py: [file-size] (600 lines)"]
    assert fresh_by_head == 0
    assert by_head == current


@pytest.mark.parametrize(
    ("line", "expected"),
    [
        ("big.py: [file-size] File exceeds 500 lines (566 lines)", "big.py: [file-size]"),
        ("a/b c.py: [naming] Name is odd", "a/b c.py: [naming]"),
        ("no rule head here", "no rule head here"),
    ],
)
def test_the_taste_identity_keeps_the_file_and_rule_only(line: str, expected: str) -> None:
    assert taste_count_ratchet.violation_identity(line) == expected


# ---------------------------------------------------------------------------
# run: the printed list, with a fake counter and lister over a real repo
# ---------------------------------------------------------------------------


def _write_tree(repo: Path, count: int, lines: list[str]) -> None:
    (repo / "count.txt").write_text(f"{count}\n", encoding="utf-8")
    (repo / "violations.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    marker = repo / _MARKER
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text("# marker\n", encoding="utf-8")


def _counter(root: Path) -> int | None:
    return int((root / "count.txt").read_text(encoding="utf-8").strip())


def _tree_lister(root: Path, _changed: frozenset[str]) -> list[str] | None:
    path = root / "violations.txt"
    if not path.is_file():
        return None
    return path.read_text(encoding="utf-8").splitlines()


def _regressed_repo(tmp_path: Path, existing: int) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    init_repo(repo)
    base = [f"old{index:03d}.py: [r] m" for index in range(existing)]
    _write_tree(repo, existing, base)
    commit_all(repo, "base")
    git(repo, "checkout", "-qb", "topic")
    _write_tree(repo, existing + 1, [*base, "zzz_new.py: [r] m"])
    commit_all(repo, "topic")
    return repo


def _run(repo: Path, lister: brd.Lister) -> int:
    args = brd.build_parser("test").parse_args(["--repo-root", str(repo), "--base-ref", "main"])
    return brd.run(
        args,
        label="fake ratchet",
        counter=_counter,
        scan_error="fake scan failed",
        regression_advice="Remove the violations.",
        introduced_by=_MARKER,
        lister=lister,
    )


@needs_git
def test_the_added_violation_prints_first_when_it_sits_past_the_cap(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = _regressed_repo(tmp_path, existing=60)

    code = _run(repo, _tree_lister)

    err = capsys.readouterr().err
    printed = [line.strip() for line in err.splitlines() if line.startswith("  ")]
    assert code == brd.EXIT_REGRESSION
    assert "1 new since the merge base" in err
    assert "NEW zzz_new.py: [r] m" in printed
    assert printed.index("NEW zzz_new.py: [r] m") < printed.index("old000.py: [r] m")
    assert "... and 21 more" in err


@needs_git
def test_an_unreadable_merge_base_list_still_prints_and_says_so(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = _regressed_repo(tmp_path, existing=3)

    def lister(root: Path, changed: frozenset[str]) -> list[str] | None:
        return _tree_lister(root, changed) if root == repo.resolve() else None

    code = _run(repo, lister)

    err = capsys.readouterr().err
    assert code == brd.EXIT_REGRESSION
    assert "merge base list unavailable" in err
    assert "zzz_new.py: [r] m" in err
    assert brd.NEW_MARKER not in err


@needs_git
def test_a_regression_with_no_diffable_entry_prints_no_new_header(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Negative: when the lister cannot tell old from new, it claims nothing."""
    repo = _regressed_repo(tmp_path, existing=3)
    same = ["a.py: x", "b.py: x"]

    code = _run(repo, lambda _root, _changed: list(same))

    err = capsys.readouterr().err
    assert code == brd.EXIT_REGRESSION
    assert "new since the merge base" not in err
    assert brd.NEW_MARKER not in err
    assert "a.py: x" in err


# ---------------------------------------------------------------------------
# taste: the whole path with the real linter
# ---------------------------------------------------------------------------


def _oversized(marker: str) -> str:
    return f"# {marker}\n" + "".join(f"x{index} = {index}\n" for index in range(600))


@needs_git
def test_taste_names_the_added_file_first_among_many_touched_existing_offenders(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The reported shape: the branch edits 45 failing files and adds one more.

    Every edited file is in the touched set, so ordering by touched files
    leaves the added file at index 45, past the 40-line cap. The added file
    sorts last by name so scan order cannot rescue it either.
    """
    repo = tmp_path / "repo"
    repo.mkdir()
    init_repo(repo)
    linter = repo / _LINTER_RELATIVE
    linter.parent.mkdir(parents=True)
    shutil.copy(Path(__file__).resolve().parents[2] / _LINTER_RELATIVE, linter)
    marker = repo / "scripts" / "ci" / "taste_count_ratchet.py"
    marker.parent.mkdir(parents=True)
    marker.write_text("# bootstrap marker for base_derived_ratchet\n", encoding="utf-8")
    commit_all(repo, "ratchet lands")
    git(repo, "tag", "ratchet-landed")
    for index in range(45):
        (repo / f"old{index:02d}.py").write_text(_oversized("base"), encoding="utf-8")
    commit_all(repo, "base")
    git(repo, "checkout", "-qb", "feat")
    for index in range(45):
        (repo / f"old{index:02d}.py").write_text(_oversized("feat") + "y = 1\n", encoding="utf-8")
    (repo / "zzz_added.py").write_text(_oversized("added"), encoding="utf-8")
    commit_all(repo, "feat")

    code = taste_count_ratchet.main(["--repo-root", str(repo), "--base-ref", "main"])

    err = capsys.readouterr().err
    printed = [line.strip() for line in err.splitlines() if line.startswith("  ")]
    assert code == taste_count_ratchet.EXIT_REGRESSION
    assert "1 new since the merge base" in err
    assert printed[1].startswith("NEW zzz_added.py: [file-size]")
    assert sum(1 for line in printed if line.startswith("NEW ")) == 1
