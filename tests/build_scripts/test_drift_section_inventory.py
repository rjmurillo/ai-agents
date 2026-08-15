"""Tests for section inventory in agent drift detection (Issue #4852).

Validates that unlisted H2 sections present on only one side fail the gate,
headings inside fenced code blocks are ignored, and platform-only exceptions
work correctly.
"""

from __future__ import annotations

import importlib.util
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
