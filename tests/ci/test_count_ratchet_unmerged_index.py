"""A conflicted path must be counted once, not once per merge stage (#4746).

``git ls-files`` prints one line per index entry, and an unmerged path holds
one entry per merge stage. Every ratchet under ``scripts/ci`` enumerates
through ``count_ratchet.tracked_files``, so mid-merge each of them handed its
linter the same path two or three times and counted its violations that many
times. The reported symptom was ``585 violations > baseline 583 (+2)`` on a
tree whose only conflicted file was byte-identical to ``origin/main``.

Git is the boundary under test here, so it is not mocked. The end-to-end case
also drives the real taste linter, because the defect lives in the seam between
the enumeration and the scan and a fake counter cannot show it.
"""

from __future__ import annotations

import shutil
from collections.abc import Sequence
from pathlib import Path

import pytest

from scripts.ci import (
    cli_exit_contract_ratchet,
    count_ratchet,
    memory_index_count_ratchet,
    ruff_count_ratchet,
    subprocess_encoding_count_ratchet,
    taste_count_ratchet,
    type_ignore_count_ratchet,
)
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


@needs_git
def test_a_conflicted_file_counts_the_same_as_the_tree_it_resolves_to(tmp_path):
    """The issue's reproduction, asserted end to end.

    Content is identical either side of the ``git add``, so any difference in
    the count comes from the index alone. Before the fix this measured 4
    against 2: one violation for the linter's own copy plus three for the
    conflicted file, the ``+2`` the issue reports.
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

    assert _git(repo, "merge", "feat").returncode != 0
    # Resolve on disk only, leaving the index unmerged. The bytes below are the
    # bytes that get staged, so the two measurements see identical content.
    resolution = _oversized("main")
    big.write_text(resolution, encoding="utf-8")

    mid_merge = taste_count_ratchet.current_count(repo)

    _git(repo, "add", "big.py")
    assert big.read_text(encoding="utf-8") == resolution
    resolved = taste_count_ratchet.current_count(repo)

    assert mid_merge == resolved
    assert resolved is not None and resolved > 0, "the fixture must carry a violation"


# ---------------------------------------------------------------------------
# Wiring: the fix only helps a ratchet that reads through the fixed seam
# ---------------------------------------------------------------------------


class _EnumerationSpy:
    """Stands in for ``tracked_files`` and records that it was reached.

    Asserting that a module still holds the imported name proves only that the
    import survived: a consumer can stop calling it, keep the unused import,
    and pass. Driving the real counting entry point with this in place is what
    the repository's consumer-wiring rule asks for.
    """

    def __init__(self, result: list[str] | None) -> None:
        self.result = result
        self.calls = 0

    def __call__(self, repo_root: Path, globs: Sequence[str]) -> list[str] | None:
        self.calls += 1
        return self.result


def _stub_memory_tier_validator(monkeypatch) -> None:
    """Stub the external validator ``memory_index_count_ratchet`` shells out to.

    That module runs the memory-tier validator before it enumerates, and the
    validator is absent from a scratch root, so the module would bail before
    reaching the enumeration and the spy would prove nothing. This mocks at the
    process boundary only, leaving the enumeration on the path under test. The
    stub warning names a file that the empty enumeration will report untracked,
    which is what makes the control below land on zero.
    """
    monkeypatch.setattr(
        memory_index_count_ratchet,
        "_warning_lines",
        lambda _root: ["a.md: no index references this file"],
    )


_RATCHET_CONSUMERS = [
    (cli_exit_contract_ratchet, None),
    (memory_index_count_ratchet, _stub_memory_tier_validator),
    (ruff_count_ratchet, None),
    (subprocess_encoding_count_ratchet, None),
    (taste_count_ratchet, None),
    (type_ignore_count_ratchet, None),
]

_CONSUMER_IDS = [module.__name__.rsplit(".", 1)[-1] for module, _ in _RATCHET_CONSUMERS]


@pytest.mark.parametrize(("module", "prepare"), _RATCHET_CONSUMERS, ids=_CONSUMER_IDS)
def test_every_ratchet_counts_through_the_shared_enumeration(
    module, prepare, monkeypatch, tmp_path
):
    """A ratchet that rolls its own ``ls-files`` reopens #4746 for itself.

    The issue asked whether the siblings share the enumeration. They do, which
    is why one fix covers all six. This drives each consumer's real
    ``current_count`` and fails the moment one stops routing through the
    deduplicating helper.

    The unreadable-enumeration verdict is asserted alongside the call, because
    a consumer that reached the helper and then ignored its ``None`` would be
    wired and still wrong: each of these modules documents returning None
    rather than 0 as load-bearing, since a zero from a broken scan reads as a
    clean tree and ``--update`` would write it into the baseline.
    """
    if prepare is not None:
        prepare(monkeypatch)
    spy = _EnumerationSpy(None)
    monkeypatch.setattr(module, "tracked_files", spy)

    result = module.current_count(tmp_path)

    assert spy.calls >= 1, f"{module.__name__} did not reach the shared enumeration"
    assert result is None, f"{module.__name__} reported a count from an unreadable scan"


@pytest.mark.parametrize(("module", "prepare"), _RATCHET_CONSUMERS, ids=_CONSUMER_IDS)
def test_a_readable_enumeration_is_not_reported_as_a_failed_scan(
    module, prepare, monkeypatch, tmp_path
):
    """Control for the case above: the None must come from the enumeration.

    Same consumer, same input, differing only in the condition under test. A
    module that returned None for an unrelated reason fails here too, so the
    case above cannot pass for the wrong reason.
    """
    if prepare is not None:
        prepare(monkeypatch)
    spy = _EnumerationSpy([])
    monkeypatch.setattr(module, "tracked_files", spy)

    result = module.current_count(tmp_path)

    assert spy.calls >= 1, f"{module.__name__} did not reach the shared enumeration"
    assert result == 0, f"{module.__name__} did not count an empty tree as zero"
