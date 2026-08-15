"""Regression guard for .markdownlint-cli2.yaml invariants.

Issue #1837 (original): ``scripts/validation/pre_pr.py`` failed Markdown Linting
on a pristine ``main`` because the regenerated Copilot CLI skills under
``src/copilot-cli/skills/**`` carried 403 MD040/MD041/MD036 violations.  PR #331
added blanket exclusions for both skill trees as the fix.

Issue #4038: proposed removing the blanket exclusions after an apparent measurement
showed "0 violations."  PR #4065 acted on that measurement and deleted the exclusions.

That measurement was tautological: the linter ran WITH the exclusions still in
the config, so it scanned 0 files and found 0 violations, then concluded the
exclusions were stale.  A correct A/B measurement shows:

- Pre-#4065 config (blanket exclusions present): 0 files linted, 0 issues.
- Post-#4065 config (exclusions removed): 697 files linted, 823 issues.

"0 issues" came from "0 files".  The exclusions were working, not stale.

The correct fix (issue #4038's "Suggested next step"): scope only the two
dominant rules off for the skill trees via per-glob overrides:
- MD040 (fenced-code-language): 575 of 823 violations -- skill docs carry bare
  fences for illustrative snippets where a language tag would mislead.
- MD033 (no-inline-html): 132 of 823 violations -- skill docs use structured
  inline HTML (``<example>``, ``<step>``, XML tags) as semantic markers.

The remaining 58 violations across 35 files were fixed in place.

These tests guard:
1. The per-glob overrides for the skill trees are present and correctly configured.
2. Every glob in ``ignores`` matches at least one file on disk (no stale exclusions).
3. Every ``filter`` in ``overrides`` matches at least one file on disk.
4. Running the linter on the skill trees produces a nonzero file count.  This is
   the isolating negative control: with a blanket exclusion, the linter scans 0
   files and the test fails, exposing the tautological-measurement pattern
   described above.

Canonical source: ``.markdownlint-cli2.yaml`` (repo root).
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Any, cast

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = REPO_ROOT / ".markdownlint-cli2.yaml"

SKILL_TREES = [".claude/skills/**", "src/copilot-cli/skills/**"]
REQUIRED_SKILL_DISABLED_RULES = {"MD040": False, "MD033": False}


@pytest.fixture(scope="module")
def config() -> dict[str, object]:
    """Parsed .markdownlint-cli2.yaml from the repo root."""
    assert CONFIG_PATH.is_file(), f"missing config: {CONFIG_PATH}"
    return cast(dict[str, object], yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8")))


def test_config_parses_as_mapping(config: dict[str, object]) -> None:
    """The config file is a YAML mapping with the expected top-level keys."""
    assert isinstance(config, dict)
    assert "config" in config
    assert "ignores" in config


def test_skill_tree_overrides_present(config: dict[str, object]) -> None:
    """Both skill trees have per-glob overrides disabling MD040 and MD033.

    PR #4065 removed the blanket exclusions based on a tautological measurement.
    The replacement is per-glob overrides that disable only the two rules that
    accounted for 86% of the violations (MD040=575, MD033=132 of 823).
    The remaining 58 violations were fixed in place.
    """
    overrides = cast(list[dict[str, object]], config.get("overrides", []))
    assert isinstance(overrides, list) and overrides, (
        "config must have a non-empty 'overrides' list for skill tree rule scoping; "
        "removing it re-introduces 823 violations in 141 files (issue #1837)."
    )

    covered_trees: set[str] = set()
    for entry in overrides:
        filters = cast(list[str], entry.get("filter", []))
        rule_config = cast(dict[str, object], entry.get("config", {}))
        for tree in SKILL_TREES:
            if tree in filters:
                for rule, expected in REQUIRED_SKILL_DISABLED_RULES.items():
                    assert rule_config.get(rule) == expected, (
                        f"{rule} must be {expected!r} in the '{tree}' override; "
                        f"re-enabling it exposes {575 if rule == 'MD040' else 132} violations."
                    )
                covered_trees.add(tree)

    missing = set(SKILL_TREES) - covered_trees
    assert not missing, (
        f"skill tree(s) missing per-glob override: {missing}. "
        "Both trees must have MD040 and MD033 disabled."
    )


def test_all_ignores_globs_match_files(config: dict[str, object]) -> None:
    """Every skill-tree-related glob in ``ignores`` matches at least one file.

    Scoped to skill-tree paths (the attack surface for this regression).
    The specific failure mode to defend against: a scope measurement taken with
    the scope filter already applied -- the linter scans 0 files and reports
    0 violations, making the exclusion appear redundant when it is not.

    General tool directories (.git, .venv, node_modules, .claude/worktrees, etc.)
    are skipped: they may be empty or absent in worktrees and their exclusion is
    always necessary.
    """
    ignores = cast(list[str], config.get("ignores", []))
    # Only verify skill-related explicit ignores (not blanket tool dirs).
    skill_ignores = [
        p for p in ignores if not p.startswith("!") and ("skills/" in p or "skill" in p.lower())
    ]
    for pattern in skill_ignores:
        matched = list(REPO_ROOT.glob(pattern))
        assert matched, (
            f"skill-related ignore glob '{pattern}' matches zero files on disk; "
            "if the path was deleted or renamed, remove the stale entry."
        )


def test_all_override_filters_match_files(config: dict[str, object]) -> None:
    """Every ``filter`` entry in ``overrides`` matches at least one file on disk.

    A filter that matches nothing silently becomes inert -- the override rules
    apply to zero files, giving a false impression of coverage.  This is the
    same tautological-measurement pattern that caused issue #1837 to recur.
    """
    overrides = cast(list[dict[str, object]], config.get("overrides", []))
    for entry in overrides:
        for pattern in cast(list[str], entry.get("filter", [])):
            if pattern.startswith("!"):
                continue
            matched = list(REPO_ROOT.glob(pattern))
            assert matched, (
                f"override filter '{pattern}' matches zero files on disk; "
                "the override is inert and the rule configuration has no effect."
            )


def test_skill_tree_nonzero_file_count() -> None:
    """Running markdownlint on the skill tree lints a nonzero number of files.

    This is the isolating negative control for the tautological-measurement
    failure mode: if a blanket ``ignores`` entry covers the skill trees, the
    linter scans 0 files and reports 0 issues, making the exclusion appear
    redundant.  This test fails under that condition, exposing the suppression.

    With the correct per-glob overrides (no blanket exclusion), the linter
    scans 400+ files and this test passes.  The mutation that reverts to a
    blanket exclusion causes the linter to scan 0 files, failing this test.
    """
    result = subprocess.run(
        [
            "npx",
            "markdownlint-cli2@0.23.1",
            "--no-globs",
            "--",
            ".claude/skills/**/*.md",
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    output = result.stdout + result.stderr
    match = re.search(r"Linting:\s+(\d+)\s+file", output)
    file_count = int(match.group(1)) if match else 0
    assert file_count > 0, (
        f"markdownlint scanned 0 files in .claude/skills/**/*.md "
        f"(output: {output!r}). "
        "A blanket 'ignores' entry is likely suppressing the entire skill tree."
    )


def test_md024_scoped_to_siblings(config: dict[str, object]) -> None:
    """MD024 must be siblings_only so repeated platform sub-headings pass.

    docs/installation.md intentionally reuses "Claude Code" and "GitHub Copilot
    CLI" sub-headings under several distinct parent sections. siblings_only
    permits that while still catching true sibling duplicates.
    """
    md024 = cast(dict[str, Any], config["config"]).get("MD024")
    assert isinstance(md024, dict), "MD024 must be configured as a mapping"
    assert md024.get("siblings_only") is True


def test_md040_remains_enabled(config: dict[str, object]) -> None:
    """MD040 (fenced-code-language) stays on globally; per-glob overrides scope it.

    The global MD040 rule fires on agent files, README, and eval docs.
    The per-glob overrides for the skill trees disable it only there,
    where bare fences are illustrative and a language tag would mislead.
    """
    assert cast(dict[str, Any], config["config"]).get("MD040") is True


def test_md041_remains_enabled(config: dict[str, object]) -> None:
    """MD041 (first-line-heading) stays on; agent files keep their H1 to pass it."""
    assert cast(dict[str, Any], config["config"]).get("MD041") is True


# Worktree-root parity guard (issue #4248)
# All gitignored worktree root patterns must appear so a full-repo walk
# does not count duplicate .md files from sibling checkouts.
_REQUIRED_WORKTREE_IGNORES = [
    ".claude/worktrees/**",
    ".worktrees/**",
    ".wt/**",
    "worktree-*/**",
    "worktree--/**",
    "wt_*/**",
    "worktrees/**",
]
_REQUIRED_SESSION_SCRATCH_IGNORES = [".agent-scratch/**", ".scratch/**"]
_REQUIRED_GITIGNORE_WORKTREE = "wt_*/"


def test_all_worktree_roots_are_ignored(config: dict[str, object]) -> None:
    """Every gitignored worktree root pattern must appear in the ignores list.

    A missing entry causes the linter to walk the full worktree and count its
    .md files as if they were part of this repo (issue #4248).
    """
    ignores: list[str] = cast("list[str]", config.get("ignores", []))
    missing = [p for p in _REQUIRED_WORKTREE_IGNORES if p not in ignores]
    assert not missing, (
        f"Missing worktree ignore patterns in .markdownlint-cli2.yaml: {missing}"
    )


def test_wt_star_is_in_gitignore() -> None:
    """wt_*/ must be in .gitignore so the markdownlint ignore is meaningful.

    If .gitignore does not list wt_*/, the worktree directories are tracked
    by git and would not be excluded by the YAML ignore pattern alone.
    """
    gitignore = REPO_ROOT / ".gitignore"
    assert gitignore.is_file(), ".gitignore not found"
    content = gitignore.read_text(encoding="utf-8")
    assert "wt_*/" in content, ".gitignore is missing the 'wt_*/' entry (issue #4248)"


def test_session_scratch_roots_are_ignored(config: dict[str, object]) -> None:
    """Agent session scratch trees must never enter a Markdown full scan."""
    ignores: list[str] = cast("list[str]", config.get("ignores", []))
    missing = [p for p in _REQUIRED_SESSION_SCRATCH_IGNORES if p not in ignores]
    assert not missing, f"Missing session scratch ignores: {missing}"
