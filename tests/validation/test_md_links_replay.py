"""Regression checks for historical trees and inbound link changes."""

from pathlib import Path

from scripts.validation import check_md_links as links
from tests.validation.test_check_md_links import _git, make_repo


def test_tree_reports_baselined_debt(tmp_path: Path, capsys) -> None:
    repo = make_repo(tmp_path, {"docs/a.md": "[gone](gone.md)\n"}, commit=True)
    baseline = repo / links.DEFAULT_BASELINE
    baseline.parent.mkdir(parents=True)
    baseline.write_text("missing-target:docs/a.md:gone.md\n", encoding="utf-8")
    assert links.main(["--repo-root", str(repo), "--tree"]) == 1
    assert "missing-target: gone.md" in capsys.readouterr().out


def test_heading_rename_flags_unchanged_inbound_link(tmp_path: Path, capsys) -> None:
    repo = make_repo(
        tmp_path,
        {
            "docs/a.md": "[topic](b.md#old-heading)\n",
            "docs/b.md": "# Old heading\n",
        },
        commit=True,
    )
    base = _git(repo, "rev-parse", "HEAD").strip()
    (repo / "docs/b.md").write_text("# New heading\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "rename")
    assert links.main(["--repo-root", str(repo), "--base-ref", base]) == 1
    assert "docs/a.md:1: missing-anchor" in capsys.readouterr().out


def test_new_copy_of_existing_debt_is_not_suppressed(tmp_path: Path, capsys) -> None:
    repo = make_repo(tmp_path, {"docs/a.md": "[gone](gone.md)\n"}, commit=True)
    base = _git(repo, "rev-parse", "HEAD").strip()
    (repo / "docs/a.md").write_text("[gone](gone.md)\n[duplicate](gone.md)\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "copy")
    assert links.main(["--repo-root", str(repo), "--base-ref", base]) == 1
    assert "missing-target: gone.md" in capsys.readouterr().out


def test_inherited_debt_does_not_fail_a_changed_file_replay(tmp_path: Path) -> None:
    repo = make_repo(tmp_path, {"docs/a.md": "[gone](gone.md)\n"}, commit=True)
    base = _git(repo, "rev-parse", "HEAD").strip()
    (repo / "docs/a.md").write_text("# Notes\n[gone](gone.md)\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "heading")
    assert links.main(["--repo-root", str(repo), "--base-ref", base]) == 0
