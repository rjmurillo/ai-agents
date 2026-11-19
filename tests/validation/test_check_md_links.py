"""Tests for the relative markdown link and anchor checker.

Fixtures are built in ``tmp_path`` git repositories, so no markdown file with a
broken link is committed to this repository. Covers both finding kinds
(``missing-target``, ``missing-anchor``), the skips (fences, external, out of
scope), the baseline ratchet, and the exit-code contract of ``main``.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

import scripts.validation.check_md_links as check_md_links
from scripts.validation.md_anchors import anchors_in, heading_text, slugify

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC = "src/claude/skills/demo/references"
IDENTITY = ["-c", "user.name=Test", "-c", "user.email=test@example.com"]


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *IDENTITY, *args],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return result.stdout


def make_repo(tmp_path: Path, files: dict[str, str], *, commit: bool = False) -> Path:
    """Create a git repository holding ``files``, staged and optionally committed."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")
    for name, body in files.items():
        path = repo / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
    _git(repo, "add", "-A")
    if commit:
        _git(repo, "commit", "-q", "-m", "seed")
    return repo


def scan(repo: Path, **kwargs: object) -> list[check_md_links.Finding]:
    """Return the findings of a full-scope scan with an empty baseline."""
    kwargs.setdefault("baseline", set())
    findings, _examined, _fragments = check_md_links.find_broken_md_links(repo, **kwargs)  # type: ignore[arg-type]
    return findings


def kinds(findings: list[check_md_links.Finding]) -> list[tuple[str, str]]:
    return [(f.kind, f.target) for f in findings]


def test_missing_relative_target_is_a_finding(tmp_path: Path) -> None:
    repo = make_repo(tmp_path, {"docs/a.md": "See [b](b.md).\n"})

    findings = scan(repo)

    assert kinds(findings) == [("missing-target", "b.md")]
    assert findings[0].format() == "docs/a.md:1: missing-target: b.md"


def test_existing_target_and_directory_are_clean(tmp_path: Path) -> None:
    repo = make_repo(
        tmp_path,
        {
            "docs/a.md": "[b](b.md) [dir](sub/) [up](../README.md)\n",
            "docs/b.md": "x\n",
            "docs/sub/c.md": "x\n",
            "README.md": "x\n",
        },
    )

    assert scan(repo) == []


def test_cross_file_broken_anchor_is_a_finding(tmp_path: Path) -> None:
    repo = make_repo(
        tmp_path,
        {"docs/a.md": "[b](b.md#nope)\n", "docs/b.md": "# Real heading\n"},
    )

    assert kinds(scan(repo)) == [("missing-anchor", "b.md#nope")]


def test_valid_reference_style_link_is_clean(tmp_path: Path) -> None:
    repo = make_repo(
        tmp_path,
        {
            "docs/a.md": "See [the b doc][bee] and [bee].\n\n[bee]: b.md#top-section\n",
            "docs/b.md": "# Top section\n",
        },
    )

    assert scan(repo) == []


def test_broken_reference_style_link_is_a_finding(tmp_path: Path) -> None:
    repo = make_repo(tmp_path, {"docs/a.md": "See [x][Lbl].\n\n[lbl]: gone.md\n"})

    assert kinds(scan(repo)) == [("missing-target", "gone.md")]


def test_undefined_reference_label_is_not_a_link(tmp_path: Path) -> None:
    repo = make_repo(tmp_path, {"docs/a.md": "Text [not a link][nowhere] and [bare].\n"})

    assert scan(repo) == []


def test_valid_cross_file_anchors_including_duplicate_and_code_span(tmp_path: Path) -> None:
    target = "# X\n\n## X\n\n## Use `run_tests` now\n\n## Plain: Heading (v2)\n"
    source = (
        "[first](t.md#x) [second](t.md#x-1) [code](t.md#use-run_tests-now) "
        "[punct](t.md#plain-heading-v2)\n"
    )
    repo = make_repo(tmp_path, {"docs/s.md": source, "docs/t.md": target})

    assert scan(repo) == []


def test_third_duplicate_heading_is_x_2_and_x_3_is_missing(tmp_path: Path) -> None:
    target = "# X\n## X\n## X\n"
    repo = make_repo(
        tmp_path, {"docs/s.md": "[ok](t.md#x-2) [bad](t.md#x-3)\n", "docs/t.md": target}
    )

    assert kinds(scan(repo)) == [("missing-anchor", "t.md#x-3")]


def test_html_anchor_targets_are_valid(tmp_path: Path) -> None:
    target = '<a id="by-id"></a>\n<a name="by-name"></a>\n'
    repo = make_repo(
        tmp_path, {"docs/s.md": "[i](t.md#by-id) [n](t.md#by-name)\n", "docs/t.md": target}
    )

    assert scan(repo) == []


def test_staged_but_uncommitted_target_counts_as_present(tmp_path: Path) -> None:
    repo = make_repo(tmp_path, {"docs/a.md": "[b](b.md#sec)\n"}, commit=True)
    (repo / "docs/b.md").write_text("# Sec\n", encoding="utf-8")
    _git(repo, "add", "docs/b.md")

    assert scan(repo) == []


def test_untracked_target_is_missing(tmp_path: Path) -> None:
    repo = make_repo(tmp_path, {"docs/a.md": "[b](b.md)\n"}, commit=True)
    (repo / "docs/b.md").write_text("x\n", encoding="utf-8")

    assert kinds(scan(repo)) == [("missing-target", "b.md")]


def test_link_inside_a_fenced_block_is_ignored(tmp_path: Path) -> None:
    body = "```markdown\n[x](gone.md)\n```\n\n~~~\n[y](gone2.md#a)\n~~~\n"
    repo = make_repo(tmp_path, {"docs/a.md": body})

    assert scan(repo) == []


def test_link_inside_inline_code_is_ignored(tmp_path: Path) -> None:
    repo = make_repo(tmp_path, {"docs/a.md": "Write `[x](gone.md)` like that.\n"})

    assert scan(repo) == []


def test_heading_inside_a_fence_is_not_an_anchor(tmp_path: Path) -> None:
    target = "# Real\n\n```md\n# Fenced heading\n```\n"
    repo = make_repo(tmp_path, {"docs/s.md": "[f](t.md#fenced-heading)\n", "docs/t.md": target})

    assert kinds(scan(repo)) == [("missing-anchor", "t.md#fenced-heading")]


@pytest.mark.parametrize(
    "dest",
    [
        "https://example.com/x.md",
        "mailto:a@example.com",
        "ssh://host/x.md",
        "//host/x.md",
        "/abs/x.md",
        "#same-file",
        "",
    ],
)
def test_external_absolute_and_same_file_destinations_are_ignored(
    tmp_path: Path, dest: str
) -> None:
    repo = make_repo(tmp_path, {"docs/a.md": f"[x]({dest})\n"})

    assert scan(repo) == []


def test_adr_targets_are_left_to_the_adr_checker(tmp_path: Path) -> None:
    repo = make_repo(tmp_path, {"docs/a.md": "[adr](ADR-001-missing.md)\n"})

    assert scan(repo) == []


def test_out_of_scope_files_are_ignored(tmp_path: Path) -> None:
    repo = make_repo(
        tmp_path,
        {
            "notes/a.md": "[x](gone.md)\n",
            "src/copilot-cli/skills/demo/SKILL.md": "[x](gone.md)\n",
            "src/claude/skills/demo/scripts/readme.md": "[x](gone.md)\n",
            "docs/a.txt": "[x](gone.md)\n",
        },
    )

    findings, examined, _ = check_md_links.find_broken_md_links(repo, baseline=set())

    assert (findings, examined) == ([], 0)


def test_skill_md_and_references_are_in_scope(tmp_path: Path) -> None:
    repo = make_repo(
        tmp_path,
        {
            "src/claude/skills/demo/SKILL.md": "[x](gone.md)\n",
            f"{SRC}/guide.md": "[y](gone2.md)\n",
        },
    )

    assert {f.file for f in scan(repo)} == {
        "src/claude/skills/demo/SKILL.md",
        f"{SRC}/guide.md",
    }


def test_link_through_a_tracked_symlink_resolves(tmp_path: Path) -> None:
    repo = make_repo(
        tmp_path,
        {
            "docs/a.md": "[s](../.claude/skills/demo/SKILL.md#intro)\n",
            "src/claude/skills/demo/SKILL.md": "# Intro\n",
        },
    )
    (repo / ".claude/skills").mkdir(parents=True)
    try:
        os.symlink("../../src/claude/skills/demo", repo / ".claude/skills/demo")
    except OSError:
        pytest.skip("symlinks unavailable")
    _git(repo, "add", "-A")

    assert scan(repo) == []


def test_baseline_entry_suppresses_one_finding(tmp_path: Path) -> None:
    repo = make_repo(tmp_path, {"docs/a.md": "[b](b.md)\n[c](c.md)\n"})

    findings = scan(repo, baseline={"missing-target:docs/a.md:b.md"})

    assert kinds(findings) == [("missing-target", "c.md")]


def test_baseline_fragment_entry_is_written_with_percent_23(tmp_path: Path) -> None:
    repo = make_repo(tmp_path, {"docs/a.md": "[b](b.md#x)\n", "docs/b.md": "# Y\n"})

    assert scan(repo, baseline={"missing-anchor:docs/a.md:b.md%23x"}) == []


def test_stale_baseline_entry_fails_a_full_scan_only(tmp_path: Path) -> None:
    repo = make_repo(tmp_path, {"docs/a.md": "fine\n"})
    stale = {"missing-target:docs/a.md:gone.md"}

    full = scan(repo, baseline=stale)
    staged = scan(repo, baseline=stale, files=["docs/a.md"])

    assert [f.kind for f in full] == ["stale-allowance"]
    assert staged == []


def test_malformed_baseline_entry_is_a_config_error(tmp_path: Path) -> None:
    repo = make_repo(tmp_path, {"docs/a.md": "fine\n"})

    with pytest.raises(ValueError, match="not shaped"):
        scan(repo, baseline={"docs/a.md"})


def _write_baseline(repo: Path, entries: list[str]) -> None:
    path = repo / "scripts/validation/check_md_links_baseline.txt"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("# header\n" + "".join(f"{e}\n" for e in entries), encoding="utf-8")


def test_baseline_addition_not_at_base_ref_fails(tmp_path: Path) -> None:
    repo = make_repo(tmp_path, {"docs/a.md": "[b](b.md)\n[c](c.md)\n"})
    _write_baseline(repo, ["missing-target:docs/a.md:b.md"])
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "seed")
    _write_baseline(repo, ["missing-target:docs/a.md:b.md", "missing-target:docs/a.md:c.md"])

    added = check_md_links.main(["--repo-root", str(repo), "--base-ref", "HEAD"])
    unchanged = check_md_links.main(["--repo-root", str(repo), "--base-ref", "none"])

    assert added == 2
    assert unchanged == 0


def test_main_exit_codes_for_clean_findings_and_empty_scope(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = make_repo(tmp_path, {"docs/a.md": "[b](b.md)\n"})
    empty = tmp_path / "empty"
    empty.mkdir()
    _git(empty, "init", "-q")

    bad = check_md_links.main(["--repo-root", str(repo), "--base-ref", "none"])
    out = capsys.readouterr().out
    nothing = check_md_links.main(["--repo-root", str(empty), "--base-ref", "none"])

    assert bad == 1
    assert "docs/a.md:1: missing-target: b.md" in out
    assert "1 violation(s) across 1 markdown file(s); 0 fragment link(s) checked" in out
    assert nothing == 2


def test_summary_reports_the_fragment_denominator(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = make_repo(
        tmp_path, {"docs/a.md": "[x](b.md#one) [y](b.md#two)\n", "docs/b.md": "# One\n# Two\n"}
    )

    code = check_md_links.main(["--repo-root", str(repo), "--base-ref", "none"])

    assert code == 0
    assert "2 fragment link(s) checked" in capsys.readouterr().out


def test_staged_mode_checks_only_the_named_in_scope_files(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = make_repo(
        tmp_path,
        {"docs/a.md": "[x](gone.md)\n", "docs/b.md": "[y](gone2.md)\n", "n/c.md": "[z](g.md)\n"},
    )

    code = check_md_links.main(
        ["--repo-root", str(repo), "--base-ref", "none", "docs/b.md", "n/c.md"]
    )
    out = capsys.readouterr().out

    assert code == 1
    assert "docs/b.md:1" in out
    assert "docs/a.md" not in out
    assert "n/c.md" not in out


def test_validate_md_links_returns_a_bool(tmp_path: Path) -> None:
    repo = make_repo(tmp_path, {"docs/a.md": "[b](b.md)\n"})

    assert check_md_links.validate_md_links(repo, base_ref="none") is False


@pytest.mark.parametrize(
    ("heading", "slug"),
    [
        ("Plain heading", "plain-heading"),
        ("`code` and text", "code-and-text"),
        ("A [link](x.md) here", "a-link-here"),
        ("Image ![alt](a.png) gone", "image--gone"),
        ("Dots. And: punctuation!", "dots-and-punctuation"),
        ("snake_case and _emph_", "snake_case-and-emph"),
        ("Under_score `a_b`", "under_score-a_b"),
        ("Tabs\tand  spaces", "tabsand--spaces"),
        ("Ünïcode 日本語", "ünïcode-日本語"),
    ],
)
def test_slug_rule_matches_markdownlint_md051(heading: str, slug: str) -> None:
    assert slugify(heading_text(heading)) == slug


def test_anchors_in_handles_setext_headings_frontmatter_and_custom_ids() -> None:
    body = "---\ntitle: x\n---\n\nSetext Title\n------------\n\n## With id {#my-id}\n"

    anchors = anchors_in(body)

    assert {"setext-title", "my-id", "top"} <= anchors
    assert "title-x" not in anchors


def _markdownlint_binary() -> str | None:
    return shutil.which("markdownlint-cli2")


@pytest.mark.skipif(_markdownlint_binary() is None, reason="markdownlint-cli2 not installed")
def test_markdownlint_already_flags_click_here_and_same_file_anchor(tmp_path: Path) -> None:
    """MD059 and MD051 own these two cases, so this gate does not repeat them."""
    work = tmp_path / "lint"
    work.mkdir()
    shutil.copy(REPO_ROOT / ".markdownlint-cli2.yaml", work / ".markdownlint-cli2.yaml")
    (work / "doc.md").write_text(
        "# Title\n\nSee [click here](x.md) and [a](#nope).\n", encoding="utf-8"
    )

    result = subprocess.run(
        [str(_markdownlint_binary()), "doc.md"],
        cwd=work,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    output = result.stdout + result.stderr

    assert "MD059" in output
    assert "MD051" in output
