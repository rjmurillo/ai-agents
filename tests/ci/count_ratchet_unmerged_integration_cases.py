"""Count each conflicted path once across ratchet consumers."""

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


def _install_linter(repo: Path) -> None:
    """Copy the taste linter into ``repo`` at the path the ratchet expects.

    ``taste_count_ratchet`` runs the linter as ``cwd=repo_root`` plus a
    repo-relative path, so a scratch repository needs its bundled library too.
    The linter imports ``ai_review_common`` and, through the ADR-047
    bootstrap, ``hook_utilities.frontmatter_block`` from ``<root>/lib``.
    """
    source = Path(__file__).resolve().parents[2] / _LINTER_RELATIVE
    assert source.is_file(), f"the taste linter moved: {source}"
    destination = repo / _LINTER_RELATIVE
    destination.parent.mkdir(parents=True)
    shutil.copy(source, destination)
    for package in ("ai_review_common", "hook_utilities"):
        shutil.copytree(
            source.parents[3] / "lib" / package,
            destination.parents[3] / "lib" / package,
            ignore=shutil.ignore_patterns("__pycache__"),
        )


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
    marker = repo / "scripts" / "ci" / "taste_count_ratchet.py"
    marker.parent.mkdir(parents=True)
    marker.write_text("# bootstrap marker for base_derived_ratchet\n", encoding="utf-8")
    _commit_all(repo, "ratchet lands")
    _git(repo, "tag", "ratchet-landed")
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

    rc = taste_count_ratchet.main(["--repo-root", str(repo), "--base-ref", "ratchet-landed"])

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
