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
