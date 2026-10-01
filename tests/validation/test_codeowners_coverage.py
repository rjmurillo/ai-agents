"""Tests for scripts/validation/codeowners_coverage.py.

The matcher decides whether a manifest file is owned, so a wrong answer either
hides a gap or invents one. Each pattern shape this repository's CODEOWNERS uses
is pinned here, plus the shapes it refuses.
"""

from __future__ import annotations

import sys
from pathlib import Path

_VALIDATION_DIR = Path(__file__).resolve().parents[2] / "scripts" / "validation"
if str(_VALIDATION_DIR) not in sys.path:
    sys.path.insert(0, str(_VALIDATION_DIR))

import codeowners_coverage as cc
import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
OWNER = ("@o",)


def _owned(pattern: str, path: str) -> bool:
    return bool(cc.owners_of(path, [cc.Rule(pattern, OWNER, 1)]))


class TestPatternShapes:
    @pytest.mark.parametrize(
        ("pattern", "path"),
        [
            ("/scripts/validation/", "scripts/validation/a.py"),
            ("/scripts/validation/", "scripts/validation/deep/b.py"),
            ("/scripts/validation", "scripts/validation/a.py"),
            ("/lefthook.yml", "lefthook.yml"),
            ("/.github/CODEOWNERS", ".github/CODEOWNERS"),
            ("*.py", "a.py"),
            ("*.py", "x/y/z.py"),
            ("docs/", "docs/a.md"),
            ("docs/", "x/docs/a.md"),
            ("scripts/*.py", "scripts/a.py"),
            ("/scripts/**", "scripts/a/b.py"),
            ("**/foo.py", "foo.py"),
            ("**/foo.py", "a/b/foo.py"),
            ("a/**/b.py", "a/b.py"),
            ("a/**/b.py", "a/x/y/b.py"),
            ("/a/?.py", "a/x.py"),
            ("/", "anything.txt"),
        ],
    )
    def test_matches(self, pattern: str, path: str) -> None:
        assert _owned(pattern, path)

    @pytest.mark.parametrize(
        ("pattern", "path"),
        [
            ("/scripts/validation/", "scripts/validationx/a.py"),
            ("/scripts/validation/", "scripts/other/a.py"),
            ("/scripts/validation/", "x/scripts/validation/a.py"),
            ("/lefthook.yml", "sub/lefthook.yml"),
            ("/lefthook.yml", "lefthook.yml.bak"),
            ("*.py", "a.pyc"),
            ("scripts/*.py", "scripts/a/b.py"),
            ("scripts/*.py", "x/scripts/a.py"),
            ("/a/?.py", "a/xy.py"),
            ("/a/?.py", "a/x/.py"),
            ("a/**/b.py", "a/b.pyc"),
            ("/scripts/**", "scriptsx/a.py"),
        ],
    )
    def test_does_not_match(self, pattern: str, path: str) -> None:
        assert not _owned(pattern, path)

    def test_a_slash_in_the_middle_anchors_the_pattern(self) -> None:
        assert _owned("scripts/ci/x.py", "scripts/ci/x.py")
        assert not _owned("scripts/ci/x.py", "sub/scripts/ci/x.py")

    def test_a_name_without_a_slash_matches_at_any_depth(self) -> None:
        assert _owned("Makefile", "a/b/Makefile")


class TestParsing:
    def test_comments_blanks_and_trailing_comments_are_ignored(self) -> None:
        text = "# header\n\n/a/  @x  # why\n   \n/b.py @y @z\n"

        rules = cc.parse(text)

        assert [(r.pattern, r.owners, r.line) for r in rules] == [
            ("/a/", ("@x",), 3),
            ("/b.py", ("@y", "@z"), 5),
        ]

    def test_the_last_matching_rule_wins(self) -> None:
        rules = cc.parse("/a/ @first\n/a/b.py @second\n")

        assert cc.owners_of("a/b.py", rules) == ("@second",)
        assert cc.owners_of("a/c.py", rules) == ("@first",)

    def test_a_rule_that_names_no_owner_releases_the_file(self) -> None:
        rules = cc.parse("/a/ @first\n/a/b.py\n")

        assert cc.owners_of("a/b.py", rules) == ()

    @pytest.mark.parametrize("pattern", ["!negated", "[abc].py", r"a\ b.py"])
    def test_syntax_this_matcher_does_not_implement_is_refused(self, pattern: str) -> None:
        with pytest.raises(cc.UnsupportedPatternError, match="line 2"):
            cc.parse(f"/ok/ @x\n{pattern} @y\n")

    def test_the_repository_codeowners_parses(self) -> None:
        rules = cc.load(REPO_ROOT / ".github" / "CODEOWNERS")

        assert rules
        assert all(rule.owners for rule in rules)


class TestCoverage:
    def test_an_owned_path_is_neither_uncovered_nor_excluded(self) -> None:
        rules = cc.parse("/a/ @x\n")

        assert cc.coverage(["a/b.py"], rules, {}) == ([], [])

    def test_an_unowned_path_is_uncovered_and_sorted_once(self) -> None:
        rules = cc.parse("/a/ @x\n")

        uncovered, excluded = cc.coverage(["z.py", "b.py", "z.py"], rules, {})

        assert uncovered == ["b.py", "z.py"]
        assert excluded == []

    def test_a_named_exclusion_with_a_reason_is_excluded_not_uncovered(self) -> None:
        rules = cc.parse("/a/ @x\n")

        uncovered, excluded = cc.coverage(["b.py"], rules, {"b.py": "generated"})

        assert uncovered == []
        assert excluded == ["b.py"]

    def test_an_exclusion_without_a_reason_does_not_exclude(self) -> None:
        rules = cc.parse("/a/ @x\n")

        uncovered, _ = cc.coverage(["b.py"], rules, {"b.py": ""})

        assert uncovered == ["b.py"]

    def test_an_exclusion_names_one_path_exactly(self) -> None:
        rules = cc.parse("/a/ @x\n")

        uncovered, _ = cc.coverage(["b.py", "b.pyc"], rules, {"b.py": "why"})

        assert uncovered == ["b.pyc"]


class TestTheRepositoryCodeowners:
    """ADR-101 names paths a hand-written list kept missing; check they read as unowned."""

    @pytest.fixture(scope="class")
    def rules(self) -> list[cc.Rule]:
        return cc.load(REPO_ROOT / ".github" / "CODEOWNERS")

    @pytest.mark.parametrize(
        "path",
        [
            ".github/workflows/pytest.yml",
            ".github/actions/setup-code-env/action.yml",
            "scripts/validation/git_hook_policy.py",
            "lefthook.yml",
            ".github/CODEOWNERS",
        ],
    )
    def test_the_enforcement_paths_owned_by_the_seed_list_are_owned(
        self, rules: list[cc.Rule], path: str
    ) -> None:
        assert cc.owners_of(path, rules)
