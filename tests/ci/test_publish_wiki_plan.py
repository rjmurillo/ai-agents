"""Tests for the page plan built by scripts/ci/publish_wiki.py (issue #7202).

Covers page mapping, sidebar order, the one-way banner, and every refusal a bad
docs/training tree must produce. See test_publish_wiki.py for link rewriting and
the exit codes of ``main``.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.ci import publish_wiki as pw
from tests.ci.publish_wiki_helpers import BLOB, README, REPO_URL, make_repo, write


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    return make_repo(tmp_path / "repo")


def plan_for(repo: Path) -> pw.Plan:
    return pw.build_plan(repo / pw.SOURCE_DIR, repo, REPO_URL)


def test_plan_maps_readme_to_home_and_skips_template(repo: Path) -> None:
    assert sorted(plan_for(repo).files) == [
        "Home.md",
        "_Sidebar.md",
        "first-page.md",
        "second-page.md",
    ]


def test_home_carries_one_way_banner_and_source_footer(repo: Path) -> None:
    home = plan_for(repo).files["Home.md"]
    assert home.startswith("> **This wiki is a read-only mirror.**")
    assert "overwritten on the next publish" in home
    assert f"Source: [docs/training/README.md]({BLOB}/docs/training/README.md)" in home


def test_sidebar_follows_readme_order_not_alphabet(repo: Path) -> None:
    write(
        repo,
        "docs/training/README.md",
        "# T\n\n- [Z](second-page.md)\n\n- [A](first-page.md)\n",
    )
    sidebar = plan_for(repo).files["_Sidebar.md"]
    assert sidebar.index("(second-page)") < sidebar.index("(first-page)")
    assert "- [Second steps](second-page)" in sidebar
    assert sidebar.startswith("**[Feature training](Home)**")


def test_sidebar_lists_a_page_once_even_if_linked_twice(repo: Path) -> None:
    write(repo, "docs/training/README.md", README + "\nAgain [one](first-page.md).\n")
    assert plan_for(repo).files["_Sidebar.md"].count("(first-page)") == 1


def test_page_links_are_rewritten_in_output(repo: Path) -> None:
    first = plan_for(repo).files["first-page.md"]
    assert "[second](second-page#part)" in first
    assert "[home](Home)" in first


def test_page_not_in_readme_is_rejected(repo: Path) -> None:
    write(repo, "docs/training/orphan.md", "# Orphan\n")
    with pytest.raises(pw.SourceError, match="orphan.md"):
        plan_for(repo)


def test_front_matter_is_rejected(repo: Path) -> None:
    write(repo, "docs/training/first-page.md", "---\ntitle: x\n---\n# First\n")
    with pytest.raises(pw.SourceError, match="front matter"):
        plan_for(repo)


def test_subdirectory_is_rejected(repo: Path) -> None:
    (repo / "docs/training/sub").mkdir()
    with pytest.raises(pw.SourceError, match="flat"):
        plan_for(repo)


@pytest.mark.parametrize("name", ["Bad_Name.md", "UPPER.md", "two words.md", "-lead.md"])
def test_non_kebab_name_is_rejected(repo: Path, name: str) -> None:
    write(repo, f"docs/training/{name}", "# x\n")
    with pytest.raises(pw.SourceError, match="kebab-case"):
        plan_for(repo)


def test_non_markdown_file_is_rejected(repo: Path) -> None:
    write(repo, "docs/training/notes.txt", "x")
    with pytest.raises(pw.SourceError, match="only .md"):
        plan_for(repo)


def test_missing_readme_is_rejected(repo: Path) -> None:
    (repo / "docs/training/README.md").unlink()
    with pytest.raises(pw.SourceError, match="README.md is missing"):
        plan_for(repo)


def test_plan_is_deterministic(repo: Path) -> None:
    assert plan_for(repo) == plan_for(repo)


def test_real_training_tree_plans_cleanly() -> None:
    """Every sibling PR runs this: a page the index misses, or a bad link, fails here."""
    root = Path(__file__).resolve().parents[2]
    plan = pw.build_plan(root / pw.SOURCE_DIR, root, REPO_URL)
    assert "Home.md" in plan.files
    assert "_template.md" not in plan.files
