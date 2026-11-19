"""Regressions for the link-check review on PR #7455.

Each test failed on 18b2d99a5d before the parser and baseline-count fixes.
"""

from __future__ import annotations

from pathlib import Path

import pytest

import scripts.validation.check_md_links as check_md_links
from tests.validation.test_check_md_links import _git, kinds, make_repo, scan


def test_a_second_copy_of_a_baselined_link_fails_pre_pr(tmp_path: Path) -> None:
    repo = make_repo(
        tmp_path,
        {
            "docs/a.md": "[old](gone.md)\n",
            "scripts/validation/check_md_links_baseline.txt": "missing-target:docs/a.md:gone.md\n",
        },
        commit=True,
    )
    base = _git(repo, "rev-parse", "HEAD").strip()
    (repo / "docs/a.md").write_text("[old](gone.md)\n[again](gone.md)\n", encoding="utf-8")
    _git(repo, "add", "docs/a.md")

    assert check_md_links.main(["--repo-root", str(repo), "--base-ref", base]) == 1


def test_staged_mode_reports_a_second_baselined_copy(tmp_path: Path) -> None:
    repo = make_repo(tmp_path, {"docs/a.md": "[old](gone.md)\n[again](gone.md)\n"})

    findings = scan(repo, baseline={"missing-target:docs/a.md:gone.md"}, files=["docs/a.md"])

    assert kinds(findings) == [("missing-target", "gone.md")]


def test_a_fence_on_the_list_marker_line_does_not_hide_later_links(tmp_path: Path) -> None:
    body = "1. ```md\n   [example](gone.md)\n   ```\n\n[after](also-gone.md)\n"
    repo = make_repo(tmp_path, {"docs/a.md": body})

    assert kinds(scan(repo)) == [("missing-target", "also-gone.md")]


def test_a_fence_inside_a_list_is_not_a_link(tmp_path: Path) -> None:
    body = "1. Step\n\n    ```md\n    [example](gone.md)\n    ```\n\n[after](also-gone.md)\n"
    repo = make_repo(tmp_path, {"docs/a.md": body})

    assert kinds(scan(repo)) == [("missing-target", "also-gone.md")]


def test_a_fence_inside_a_blockquote_is_not_a_link(tmp_path: Path) -> None:
    body = "> ```md\n> [example](gone.md)\n> ```\n\n[after](also-gone.md)\n"
    repo = make_repo(tmp_path, {"docs/a.md": body})

    assert kinds(scan(repo)) == [("missing-target", "also-gone.md")]


def test_a_root_four_space_marker_does_not_hide_the_next_link(tmp_path: Path) -> None:
    repo = make_repo(tmp_path, {"docs/a.md": "    ```\n[x](gone.md)\n"})

    assert kinds(scan(repo)) == [("missing-target", "gone.md")]


def test_an_angle_bracket_name_with_a_space_resolves(tmp_path: Path) -> None:
    repo = make_repo(
        tmp_path,
        {"docs/a.md": "[x](<my file.md#sec>)\n", "docs/my file.md": "# Sec\n"},
    )

    assert scan(repo) == []


def test_a_code_formatted_shortcut_label_is_checked(tmp_path: Path) -> None:
    repo = make_repo(tmp_path, {"docs/a.md": "[`foo`]\n\n[`foo`]: gone.md\n"})

    assert kinds(scan(repo)) == [("missing-target", "gone.md")]


def test_an_example_link_inside_backticks_is_still_ignored(tmp_path: Path) -> None:
    repo = make_repo(tmp_path, {"docs/a.md": "Write `[x](gone.md)` like that.\n"})

    assert scan(repo) == []


def test_link_syntax_inside_a_heading_code_span_is_literal(tmp_path: Path) -> None:
    repo = make_repo(
        tmp_path,
        {
            "docs/s.md": "[h](t.md#use-xy) [p](t.md#pic-ab)\n",
            "docs/t.md": "## Use `[x](y)`\n\n## Pic `![a](b)`\n",
        },
    )

    assert scan(repo) == []


def test_an_anchor_example_inside_backticks_is_not_an_anchor(tmp_path: Path) -> None:
    repo = make_repo(
        tmp_path,
        {
            "docs/s.md": "[g](t.md#gone) [k](t.md#kept)\n",
            "docs/t.md": 'An example: `<a id="gone"></a>`\n<a id="kept"></a>\n',
        },
    )

    assert kinds(scan(repo)) == [("missing-anchor", "t.md#gone")]


def test_unstaged_deletion_of_a_tracked_target_uses_the_index(tmp_path: Path) -> None:
    repo = make_repo(
        tmp_path,
        {"docs/a.md": "[b](b.md#sec)\n", "docs/b.md": "# Sec\n"},
        commit=True,
    )
    (repo / "docs/b.md").unlink()

    assert check_md_links.main(["--repo-root", str(repo), "--base-ref", "none"]) == 0


def test_unstaged_deletion_still_reports_a_missing_anchor(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = make_repo(
        tmp_path,
        {"docs/a.md": "[b](b.md#sec)\n", "docs/b.md": "# Other\n"},
        commit=True,
    )
    (repo / "docs/b.md").unlink()

    assert check_md_links.main(["--repo-root", str(repo), "--base-ref", "none"]) == 1
    assert "missing-anchor: b.md#sec" in capsys.readouterr().out


def test_staged_rename_reports_the_untouched_inbound_link(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = make_repo(
        tmp_path,
        {"docs/a.md": "# A\n", "docs/c.md": "[a](a.md)\n[nope](missing.md)\n"},
        commit=True,
    )
    _git(repo, "mv", "docs/a.md", "docs/b.md")

    code = check_md_links.main(["--repo-root", str(repo), "--base-ref", "none", "docs/b.md"])
    out = capsys.readouterr().out

    assert code == 1
    assert "docs/c.md:1: missing-target: a.md" in out
    assert "missing.md" not in out


def test_staged_delete_reports_the_untouched_inbound_link(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = make_repo(
        tmp_path,
        {"docs/a.md": "# A\n", "docs/c.md": "[a](a.md)\n"},
        commit=True,
    )
    _git(repo, "rm", "docs/a.md")

    code = check_md_links.main(["--repo-root", str(repo), "--base-ref", "none", "docs/a.md"])
    out = capsys.readouterr().out

    assert code == 1
    assert "docs/c.md:1: missing-target: a.md" in out


def test_staged_heading_rename_reports_the_untouched_inbound_anchor(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = make_repo(
        tmp_path,
        {"docs/a.md": "# Old heading\n", "docs/c.md": "[a](a.md#old-heading)\n"},
        commit=True,
    )
    (repo / "docs/a.md").write_text("# New heading\n", encoding="utf-8")
    _git(repo, "add", "docs/a.md")

    code = check_md_links.main(["--repo-root", str(repo), "--base-ref", "none", "docs/a.md"])
    out = capsys.readouterr().out

    assert code == 1
    assert "docs/c.md:1: missing-anchor: a.md#old-heading" in out


def test_staged_rename_is_clean_when_the_inbound_link_is_updated(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = make_repo(
        tmp_path,
        {"docs/a.md": "# A\n", "docs/c.md": "[a](a.md)\n"},
        commit=True,
    )
    _git(repo, "mv", "docs/a.md", "docs/b.md")
    (repo / "docs/c.md").write_text("[b](b.md)\n", encoding="utf-8")
    _git(repo, "add", "docs/c.md")

    code = check_md_links.main(["--repo-root", str(repo), "--base-ref", "none", "docs/b.md"])
    out = capsys.readouterr().out

    assert code == 0
    assert "docs/c.md" not in out


def test_staged_rename_reports_an_angle_bracket_link_with_spaces(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = make_repo(
        tmp_path,
        {
            "docs/my file.md": "# A\n",
            "docs/c.md": "[a](<my file.md>)\n[nope](missing.md)\n",
        },
        commit=True,
    )
    _git(repo, "mv", "docs/my file.md", "docs/b.md")

    code = check_md_links.main(["--repo-root", str(repo), "--base-ref", "none", "docs/b.md"])
    out = capsys.readouterr().out

    assert code == 1
    assert "docs/c.md:1: missing-target: my file.md" in out
    assert "missing.md" not in out


def test_staged_rename_reports_the_index_link_when_the_worktree_is_fixed(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = make_repo(
        tmp_path,
        {"docs/a.md": "# A\n", "docs/c.md": "[a](a.md)\n"},
        commit=True,
    )
    _git(repo, "mv", "docs/a.md", "docs/b.md")
    (repo / "docs/c.md").write_text("[b](b.md)\n", encoding="utf-8")

    code = check_md_links.main(["--repo-root", str(repo), "--base-ref", "none", "docs/b.md"])
    out = capsys.readouterr().out

    assert code == 1
    assert "docs/c.md:1: missing-target: a.md" in out


def test_staged_delete_of_a_non_md_target_reports_the_inbound_link(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = make_repo(
        tmp_path,
        {"docs/pic.png": "x\n", "docs/b.md": "# B\n", "docs/c.md": "[p](pic.png)\n"},
        commit=True,
    )
    _git(repo, "rm", "docs/pic.png")
    (repo / "docs/b.md").write_text("# B\n\nedit\n", encoding="utf-8")
    _git(repo, "add", "docs/b.md")

    code = check_md_links.main(["--repo-root", str(repo), "--base-ref", "none", "docs/b.md"])
    out = capsys.readouterr().out

    assert code == 1
    assert "docs/c.md:1: missing-target: pic.png" in out


def test_committed_heading_change_reports_inbound_when_only_the_target_is_named(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = make_repo(
        tmp_path,
        {"docs/a.md": "# Old heading\n", "docs/c.md": "[a](a.md#old-heading)\n"},
        commit=True,
    )
    base = _git(repo, "rev-parse", "HEAD").strip()
    (repo / "docs/a.md").write_text("# New heading\n", encoding="utf-8")
    _git(repo, "add", "docs/a.md")
    _git(repo, "commit", "-q", "-m", "rename heading")

    code = check_md_links.main(["--repo-root", str(repo), "--base-ref", base, "docs/a.md"])
    out = capsys.readouterr().out

    assert code == 1
    assert "docs/c.md:1: missing-anchor: a.md#old-heading" in out


def test_paths_outside_scope_are_named_instead_of_a_silent_pass(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = make_repo(
        tmp_path,
        {"README.md": "[x](missing.md)\n", "notes/page.md": "[y](missing.md)\n"},
        commit=True,
    )

    code = check_md_links.main(
        ["--repo-root", str(repo), "--base-ref", "none", "README.md", "notes/page.md"]
    )
    captured = capsys.readouterr()

    assert code == 0
    assert "2 file(s) outside link-check scope: README.md, notes/page.md" in captured.err
    assert "0 markdown file" not in captured.out
    assert "violation" not in captured.out


def test_parentheses_in_a_filename_or_title_do_not_hide_the_link(tmp_path: Path) -> None:
    missing = make_repo(
        tmp_path,
        {"docs/a.md": '[x](gone(v2).md)\n[y](other.md "note (a)")\n'},
    )
    present_root = tmp_path / "ok"
    present_root.mkdir()
    present = make_repo(
        present_root,
        {"docs/a.md": "[x](<gone(v2).md>)\n", "docs/gone(v2).md": "# Ok\n"},
    )

    assert kinds(scan(missing)) == [
        ("missing-target", "gone(v2).md"),
        ("missing-target", "other.md"),
    ]
    assert scan(present) == []


def _skill_link_repo(tmp_path: Path) -> tuple[Path, Path]:
    """Return a repo whose index links ``.claude/skills/demo`` at the real skill."""
    repo = make_repo(
        tmp_path,
        {
            "docs/a.md": "[s](../.claude/skills/demo/SKILL.md#intro)\n",
            "src/claude/skills/demo/SKILL.md": "# Intro\n",
        },
    )
    link = repo / ".claude/skills/demo"
    link.parent.mkdir(parents=True)
    try:
        link.symlink_to("../../src/claude/skills/demo")
    except OSError:
        pytest.skip("symlinks unavailable")
    _git(repo, "add", ".claude/skills/demo")
    return repo, link


def test_a_deleted_worktree_symlink_still_resolves_from_the_index(tmp_path: Path) -> None:
    repo, link = _skill_link_repo(tmp_path)
    link.unlink()

    assert scan(repo) == []


def test_a_plain_file_checkout_of_a_symlink_still_resolves(tmp_path: Path) -> None:
    repo, link = _skill_link_repo(tmp_path)
    link.unlink()
    link.write_text("../../src/claude/skills/demo", encoding="utf-8")

    assert scan(repo) == []


def test_an_unstaged_symlink_retarget_does_not_hide_the_index_target(tmp_path: Path) -> None:
    repo, link = _skill_link_repo(tmp_path)
    link.unlink()
    try:
        link.symlink_to("../../src/claude/skills/missing")
    except OSError:
        pytest.skip("symlinks unavailable")

    assert scan(repo) == []
