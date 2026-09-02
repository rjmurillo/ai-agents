"""Local-axis routing must match what each scanner actually reads.

A local axis is one scanner. Routing it at a change whose files that scanner
skips produces a run over zero files, which `adapt_local_axis_verdict` reports
as UNKNOWN, so the axis can never reach PASS and the review cannot finish. That
is not hypothetical: `executable-code` covered `.rs` and `.rb`, which neither
scanner scores, and `docs-and-instructions` covered `.mdx`, `.rst`, and `.txt`,
which `doc-accuracy` never inventories.

The parity tests here compare the selector's mirrors against the scanner
sources themselves rather than against a copied literal, so widening either
scanner reds this module instead of silently re-opening the gap.

Kept out of ``test_select_axes.py`` and ``test_select_axes_contract.py``
because both are already over the 500-line taste limit.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

TESTS_SKILLS_DIR = str(Path(__file__).resolve().parents[1])
PROJECT_ROOT = Path(__file__).resolve().parents[3]
if TESTS_SKILLS_DIR not in sys.path:
    sys.path.insert(0, TESTS_SKILLS_DIR)

from claude_skills_import import import_skill_script

mod = import_skill_script(
    ".claude/skills/review/scripts/select_axes.py",
    module_name="review_select_axes_capability",
)
assess = import_skill_script(
    ".claude/skills/code-qualities-assessment/scripts/assess.py",
    module_name="capability_assess",
)
taste = import_skill_script(
    ".claude/skills/taste-lints/scripts/taste_lints.py",
    module_name="capability_taste_lints",
)
doc_accuracy = import_skill_script(
    ".claude/skills/doc-accuracy/scripts/doc_accuracy.py",
    module_name="capability_doc_accuracy",
)
scan_principles = import_skill_script(
    ".claude/skills/golden-principles/scripts/scan_principles.py",
    module_name="capability_scan_principles",
)

REFERENCES_DIR = PROJECT_ROOT / ".claude" / "skills" / "review" / "references"
CANDIDATES = tuple(mod.discover_canonical_axes(REFERENCES_DIR))


def select(paths: list[str], **kwargs: object) -> dict:
    return mod.select_axes(changed_paths=paths, canonical_candidates=CANDIDATES, **kwargs)


class TestMirrorsMatchTheScannerSources:
    """The selector's copies must equal the scanners' own acceptance sets."""

    def test_assess_suffixes_match_language_map(self):
        assert mod._ASSESS_SUFFIXES == frozenset(assess._LANGUAGE_BY_SUFFIX)

    def test_taste_lint_suffixes_match_scannable_extensions(self):
        assert mod._TASTE_LINT_SUFFIXES == frozenset(taste.SCANNABLE_EXTENSIONS)

    def test_doc_accuracy_globs_are_still_markdown_only(self):
        """Widening DOC_GLOBS must force the routing predicate to widen too."""
        assert doc_accuracy.DOC_GLOBS == ["docs/**/*.md", "**/*.md"]

    def test_doc_accuracy_excluded_dirs_match_the_scanner(self):
        """The inventory walk prunes these, so a matching suffix is not enough."""
        assert mod._DOC_ACCURACY_EXCLUDED_DIRS == frozenset(doc_accuracy.EXCLUDE_DIRS)

    @pytest.mark.parametrize("excluded", sorted(doc_accuracy.EXCLUDE_DIRS))
    def test_markdown_under_an_excluded_dir_is_not_routed(self, excluded):
        """Parity for every excluded directory, not just the reported one.

        This repository tracks `build/AGENTS.md`, which matches `**/*.md` and is
        still never inventoried, so routing it produced an empty scan and an
        UNKNOWN the review could not finish on.
        """
        assert not mod._doc_accuracy_reads(f"{excluded}/AGENTS.md")

    def test_markdown_outside_an_excluded_dir_is_still_routed(self):
        """Negative control: the exclusion must not swallow ordinary docs."""
        assert mod._doc_accuracy_reads("docs/guide.md")
        assert mod._doc_accuracy_reads("README.md")

    def test_excluded_name_as_the_file_is_not_an_excluded_dir(self):
        """The walk prunes directories, so only parent segments count."""
        assert mod._doc_accuracy_reads("docs/build.md")

    @pytest.mark.parametrize(
        "path",
        [
            ".claude/skills/review/SKILL.md",
            ".CLAUDE/SKILLS/review/SKILL.MD",
            ".claude/skills/review/skill.md",
            ".claude/agents/architect.md",
            ".claude/agents/CLAUDE.md",
            ".claude/agents/Claude.md",
            ".github/workflows/ci.yml",
            ".github/workflows/CI.YML",
            "scripts/setup.sh",
            "scripts/setup.SH",
            "src/app.py",
            "docs/guide.md",
        ],
    )
    def test_golden_principles_mirror_matches_is_applicable(self, path):
        """Behavioral parity with the scanner's own guard, casing included."""
        assert mod._golden_principles_reads(path) is scan_principles._is_applicable(path)


class TestLocalRoutingFollowsScannerSupport:
    """One supported and one unsupported language per scanner."""

    @pytest.mark.parametrize("path", ["src/app.ts", "src/App.java", "src/main.go"])
    def test_assess_only_languages_skip_taste_lints(self, path):
        local = set(select([path])["local_selected"])
        assert "code-qualities-assessment" in local
        assert "taste-lints" not in local

    @pytest.mark.parametrize("path", ["scripts/deploy.ps1", "scripts/setup.sh"])
    def test_taste_lint_only_languages_skip_assess(self, path):
        local = set(select([path])["local_selected"])
        assert "taste-lints" in local
        assert "code-qualities-assessment" not in local

    @pytest.mark.parametrize("path", ["src/main.rs", "lib/widget.rb"])
    def test_languages_neither_scanner_reads_select_no_local_axis(self, path):
        """The reported case: both selected, both scanned nothing, both UNKNOWN."""
        result = select([path])
        assert result["local_selected"] == []
        assert result["fail_closed"] is False

    @pytest.mark.parametrize("path", ["src/main.rs", "lib/widget.rb"])
    def test_canonical_code_quality_still_reviews_them(self, path):
        """Negative control: the narrowing touches local axes only.

        A subagent reads Rust and Ruby fine, so dropping the scanners must not
        leave the change unreviewed.
        """
        assert "code-quality" in select([path])["canonical_selected"]

    def test_python_still_selects_both_scanners(self):
        """Negative control: .py is the one suffix both scanners accept."""
        local = set(select(["src/service.py"])["local_selected"])
        assert {"code-qualities-assessment", "taste-lints"} <= local

    def test_skip_reason_names_the_scanner_gap(self):
        result = select(["src/main.rs"])
        assert "scanner reads" in result["skipped"]["taste-lints"]


class TestCaseSensitivityFollowsEachScanner:
    """The classifier lowercases; the scanners do not all agree with that."""

    def test_uppercase_markdown_is_not_read_by_doc_accuracy(self):
        """DOC_GLOBS matches case-sensitively, so `.MD` is never inventoried.

        Asserted on the predicate rather than on `local_selected`, because a
        `.MD`-only diff now strands the path and fails the run closed, which
        selects every axis. The routing decision is the predicate.
        """
        assert not mod._doc_accuracy_reads("README.MD")
        assert select(["README.MD"])["fail_closed"] is True

    def test_uppercase_skill_path_is_not_routed_to_golden_principles(self):
        """The reported case: selected, zero applicable files, UNKNOWN."""
        assert "golden-principles" not in select([".CLAUDE/SKILLS/review/SKILL.MD"])[
            "local_selected"
        ]

    def test_real_cased_skill_path_is_still_routed(self):
        """Negative control: the fix must not stop routing the real path."""
        assert "golden-principles" in select([".claude/skills/review/SKILL.md"])[
            "local_selected"
        ]

    def test_uppercase_suffix_still_reaches_assess(self):
        """assess.py folds case (`suffix.lower()`), so the mirror must too."""
        assert "code-qualities-assessment" in select(["src/App.PY"])["local_selected"]


class TestOverrideModesKeepEveryLocalAxis:
    """Deep and fail-closed are explicit run-everything modes."""

    def test_deep_keeps_every_local_axis(self):
        assert set(select(["src/main.rs"], deep=True)["local_selected"]) == set(mod.LOCAL_AXES)

    def test_fail_closed_keeps_every_local_axis(self):
        result = select(["some/unclassifiable/blob.bin"])
        assert result["fail_closed"] is True
        assert set(result["local_selected"]) == set(mod.LOCAL_AXES)

    def test_pin_overrides_the_scanner_narrowing(self):
        """A caller who names the axis gets it, scanner support or not."""
        result = select(["src/main.rs"], pinned=["taste-lints"])
        assert "taste-lints" in result["local_selected"]


class TestExecutableCodeCoversEveryScannerSuffix:
    """`_CODE_SUFFIXES` must be a superset of what the local scanners read.

    A suffix missing from it never matches `executable-code`, so the row cannot
    contribute `code-quality` or either scanner. When another row has already
    classified the path, the run is not fail-closed either, so the shortfall is
    silent.
    """

    def test_code_suffixes_cover_every_scanner_suffix(self):
        """Negative control by construction: enrolling a suffix in either
        scanner without adding it here reds this test."""
        scanner_suffixes = mod._ASSESS_SUFFIXES | mod._TASTE_LINT_SUFFIXES
        # The scanners also read data and doc formats that are not source code;
        # executable-code speaks for source only.
        non_source = {".yml", ".yaml", ".md", ".json"}
        assert (scanner_suffixes - non_source) <= mod._CODE_SUFFIXES

    def test_bash_under_a_toolkit_path_still_reaches_taste_lints(self):
        """Reported case: toolkit-governance classified it and nothing else ran.

        taste_lints reads `.bash`, so skipping it here lost a real scan without
        failing the run closed.
        """
        result = select(["scripts/setup.bash"])
        assert result["fail_closed"] is False
        assert "code-quality" in result["canonical_selected"]
        assert "taste-lints" in result["local_selected"]

    @pytest.mark.parametrize(
        "path", [".claude/hooks/thing.mjs", ".claude/skills/demo/helper.cjs"]
    )
    def test_mjs_and_cjs_under_an_agent_path_still_reach_assess(self, path):
        """Reported case: agent-artifacts classified it and assess never ran."""
        result = select([path])
        assert result["fail_closed"] is False
        assert "code-quality" in result["canonical_selected"]
        assert "code-qualities-assessment" in result["local_selected"]

    def test_bash_does_not_reach_assess(self):
        """Negative control: widening the row must not widen the scanners."""
        assert "code-qualities-assessment" not in select(["scripts/setup.bash"])["local_selected"]

    def test_mjs_does_not_reach_taste_lints(self):
        """Negative control in the other direction."""
        assert "taste-lints" not in select([".claude/hooks/thing.mjs"])["local_selected"]


class TestUnreviewablePathsFailClosed:
    """Narrowing a local axis must not leave a path reviewed by nobody.

    The narrowing is safe while another axis still covers the path.
    `executable-code` also contributes the canonical `code-quality` subagent, so
    a Rust file stays reviewed. `docs-and-instructions` and
    `toolkit-governance` contribute local axes alone, so dropping theirs strands
    the path: it is classified, every claiming axis skips it, and the run can
    still finish PASS with no evidence about the change at all.
    """

    @pytest.mark.parametrize("path", ["build/AGENTS.md", "README.MD"])
    def test_stranded_documentation_fails_the_run_closed(self, path):
        """Both reach doc-accuracy's row and neither can be inventoried.

        `build/AGENTS.md` is tracked in this repository and pruned by
        EXCLUDE_DIRS; `README.MD` matches the lowercased docs predicate but not
        the case-sensitive glob.
        """
        result = select([path])
        assert result["fail_closed"] is True
        assert path in result["unclassified_paths"]

    @pytest.mark.parametrize("path", ["src/main.rs", "lib/widget.rb"])
    def test_code_paths_do_not_fail_closed(self, path):
        """Negative control: the canonical axis still covers them.

        Without this, the fix for the unreadable-scanner routing would turn
        every Rust or Ruby change into a full deep review.
        """
        result = select([path])
        assert result["fail_closed"] is False
        assert "code-quality" in result["canonical_selected"]

    @pytest.mark.parametrize(
        "path", ["docs/guide.md", "src/app.py", "scripts/setup.bash", ".github/workflows/ci.yml"]
    )
    def test_covered_paths_do_not_fail_closed(self, path):
        """Negative control: an axis that can read the file keeps the run open."""
        assert select([path])["fail_closed"] is False

    def test_one_stranded_path_strands_the_whole_run(self):
        """Fail-closed is per run, so a covered sibling does not excuse it."""
        result = select(["docs/guide.md", "build/AGENTS.md"])
        assert result["fail_closed"] is True
        assert "build/AGENTS.md" in result["unclassified_paths"]
        assert "docs/guide.md" not in result["unclassified_paths"]


class TestLocalAxisNeedsThePathThatRoutedIt:
    """A selected local axis must read a path that actually selected it.

    Asking whether the scanner reads any changed path conflates two files. With
    `README.md` and `src/main.rs`, only the Rust file routes taste-lints
    (through `executable-code`) and only the README is readable by it, so a
    whole-list question kept the axis: taste-lints then scanned the README,
    skipped the Rust file, and a clean result was adapted to PASS. The report
    said the axis passed without scanning the path that selected it.
    """

    def test_effect_table_routes_no_local_axis(self):
        """The premise: local selections come only from paths.

        If an effect ever routes a local axis it has no path to check, and the
        path filter would drop it. This reds first so that change is deliberate.
        """
        assert not any(local for _canonical, local in mod._EFFECT_TABLE.values())

    def test_axis_dropped_when_only_an_unreadable_path_routed_it(self):
        result = select(["README.md", "src/main.rs"])
        assert result["fail_closed"] is False
        assert "taste-lints" not in result["local_selected"]
        assert "scanner reads" in result["skipped"]["taste-lints"]

    def test_readable_router_keeps_the_axis(self):
        """Negative control: the same README beside a Python file.

        Now `src/app.py` routes taste-lints and taste-lints reads it, so the
        axis is kept. Without this the fix above would look like "any mixed
        diff drops the axis".
        """
        result = select(["README.md", "src/app.py"])
        local = set(result["local_selected"])
        assert {"doc-accuracy", "taste-lints", "code-qualities-assessment"} <= local

    def test_doc_accuracy_survives_the_same_diff(self):
        """Negative control: the README still routes and feeds doc-accuracy."""
        assert "doc-accuracy" in select(["README.md", "src/main.rs"])["local_selected"]

    def test_routed_paths_are_tracked_per_axis(self):
        routed = mod.routed_local_paths(["README.md", "src/main.rs"])
        assert routed["doc-accuracy"] == ["README.md"]
        assert routed["taste-lints"] == ["src/main.rs"]
