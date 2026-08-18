"""Tests for section inventory in agent drift detection (Issue #4852).

Validates that unlisted H2 sections present on only one side fail the gate,
headings inside fenced code blocks are ignored, and platform-only exceptions
work correctly.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
_SCRIPT = REPO_ROOT / "build" / "scripts" / "detect_agent_drift.py"

_spec = importlib.util.spec_from_file_location("detect_agent_drift", _SCRIPT)
assert _spec is not None and _spec.loader is not None
drift = importlib.util.module_from_spec(_spec)
sys.modules.setdefault("detect_agent_drift", drift)
_spec.loader.exec_module(drift)


# --- get_markdown_sections: fenced block awareness --------------------------


class TestFencedBlockAwareness:
    """Headings inside fenced code blocks must not appear in section inventory."""

    def test_heading_inside_fence_ignored(self) -> None:
        content = (
            "## Real Section\n\nSome content.\n\n"
            "```markdown\n## Fake Heading\n\nSample output.\n```\n\n"
            "## Another Real\n\nMore content.\n"
        )
        sections = drift.get_markdown_sections(content)
        assert "Real Section" in sections
        assert "Another Real" in sections
        assert "Fake Heading" not in sections

    def test_heading_outside_fence_detected(self) -> None:
        content = "## Visible\n\nContent here.\n"
        sections = drift.get_markdown_sections(content)
        assert "Visible" in sections

    def test_nested_fence_markers(self) -> None:
        """Only top-level ``` toggles fence state."""
        content = (
            "## Before\n\nProse.\n\n"
            "```\n## InFence\n```\n\n"
            "## After\n\nMore.\n"
        )
        sections = drift.get_markdown_sections(content)
        assert "Before" in sections
        assert "After" in sections
        assert "InFence" not in sections

    def test_tilde_fence_hides_heading(self) -> None:
        """CommonMark tilde fences (~~~) hide headings the same as backticks."""
        content = "## Before\n\n~~~\n## InFence\n~~~\n\n## After\n\nMore.\n"
        sections = drift.get_markdown_sections(content)
        assert "Before" in sections
        assert "After" in sections
        assert "InFence" not in sections

    def test_indented_fence_under_list_item_hides_heading(self) -> None:
        """A fence indented under a list item (up to 3 spaces) still fences."""
        content = (
            "## Before\n\n"
            "1. Step\n"
            "   ```bash\n"
            "   ## not a heading\n"
            "   ```\n\n"
            "## After\n\nMore.\n"
        )
        sections = drift.get_markdown_sections(content)
        assert "Before" in sections
        assert "After" in sections
        assert "not a heading" not in sections

    def test_four_backtick_outer_fence_tolerates_three_backtick_inner(self) -> None:
        """A 4-backtick outer fence is not closed by a shorter 3-backtick line.

        Real example: .github/agents/task-decomposer.agent.md uses a
        4-backtick outer fence wrapping a 3-backtick inner code sample.
        """
        content = (
            "## Before\n\n"
            "````markdown\n"
            "```bash\n"
            "## inner fake heading\n"
            "```\n"
            "````\n\n"
            "## After\n\nMore.\n"
        )
        sections = drift.get_markdown_sections(content)
        assert "Before" in sections
        assert "After" in sections
        assert "inner fake heading" not in sections

    def test_mismatched_fence_characters_do_not_close_each_other(self) -> None:
        """A backtick line inside an open tilde fence does not close it."""
        content = (
            "## Before\n\n~~~\n## Still Fenced\n```\n## Also Fenced\n~~~\n\n## After\n\nMore.\n"
        )
        sections = drift.get_markdown_sections(content)
        assert "Before" in sections
        assert "After" in sections
        assert "Still Fenced" not in sections
        assert "Also Fenced" not in sections


# --- Section inventory: missing section detection ---------------------------


def _make_agent(sections: list[str]) -> str:
    """Build a minimal agent body with the given H2 sections."""
    lines = ["# Agent\n"]
    for s in sections:
        lines.append(f"## {s}\n\nContent for {s}.\n")
    return "\n".join(lines)


class TestSectionInventory:
    """Unlisted sections on one side must fail unless exempted."""

    def test_missing_section_detected(self) -> None:
        """A section on claude side but not vscode side fails."""
        claude = _make_agent(["Core Mission", "Context Maintenance"])
        vscode = _make_agent(["Core Mission"])
        result = drift.compare_agent(claude, vscode, "orchestrator", 80)
        assert "Context Maintenance" in result.missing_sections
        assert result.status == "DRIFT DETECTED"

    def test_listed_section_not_double_counted(self) -> None:
        """Sections in SECTIONS_TO_COMPARE are handled by content comparison."""
        claude = _make_agent(["Core Mission"])
        vscode = _make_agent(["Core Mission"])
        result = drift.compare_agent(claude, vscode, "test-agent", 80)
        assert result.missing_sections == []
        assert result.status != "DRIFT DETECTED"

    def test_both_sides_same_sections_passes(self) -> None:
        """Identical section sets produce no missing sections."""
        sections = ["Core Mission", "Custom Section", "Another"]
        claude = _make_agent(sections)
        vscode = _make_agent(sections)
        result = drift.compare_agent(claude, vscode, "test-agent", 80)
        assert result.missing_sections == []

    def test_platform_only_exception_accepted(self) -> None:
        """Sections in PLATFORM_ONLY_SECTIONS are adapters, not failures."""
        claude = _make_agent(["Core Mission", "Claude Code Tools"])
        vscode = _make_agent(["Core Mission"])
        result = drift.compare_agent(claude, vscode, "implementer", 80)
        assert "Claude Code Tools" in result.adapter_sections
        assert "Claude Code Tools" not in result.missing_sections
        assert result.status != "DRIFT DETECTED"

    def test_harmless_prose_no_false_positive(self) -> None:
        """Sections that exist on both sides don't trigger missing."""
        claude = _make_agent(["Core Mission", "Harmless Prose"])
        vscode = _make_agent(["Core Mission", "Harmless Prose"])
        result = drift.compare_agent(claude, vscode, "test-agent", 80)
        assert result.missing_sections == []


# --- Reproduce false negatives from #4850 and #4851 -------------------------


class TestFalseNegativeReproduction:
    """Reproduce the two false negatives cited in the issue."""

    def test_orchestrator_context_maintenance_detected(self) -> None:
        """#4851: Context Maintenance on Claude only must fail."""
        claude = _make_agent(["Core Mission", "Context Maintenance"])
        vscode = _make_agent(["Core Mission"])
        result = drift.compare_agent(claude, vscode, "orchestrator", 80)
        assert "Context Maintenance" in result.missing_sections
        assert result.status == "DRIFT DETECTED"

    def test_qa_completeness_verification_detected(self) -> None:
        """#4850: Completeness Verification missing on Copilot must fail."""
        claude = _make_agent(
            ["Core Mission", "Completeness Verification (Mandatory)"]
        )
        vscode = _make_agent(["Core Mission"])
        result = drift.compare_agent(claude, vscode, "qa", 80)
        # This is both a REQUIRED section and would be missing in inventory
        assert result.status == "DRIFT DETECTED"


# --- Report separates counts ------------------------------------------------


class TestReportCounts:
    """Report must separate missing, content drift, and adapter counts."""

    def test_format_text_includes_counts(self) -> None:
        claude = _make_agent(["Core Mission", "Only Here", "Claude Code Tools"])
        vscode = _make_agent(["Core Mission"])
        result = drift.compare_agent(claude, vscode, "implementer", 80)
        results = [result]
        output = drift.format_text(results, 80, 0.1, 1, 0, 0)
        assert "Missing sections: 1" in output
        assert "Declared adapters: 1" in output


# --- Generated mirror parity: section sets must match -----------------------


class TestMirrorParity:
    """Sections added to one generated file must appear in the other."""

    def test_section_only_in_vscode_fails(self) -> None:
        """A section only on the vscode side also fails."""
        claude = _make_agent(["Core Mission"])
        vscode = _make_agent(["Core Mission", "Output Bounds"])
        result = drift.compare_agent(claude, vscode, "orchestrator", 80)
        assert "Output Bounds" in result.missing_sections
        assert result.status == "DRIFT DETECTED"


# --- Platform-only exceptions are direction-aware ---------------------------


class TestPlatformOnlyExceptionIsDirectionAware:
    """PLATFORM_ONLY_SECTIONS must not exempt an inverted gap (review finding)."""

    def test_declared_side_is_exempted(self) -> None:
        """Claude Code Tools present on claude, absent on vscode: exempted."""
        claude = _make_agent(["Core Mission", "Claude Code Tools"])
        vscode = _make_agent(["Core Mission"])
        result = drift.compare_agent(claude, vscode, "implementer", 80)
        assert "Claude Code Tools" in result.adapter_sections
        assert "Claude Code Tools" not in result.missing_sections
        assert result.status != "DRIFT DETECTED"

    def test_inverted_side_is_not_exempted(self) -> None:
        """The same section name appearing on the OTHER side is real drift.

        PLATFORM_ONLY_SECTIONS[("implementer", "Claude Code Tools")] declares
        the section Claude-only. If it instead shows up only on the vscode
        side, that is an inverted gap the exception does not cover, and it
        must fail rather than silently pass through the same dict key.
        """
        claude = _make_agent(["Core Mission"])
        vscode = _make_agent(["Core Mission", "Claude Code Tools"])
        result = drift.compare_agent(claude, vscode, "implementer", 80)
        assert "Claude Code Tools" in result.missing_sections
        assert "Claude Code Tools" not in result.adapter_sections
        assert result.status == "DRIFT DETECTED"


# --- A baselined pair cannot suppress a NEW missing section -----------------


class TestBaselineCannotSuppressNewMissingSection:
    """Issue #4852 AC: existing baselines cannot hide a newly missing section.

    Regression test for a bug found in review: ``compare_agent`` gated the
    missing-section failure on ``not pair_is_baselined``, so an agent pair
    already accepted in ``KNOWN_BASELINE_DRIFT`` (for its content-similarity
    floor) could grow a brand-new missing section without the gate noticing.
    """

    def test_baselined_pair_still_fails_on_new_missing_section(self) -> None:
        assert ("merge-resolver", "src-claude vs src-vscode") in drift.KNOWN_BASELINE_DRIFT
        claude = _make_agent(["Core Mission", "Brand New Section"])
        vscode = _make_agent(["Core Mission"])
        result = drift.compare_agent(
            claude, vscode, "merge-resolver", 80, "src-claude vs src-vscode"
        )
        assert "Brand New Section" in result.missing_sections
        assert result.status == "DRIFT DETECTED"


# --- _exit_code: missing sections always block, in both comparisons --------


class TestExitCodeMissingSectionsAlwaysBlock:
    """Issue #4852 AC-1: a missing H2 section fails by default, install-copy
    comparison included, without needing ``--fail-on-install-drift``.
    """

    def test_install_comparison_missing_section_blocks_without_flag(self) -> None:
        result = drift.AgentResult(
            agent_name="qa",
            overall_similarity=95.0,
            status="DRIFT DETECTED",
            missing_sections=["New Section"],
            comparison=drift._INSTALL_COMPARISON_LABEL,
        )
        assert drift._exit_code([result], fail_on_install=False) == 1

    def test_install_comparison_content_drift_only_stays_advisory_without_flag(self) -> None:
        """Content drift (no missing section) in the install comparison stays
        advisory by default; ``--fail-on-install-drift`` promotes it."""
        result = drift.AgentResult(
            agent_name="qa",
            overall_similarity=50.0,
            status="DRIFT DETECTED",
            comparison=drift._INSTALL_COMPARISON_LABEL,
        )
        assert drift._exit_code([result], fail_on_install=False) == 0
        assert drift._exit_code([result], fail_on_install=True) == 1


# --- JSON output carries the same three categories as text ------------------


class TestJsonOutputIncludesMissingAndAdapterSections:
    """format_json must not silently drop missing/adapter data (review finding).

    scripts/ci/parse_drift_results.py and the weekly alert workflow only see
    the JSON output; a missing-only agent must be nameable from it.
    """

    def test_json_output_includes_missing_and_adapter_fields(self) -> None:
        claude = _make_agent(["Core Mission", "Only Here", "Claude Code Tools"])
        vscode = _make_agent(["Core Mission"])
        result = drift.compare_agent(claude, vscode, "implementer", 80)
        payload = json.loads(drift.format_json([result], 80, 0.1, 1, 0, 0))

        agent_json = payload["results"][0]
        assert agent_json["missingSections"] == ["Only Here"]
        assert agent_json["adapterSections"] == ["Claude Code Tools"]
        assert payload["summary"]["missingSections"] == 1
        assert payload["summary"]["adapterSections"] == 1


# --- Real corpus: drive the actual generated/vendored trees -----------------


class TestRealCorpusSectionInventory:
    """Drive section inventory against the real repo trees, not fabricated
    strings (review finding: a test built entirely from ``_make_agent``
    fixtures cannot catch drift between the actual src/claude,
    src/vs-code-agents, .claude/agents, and .github/agents corpora).
    """

    def test_vendored_corpus_has_no_unbaselined_missing_sections(self) -> None:
        claude_path = REPO_ROOT / "src" / "claude"
        vscode_path = REPO_ROOT / "src" / "vs-code-agents"
        results = drift.run_detection(claude_path, vscode_path, 80)

        assert len(results) > 10, "sanity check: the real corpus was not read"
        unbaselined = [
            (r.agent_name, section) for r in results for section in r.missing_sections
        ]
        assert unbaselined == [], f"unbaselined missing sections: {unbaselined}"

    def test_install_corpus_has_no_unbaselined_missing_sections(self) -> None:
        templates_path = REPO_ROOT / "templates" / "agents"
        claude_install_path = REPO_ROOT / ".claude" / "agents"
        github_install_path = REPO_ROOT / ".github" / "agents"
        results = drift.run_install_detection(
            templates_path, claude_install_path, github_install_path, 80
        )

        assert len(results) > 5, "sanity check: the real install corpus was not read"
        unbaselined = [
            (r.agent_name, section) for r in results for section in r.missing_sections
        ]
        assert unbaselined == [], f"unbaselined missing sections: {unbaselined}"

    def test_full_gate_exits_zero_against_current_tree(self) -> None:
        """End-to-end: the real CLI entry point, the real repo state."""
        exit_code = drift.main(["--all"])
        assert exit_code == 0
