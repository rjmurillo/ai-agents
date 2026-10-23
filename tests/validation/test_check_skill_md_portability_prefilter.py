"""Equivalence tests for the literal-core prefilter in the portability scan.

Issue #6734 sped the scan by skipping each boundary-anchored regex whose literal
core is absent from the prose. The skip is only safe when it never changes a
count. Each test compares the optimized count with the plain
``sum(pat.findall(prose))`` the scan used before, so a prefilter that drops a
real match, or counts on the core alone, fails here.
"""

from __future__ import annotations

import random

import pytest

from scripts.validation import check_skill_md_drift as drift
from scripts.validation import check_skill_md_portability as cmp


def _reference_count(prose: str) -> int:
    """The count before the prefilter: every pattern scans the whole prose."""
    return sum(len(pat.findall(prose)) for pat in cmp.UPSTREAM_PATTERNS)


# One prose sample per UPSTREAM_PATTERNS entry, in order, that the pattern counts.
_PER_PATTERN_SAMPLES: tuple[str, ...] = (
    "Read .agents/governance/a.md now.",
    "Write .project-toolkit/analysis/a.md now.",
    "Import from .claude/lib/helper.py now.",
    "See .claude/review-axes/x.md now.",
    "Run build/scripts/gen.py now.",
    "Edit templates/agents/x.md now.",
    "Edit templates/platforms/x.md now.",
    "Run scripts/validation/x.py now.",
)


class TestCoresCoverPatterns:
    def test_cores_cover_every_upstream_pattern(self) -> None:
        """One core per pattern, same order; a new pattern without a core fails."""
        assert len(drift.UPSTREAM_CORE_SOURCES) == len(cmp.UPSTREAM_PATTERNS)
        assert len(_PER_PATTERN_SAMPLES) == len(cmp.UPSTREAM_PATTERNS)
        for (core, pat), sample in zip(cmp._CORED_PATTERNS, _PER_PATTERN_SAMPLES, strict=True):
            assert pat.findall(sample), f"sample does not exercise {pat.pattern[:40]}"
            assert core.search(sample) is not None, f"core misses {core.pattern}"
            assert drift.UPSTREAM_CORES.search(sample) is not None

    @pytest.mark.parametrize("sample", _PER_PATTERN_SAMPLES)
    def test_each_pattern_still_counts(self, sample: str) -> None:
        assert cmp._count_prose_refs(sample) == _reference_count(sample) >= 1


class TestPrefilterEquivalence:
    @pytest.mark.parametrize(
        "prose",
        [
            "",
            "Plain prose with nothing upstream.\n",
            "The word scripts and build and templates alone are not paths.\n",
            "Read .agents/a.md and .agents/b.md.\n",
            "Mixed .agents/a.md then scripts/x.py then build/y.\n",
            "SCRIPTS/x.py and Templates/Agents/x.md\n",
            "[x](.agents/a.md) `scripts/x.py` \"build/y\" 'templates/agents'\n",
            "<img src=scripts/x.png>\n",
            "[ref]:scripts/x.py\n",
        ],
    )
    def test_matches_reference_on_known_shapes(self, prose: str) -> None:
        assert cmp._count_prose_refs(prose) == _reference_count(prose)

    def test_core_present_without_boundary_counts_zero(self) -> None:
        """The case a core-only prefilter would get wrong.

        ``subscripts/`` contains the core ``scripts/`` but the match has no
        boundary before it, so the pattern rejects it. An optimization that
        counted on the core alone would report 1 here.
        """
        prose = "Write subscripts/x and rebuild/y and mytemplates/agents.\n"

        assert drift.UPSTREAM_CORES.search(prose) is not None
        assert cmp._count_prose_refs(prose) == _reference_count(prose) == 0

    def test_unicode_case_fold_is_not_lost(self) -> None:
        """The pattern is IGNORECASE; a lowercase-literal prefilter would drop this.

        U+017F (long s) folds to ``s`` under ``re.IGNORECASE``. A ``.lower()``
        plus substring prefilter would not see it, so the cores use the same flag.
        """
        prose = "Run ſcripts/x.py now.\n"

        assert _reference_count(prose) == 1
        assert cmp._count_prose_refs(prose) == 1

    def test_pattern_whose_core_is_absent_does_not_hide_one_that_is_present(self) -> None:
        prose = "Only scripts/x.py here, and nothing else.\n"

        assert cmp._count_prose_refs(prose) == _reference_count(prose) == 1

    def test_randomized_fragments_match_reference(self) -> None:
        """Seeded fuzz over fragments that include near misses of every core."""
        fragments = [
            " ", "\n", "(", "[", '"', "`", "<", ">", "- ", "/", "\\", ".", "x", "sub",
            ".agents", ".agents/", ".project-toolkit/", ".claude/lib/", ".claude/review-axes",
            "build/", "build", "scripts/", "scripts", "templates/agents", "templates/platforms",
            "templates/", "SCRIPTS/", "Build\\", "path:", "[a]:", "<a href=", "<img src=",
            "ſ", ".agent", ".claude/", "a.md", "x.py",
        ]  # fmt: skip
        rng = random.Random(6734)
        for _ in range(3000):
            prose = "".join(rng.choice(fragments) for _ in range(rng.randint(0, 14)))
            assert cmp._count_prose_refs(prose) == _reference_count(prose), repr(prose)


class TestCountFileRefsUnchanged:
    def test_count_file_refs_and_marker_counts_match_reference(self) -> None:
        text = (
            "Read .agents/a.md.\n\n```bash\ncp scripts/x.py .\n```\n\n"
            "    indented build/y\n\nAnd templates/agents/z.md.\n"
        )
        prose = cmp._strip_code(text)

        assert cmp.count_file_refs(text) == _reference_count(prose) == 2
        assert cmp.count_upstream_refs(text) == 2

    def test_marker_still_suppresses_and_counts(self) -> None:
        text = "<!-- vendor-portability: cites .agents/a.md -->\n\nRead .agents/a.md.\n"

        assert cmp.count_file_refs(text) == 0
        assert cmp.count_marker_suppressed_refs(text) == 1

    def test_marker_removal_can_join_a_reference_and_is_still_counted(self) -> None:
        """Counting runs on the marker-free text, so a spliced path is a ref.

        An optimization that tested the raw text for a core before removing the
        marker would see no ``.agents`` here and report 0.
        """
        text = (
            "<!-- vendor-portability: note -->\n\n"
            "Read .age<!-- vendor-portability: x -->nts/a.md.\n"
        )

        without = cmp._MARKER_PATTERN.sub("", text)
        assert "Read .agents/a.md." in without
        assert cmp.count_marker_suppressed_refs(text) == _reference_count(cmp._strip_code(without))
        assert cmp.count_marker_suppressed_refs(text) == 1
