"""A conflicted path must be counted once, not once per merge stage (#4746).

``git ls-files`` prints one line per index entry, and an unmerged path holds
one entry per merge stage. All six ratchets under ``scripts/ci`` enumerate
through ``count_ratchet.tracked_files``, so mid-merge each was handed the same
path two or three times. Five of them then counted its violations that many
times. The memory-index ratchet did not: its ``_tracked_relative_paths``
builds a set, so the repeats collapsed before anything counted them. The
reported symptom was ``585 violations > baseline 583 (+2)`` on a tree whose
only conflicted file was byte-identical to ``origin/main``.

Fixing the shared enumeration still covers the immune consumer, because it
reads the index like the rest and so carries the mid-merge note. That note is
a reporting concern, not a counting one.

Git is the boundary under test here, so it is not mocked. The end-to-end case
also drives the real taste linter, because the defect lives in the seam between
the enumeration and the scan and a fake counter cannot show it.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from scripts.ci import cli_exit_contract_ratchet, count_ratchet, taste_count_ratchet
from tests.ci.count_ratchet_git_harness import commit_all as _commit_all
from tests.ci.count_ratchet_git_harness import git as _git
from tests.ci.count_ratchet_git_harness import init_repo as _init_repo

needs_git = pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")

_LINTER_RELATIVE = Path(".claude/skills/taste-lints/scripts/taste_lints.py")


# ---------------------------------------------------------------------------
# deduplicate_index_entries: the pure half, no git required
# ---------------------------------------------------------------------------


def test_a_clean_enumeration_is_returned_unchanged():
    """The no-op case. Outside a merge this fix must change nothing at all."""
    entries = ["b.py", "a.py", "nested/c.py"]

    unique, unmerged = count_ratchet.deduplicate_index_entries(entries)

    assert unique == entries
    assert unmerged == []


def test_a_three_stage_conflict_collapses_to_one_path():
    """The reported shape: content-versus-content, stages 1, 2 and 3."""
    entries = ["a.py", "big.py", "big.py", "big.py", "z.py"]

    unique, unmerged = count_ratchet.deduplicate_index_entries(entries)

    assert unique == ["a.py", "big.py", "z.py"]
    assert unmerged == ["big.py"]


def test_a_two_stage_conflict_collapses_too():
    """Add/add and delete/modify carry two stages, not three.

    The inflation is therefore not a fixed multiple, which is why the fix
    deduplicates instead of dividing the count by three.
    """
    unique, unmerged = count_ratchet.deduplicate_index_entries(["a.py", "a.py", "b.py"])

    assert unique == ["a.py", "b.py"]
    assert unmerged == ["a.py"]


def test_an_empty_enumeration_reports_nothing():
    """An empty index is not a conflict and must not read as one."""
    assert count_ratchet.deduplicate_index_entries([]) == ([], [])


def test_first_occurrence_wins_and_the_rest_of_the_order_survives():
    """Order is load-bearing: ``run`` caps the printed violation list at 40.

    A reordering here would silently change which violations a contributor
    sees on a regression, so the surviving order must be the order git printed.
    """
    entries = ["z.py", "m.py", "z.py", "a.py", "m.py", "z.py"]

    unique, unmerged = count_ratchet.deduplicate_index_entries(entries)

    assert unique == ["z.py", "m.py", "a.py"]
    assert unmerged == ["z.py", "m.py"]


def test_each_conflicted_path_is_reported_once_however_many_stages_it_has():
    """Three stages must not report the same path three times in the note."""
    _, unmerged = count_ratchet.deduplicate_index_entries(["a.py"] * 3 + ["b.py"] * 3)

    assert unmerged == ["a.py", "b.py"]


# ---------------------------------------------------------------------------
# The mid-merge note
# ---------------------------------------------------------------------------


def test_the_note_names_the_conflicted_path_and_the_working_tree_caveat():
    """The count is right now; the reader still has to know the tree is mid-merge.

    Conflict markers left on disk add lines, so a file can cross a size
    threshold on their own, and the issue records the detour a bare number cost.
    """
    note = count_ratchet._unmerged_note(["tests/build_scripts/test_x.py"])

    assert "1 path(s) unmerged in the index" in note
    assert "tests/build_scripts/test_x.py" in note
    assert "measures the working tree" in note
    assert note.endswith("\n")


def test_a_large_conflict_is_summarised_rather_than_listed():
    """Two hundred paths above a 40-line violation cap buries the payload."""
    paths = [f"f{index}.py" for index in range(9)]

    note = count_ratchet._unmerged_note(paths)

    assert "9 path(s) unmerged" in note
    assert "f0.py" in note
    assert "f4.py" in note
    assert "f5.py" not in note
    assert f"and {9 - count_ratchet.MAX_NAMED_UNMERGED} more" in note


# ---------------------------------------------------------------------------
# tracked_files, against real git
# ---------------------------------------------------------------------------


def _conflicted_repo(repo: Path, *, same_base: bool = True) -> None:
    """A repository stopped mid-merge with ``a.txt`` unmerged.

    ``same_base=False`` builds an add/add conflict, which git records with two
    stages instead of three.
    """
    _init_repo(repo)
    (repo / "keep.txt").write_text("keep\n", encoding="utf-8")
    if same_base:
        (repo / "a.txt").write_text("base\n", encoding="utf-8")
    _commit_all(repo, "base")

    _git(repo, "checkout", "-q", "-b", "feat")
    (repo / "a.txt").write_text("feat\n", encoding="utf-8")
    _commit_all(repo, "feat")

    _git(repo, "checkout", "-q", "main")
    (repo / "a.txt").write_text("main\n", encoding="utf-8")
    _commit_all(repo, "main")

    merged = _git(repo, "merge", "feat")
    assert merged.returncode != 0, "the fixture must stop in a conflicted state"


@needs_git
def test_git_repeats_an_unmerged_path_once_per_stage(tmp_path):
    """Pin the git behavior itself, so the fix is not aimed at a guess.

    Without this, a git release that stopped repeating unmerged entries would
    leave the deduplication passing its own tests while guarding nothing.
    """
    repo = tmp_path / "repo"
    repo.mkdir()
    _conflicted_repo(repo)

    listed = _git(repo, "ls-files", "-z").stdout.split("\0")

    assert [path for path in listed if path].count("a.txt") == 3


@needs_git
def test_tracked_files_lists_a_conflicted_path_once(tmp_path, capsys):
    """The fix at the seam every ratchet reads through."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _conflicted_repo(repo)

    files = count_ratchet.tracked_files(repo, ("*",))

    assert files is not None
    assert files.count("a.txt") == 1
    assert "keep.txt" in files
    assert "unmerged in the index" in capsys.readouterr().err


@needs_git
def test_tracked_files_lists_a_two_stage_conflict_once(tmp_path, capsys):
    """An add/add conflict has no stage 1 and must collapse the same way."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _conflicted_repo(repo, same_base=False)

    files = count_ratchet.tracked_files(repo, ("*",))

    assert files is not None
    assert files.count("a.txt") == 1
    assert "unmerged in the index" in capsys.readouterr().err


@needs_git
def test_a_clean_tree_lists_every_path_once_and_says_nothing(tmp_path, capsys):
    """Negative control for the note: no merge, no message.

    Without this the note could fire on every run and the assertions above
    would still pass.
    """
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)
    (repo / "a.txt").write_text("a\n", encoding="utf-8")
    (repo / "b.txt").write_text("b\n", encoding="utf-8")
    _commit_all(repo, "clean")

    files = count_ratchet.tracked_files(repo, ("*",))

    assert sorted(files or []) == ["a.txt", "b.txt"]
    assert capsys.readouterr().err == ""


@needs_git
def test_a_resolved_merge_lists_every_path_once_and_says_nothing(tmp_path, capsys):
    """Staging the resolution is what cleared the symptom in the report.

    The count must already match before that ``git add``, and the note must
    stop once the index is merged.
    """
    repo = tmp_path / "repo"
    repo.mkdir()
    _conflicted_repo(repo)
    (repo / "a.txt").write_text("resolved\n", encoding="utf-8")
    _git(repo, "add", "a.txt")

    files = count_ratchet.tracked_files(repo, ("*",))

    assert sorted(files or []) == ["a.txt", "keep.txt"]
    assert capsys.readouterr().err == ""


# ---------------------------------------------------------------------------
# End to end: the reported ratchet, the real linter (#4746)
# ---------------------------------------------------------------------------


def _install_linter(repo: Path) -> None:
    """Copy the taste linter into ``repo`` at the path the ratchet expects.

    ``taste_count_ratchet`` runs the linter as ``cwd=repo_root`` plus a
    repo-relative path, so a scratch repository needs its own copy. The linter
    is a single stdlib-only file, so copying it introduces no import graph.
    """
    source = Path(__file__).resolve().parents[2] / _LINTER_RELATIVE
    assert source.is_file(), f"the taste linter moved: {source}"
    destination = repo / _LINTER_RELATIVE
    destination.parent.mkdir(parents=True)
    shutil.copy(source, destination)


def _oversized(marker: str) -> str:
    """A file over the 500-line ``file-size`` ceiling, differing by one line."""
    return f"# {marker}\n" + "".join(f"x{index} = {index}\n" for index in range(600))


def _taste_repo_stopped_mid_merge(tmp_path: Path) -> tuple[Path, str]:
    """A repo mid-merge on an oversized file, resolved on disk but not staged.

    Returns the repo and the exact bytes on disk, so a caller that stages the
    resolution can prove the two measurements saw identical content.
    """
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)
    _install_linter(repo)
    big = repo / "big.py"
    big.write_text(_oversized("base"), encoding="utf-8")
    _commit_all(repo, "base")

    _git(repo, "checkout", "-q", "-b", "feat")
    big.write_text(_oversized("feat"), encoding="utf-8")
    _commit_all(repo, "feat")

    _git(repo, "checkout", "-q", "main")
    big.write_text(_oversized("main"), encoding="utf-8")
    _commit_all(repo, "main")

    assert _git(repo, "merge", "feat").returncode != 0, "the fixture must stop conflicted"
    resolution = _oversized("main")
    big.write_text(resolution, encoding="utf-8")
    return repo, resolution


@needs_git
def test_a_conflicted_file_counts_the_same_as_the_tree_it_resolves_to(tmp_path):
    """The issue's reproduction, asserted end to end.

    Content is identical either side of the ``git add``, so any difference in
    the count comes from the index alone. Before the fix this measured 4
    against 2: one violation for the linter's own copy plus three for the
    conflicted file, the ``+2`` the issue reports.
    """
    repo, resolution = _taste_repo_stopped_mid_merge(tmp_path)

    mid_merge = taste_count_ratchet.current_count(repo)

    _git(repo, "add", "big.py")
    assert (repo / "big.py").read_text(encoding="utf-8") == resolution
    resolved = taste_count_ratchet.current_count(repo)

    assert mid_merge == resolved
    assert resolved is not None and resolved > 0, "the fixture must carry a violation"


@needs_git
def test_one_run_prints_the_mid_merge_note_once(tmp_path, capsys):
    """A regression reads the index twice; the caveat is still printed once.

    ``run`` calls the counter, then on a regression calls the lister to render
    the violations, and the lister enumerates again. Both reads see the same
    unmerged index, so both emitted the identical note and a contributor
    mid-merge read the same caveat twice for one run.

    Driven through ``main`` rather than the helpers, because the double
    emission only exists in the sequence ``run`` performs. The violations
    header is asserted so the lister is known to have run: without that this
    would pass just as well if the second read never happened at all.
    """
    repo, _ = _taste_repo_stopped_mid_merge(tmp_path)
    baseline = tmp_path / "baseline.txt"
    baseline.write_text("0\n", encoding="utf-8")

    rc = taste_count_ratchet.main(
        ["--repo-root", str(repo), "--baseline", str(baseline)]
    )

    err = capsys.readouterr().err
    assert rc == count_ratchet.EXIT_REGRESSION, "the fixture must trip the ratchet"
    assert "Current violations:" in err, "the lister did not run, so nothing re-read"
    assert err.count("unmerged in the index") == 1, (
        f"the mid-merge note was printed {err.count('unmerged in the index')} times"
    )


def _conflict(repo: Path, relative: str, body: str) -> None:
    """Leave ``relative`` unmerged in the index, resolved on disk."""
    path = repo / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"# base\n{body}", encoding="utf-8")


@needs_git
def test_two_counting_scopes_still_print_one_note(tmp_path, capsys):
    """The two-scope consumer announces once, naming paths from both scopes.

    ``cli_exit_contract_ratchet`` counts from two disjoint pathspecs,
    ``scripts/ci/*.py`` and ``tests/**/*.py``, so it has two counting reads
    rather than one. Leaving both announcing printed a separate note per scope
    for a single run, which is the duplicate output #4746 exists to remove at
    a different shape. Silencing only the second would be wrong the other way:
    a conflict confined to ``tests/`` would then announce nothing.

    Both scopes carry a conflict here, so a fix that suppresses the wrong read
    fails this on the path list rather than only on the count.
    """
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)
    _conflict(repo, "scripts/ci/a.py", "x = 1\n")
    _conflict(repo, "tests/test_b.py", "y = 1\n")
    _commit_all(repo, "base")

    _git(repo, "checkout", "-q", "-b", "feat")
    _conflict(repo, "scripts/ci/a.py", "x = 2\n")
    _conflict(repo, "tests/test_b.py", "y = 2\n")
    _commit_all(repo, "feat")

    _git(repo, "checkout", "-q", "main")
    _conflict(repo, "scripts/ci/a.py", "x = 3\n")
    _conflict(repo, "tests/test_b.py", "y = 3\n")
    _commit_all(repo, "main")

    assert _git(repo, "merge", "feat").returncode != 0, "the fixture must stop conflicted"
    unmerged = _git(repo, "ls-files", "-u").stdout
    assert "scripts/ci/a.py" in unmerged and "tests/test_b.py" in unmerged, (
        "the fixture must leave a conflict in BOTH counting scopes"
    )

    result = cli_exit_contract_ratchet.uncovered_scripts(repo)

    err = capsys.readouterr().err
    assert result is not None, "the enumeration must still succeed mid-merge"
    assert err.count("unmerged in the index") == 1, (
        f"one run printed the mid-merge note {err.count('unmerged in the index')} times"
    )
    assert "scripts/ci/a.py" in err, "the note dropped the script scope"
    assert "tests/test_b.py" in err, "the note dropped the test scope"
