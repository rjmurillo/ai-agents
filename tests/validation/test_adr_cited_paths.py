"""Tests for scripts/validation/adr_cited_paths.py (issue #5194).

Coverage:

- extract_cited_paths: pos (a span in Decision and in Implementation Notes is
  read, a `###` subsection stays inside its section), neg (Context, Rationale,
  and References are not read; a span holding a command, a glob, a placeholder,
  or a URL cites nothing), edge (a path in a fenced block is an illustration;
  a `:line` or `#anchor` locator is stripped; `./` is stripped; a `..` segment
  is refused; a repeated path is reported once, in first-seen order).
- tracked_paths / missing_paths: pos (a tracked file is present), neg (a
  deleted file is missing), edge (an untracked file counts as missing, the
  filesystem answers outside a git checkout, and a subdirectory of another
  checkout is not mistaken for its own top level).
"""

from __future__ import annotations

import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
_VALIDATION_DIR = REPO_ROOT / "scripts" / "validation"

if str(_VALIDATION_DIR) not in sys.path:
    sys.path.insert(0, str(_VALIDATION_DIR))

from adr_cited_paths import (
    extract_cited_paths,
    missing_paths,
    tracked_paths,
)

from scripts.validation import tracked_paths as tracked_paths_mod


def _body(decision: str = "", notes: str = "", other: str = "") -> str:
    return (
        "# ADR-999: Thing\n\n"
        f"## Context\n\n{other}\n\n"
        f"## Decision\n\n{decision}\n\n"
        f"## Rationale\n\n{other}\n\n"
        f"## Implementation Notes\n\n{notes}\n\n"
        f"## References\n\n{other}\n"
    )


def _git(root: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-C", str(root), *args],
        check=True,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
    )


def _init_repo(root: Path) -> None:
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "t@example.com")
    _git(root, "config", "user.name", "t")


# --- extract_cited_paths ----------------------------------------------------


def test_reads_a_span_from_decision():
    body = _body(decision="Run `scripts/tool.py` first.")

    assert extract_cited_paths(body) == ["scripts/tool.py"]


def test_reads_a_span_from_implementation_notes():
    body = _body(notes="Lives in `src/pkg/mod.py`.")

    assert extract_cited_paths(body) == ["src/pkg/mod.py"]


def test_a_subsection_stays_inside_its_decision_section():
    body = _body(decision="### Detail\n\nSee `scripts/deep.py`.")

    assert extract_cited_paths(body) == ["scripts/deep.py"]


def test_other_sections_are_not_read():
    body = _body(other="History: `scripts/old.py` once existed.")

    assert extract_cited_paths(body) == []


def test_a_body_with_no_binding_section_cites_nothing():
    assert extract_cited_paths("# ADR-1: X\n\n## Context\n\n`a/b.py`\n") == []


def test_a_fenced_block_is_an_illustration():
    decision = textwrap.dedent(
        """\
        Shape:

        ```yaml
        path: `scripts/in_fence.py`
        ```

        ~~~text
        `scripts/in_tilde.py`
        ~~~
        """
    )

    assert extract_cited_paths(_body(decision=decision)) == []


def test_a_heading_inside_a_fence_does_not_end_the_section():
    decision = "```\n## Notes\n```\n\nAfter the fence: `scripts/after.py`."

    assert extract_cited_paths(_body(decision=decision)) == ["scripts/after.py"]


@pytest.mark.parametrize(
    "span",
    [
        "python3 scripts/x.py --flag",
        "scripts/*.py",
        "scripts/<name>.py",
        "scripts/{a,b}.py",
        "scripts/$VAR.py",
        "https://example.com/a/b.html",
        "scripts/noext",
        "scripts/dir/",
        "bare.py",
        "AGENTS.md/CLAUDE.md",
        "../../CONTRIBUTING.md",
        "a/../b.py",
        "scripts/x.1py",
    ],
)
def test_a_span_that_is_not_one_path_cites_nothing(span):
    assert extract_cited_paths(_body(decision=f"Use `{span}` here.")) == []


@pytest.mark.parametrize("locator", [":12", ":12-30", "#install"])
def test_a_line_or_anchor_locator_is_stripped(locator):
    # The locator is joined at run time so this file holds no literal
    # `path:line` citation for the citation-freshness gate to anchor on.
    assert extract_cited_paths(_body(decision=f"See `scripts/x.py{locator}`.")) == ["scripts/x.py"]


@pytest.mark.parametrize(
    ("span", "expected"),
    [
        ("./scripts/x.py", "scripts/x.py"),
        (".claude/rules/x.md", ".claude/rules/x.md"),
    ],
)
def test_a_dot_slash_prefix_is_stripped_and_a_dot_directory_kept(span, expected):
    assert extract_cited_paths(_body(decision=f"See `{span}`.")) == [expected]


def test_a_repeated_path_is_reported_once_in_first_seen_order():
    decision = "`b/two.py` then `a/one.py` then `b/two.py` again."

    assert extract_cited_paths(_body(decision=decision, notes="`a/one.py`")) == [
        "b/two.py",
        "a/one.py",
    ]


def test_html_comments_hide_a_citation():
    decision = "<!--\n`scripts/hidden.py`\n-->\n\nVisible: `scripts/shown.py`."

    assert extract_cited_paths(_body(decision=decision)) == ["scripts/shown.py"]


# --- tracked_paths / missing_paths ------------------------------------------


def test_a_tracked_file_is_present_and_a_deleted_one_is_missing(tmp_path):
    _init_repo(tmp_path)
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "live.py").write_text("x", encoding="utf-8")
    _git(tmp_path, "add", "scripts/live.py")

    tracked = tracked_paths(tmp_path)

    assert tracked == frozenset({"scripts/live.py"})
    assert missing_paths(["scripts/live.py", "scripts/gone.py"], tmp_path, tracked) == [
        "scripts/gone.py"
    ]


def test_an_untracked_file_counts_as_missing_in_a_git_checkout(tmp_path):
    _init_repo(tmp_path)
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "residue.py").write_text("x", encoding="utf-8")

    tracked = tracked_paths(tmp_path)

    assert tracked == frozenset()
    assert missing_paths(["scripts/residue.py"], tmp_path, tracked) == ["scripts/residue.py"]


@pytest.mark.skipif(sys.platform == "win32", reason="symlinks need Developer Mode on Windows")
def test_a_path_through_a_tracked_symlink_exists_only_when_its_target_is_tracked(tmp_path):
    # ADR-119: git tracks `.claude/skills/<name>` as one link entry, so the
    # files reached through it are not in `ls-files` by that spelling.
    _init_repo(tmp_path)
    (tmp_path / "src" / "skills" / "alpha").mkdir(parents=True)
    (tmp_path / "src" / "skills" / "alpha" / "SKILL.md").write_text("x", encoding="utf-8")
    (tmp_path / ".claude" / "skills").mkdir(parents=True)
    (tmp_path / ".claude" / "skills" / "alpha").symlink_to("../../src/skills/alpha")
    _git(tmp_path, "add", "src/skills/alpha/SKILL.md", ".claude/skills/alpha")
    tracked_paths_mod.clear_tracked_path_cache()

    tracked = tracked_paths(tmp_path)

    assert ".claude/skills/alpha/SKILL.md" not in tracked
    assert missing_paths(
        [".claude/skills/alpha/SKILL.md", ".claude/skills/alpha/gone.md"], tmp_path, tracked
    ) == [".claude/skills/alpha/gone.md"]


def test_the_filesystem_answers_outside_a_git_checkout(tmp_path):
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "live.py").write_text("x", encoding="utf-8")

    tracked = tracked_paths(tmp_path)

    assert tracked is None
    assert missing_paths(["scripts/live.py", "scripts/gone.py"], tmp_path, tracked) == [
        "scripts/gone.py"
    ]


def test_a_directory_is_not_a_file_in_the_filesystem_fallback(tmp_path):
    (tmp_path / "scripts" / "dir.py").mkdir(parents=True)

    assert missing_paths(["scripts/dir.py"], tmp_path, None) == ["scripts/dir.py"]


def test_a_subdirectory_of_another_checkout_is_not_its_own_top_level(tmp_path):
    _init_repo(tmp_path)
    nested = tmp_path / "nested"
    (nested / "scripts").mkdir(parents=True)
    (nested / "scripts" / "live.py").write_text("x", encoding="utf-8")

    tracked = tracked_paths(nested)

    assert tracked is None
    assert missing_paths(["scripts/live.py"], nested, tracked) == []
