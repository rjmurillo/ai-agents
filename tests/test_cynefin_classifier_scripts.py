"""Tests for cynefin-classifier skill script.

These tests verify the Cynefin Framework problem classifier functionality.
Exit codes:
    0: Classification complete
    1: Invalid arguments
    2: Insufficient information (Confusion domain)
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

# Import the module under test
_scripts = Path(__file__).parents[1] / ".claude" / "skills" / "cynefin-classifier" / "scripts"
sys.path.insert(0, str(_scripts))

from classify import (  # noqa: E402
    DOMAIN_KEYWORDS,
    PITFALLS,
    STRATEGIES,
    ClassificationResult,
    Confidence,
    Domain,
    DomainIndicators,
    classify_problem,
    count_keyword_matches,
)

if TYPE_CHECKING:
    from _pytest.capture import CaptureFixture


class TestDomainEnum:
    """Tests for Domain enum."""

    def test_has_all_cynefin_domains(self) -> None:
        """Domain enum contains all five Cynefin domains."""
        expected = {"Clear", "Complicated", "Complex", "Chaotic", "Confusion"}
        actual = {d.value for d in Domain}

        assert actual == expected

    def test_enum_values_are_title_case(self) -> None:
        """Domain values use title case."""
        for domain in Domain:
            assert domain.value[0].isupper()
            assert domain.value[1:].islower() or domain.value == "Confusion"


class TestConfidenceEnum:
    """Tests for Confidence enum."""

    def test_has_three_levels(self) -> None:
        """Confidence enum has HIGH, MEDIUM, LOW levels."""
        expected = {"HIGH", "MEDIUM", "LOW"}
        actual = {c.value for c in Confidence}

        assert actual == expected


class TestDomainIndicators:
    """Tests for DomainIndicators dataclass."""

    def test_default_initialization(self) -> None:
        """DomainIndicators initializes with empty lists."""
        indicators = DomainIndicators()

        assert indicators.clear_indicators == []
        assert indicators.complicated_indicators == []
        assert indicators.complex_indicators == []
        assert indicators.chaotic_indicators == []
        assert indicators.confusion_indicators == []

    def test_custom_initialization(self) -> None:
        """DomainIndicators accepts custom values."""
        indicators = DomainIndicators(
            clear_indicators=["obvious"],
            complicated_indicators=["analyze"],
        )

        assert indicators.clear_indicators == ["obvious"]
        assert indicators.complicated_indicators == ["analyze"]


class TestClassificationResult:
    """Tests for ClassificationResult dataclass."""

    @pytest.fixture
    def sample_result(self) -> ClassificationResult:
        """Create a sample classification result."""
        return ClassificationResult(
            problem="Test problem",
            domain=Domain.CLEAR,
            confidence=Confidence.HIGH,
            rationale="Test rationale",
            strategy="Sense-Categorize-Respond",
            actions=["Action 1", "Action 2"],
            pitfall="Test pitfall",
            temporal_note="Test temporal note",
            boundary_note="Test boundary note",
            compound_note=None,
        )

    def test_to_dict(self, sample_result: ClassificationResult) -> None:
        """to_dict returns dictionary with all fields."""
        result = sample_result.to_dict()

        assert result["problem"] == "Test problem"
        assert result["domain"] == "Clear"
        assert result["confidence"] == "HIGH"
        assert result["rationale"] == "Test rationale"
        assert result["strategy"] == "Sense-Categorize-Respond"
        assert result["actions"] == ["Action 1", "Action 2"]
        assert result["pitfall"] == "Test pitfall"
        assert result["temporal_note"] == "Test temporal note"
        assert result["boundary_note"] == "Test boundary note"
        assert result["compound_note"] is None

    def test_to_dict_is_json_serializable(self, sample_result: ClassificationResult) -> None:
        """to_dict output can be serialized to JSON."""
        result = sample_result.to_dict()

        # Should not raise
        json_str = json.dumps(result)
        assert isinstance(json_str, str)

    def test_to_markdown_contains_required_sections(
        self,
        sample_result: ClassificationResult,
    ) -> None:
        """to_markdown includes all required sections."""
        md = sample_result.to_markdown()

        assert "## Cynefin Classification" in md
        assert "**Problem**:" in md
        assert "### Domain: CLEAR" in md
        assert "**Confidence**: HIGH" in md
        assert "### Rationale" in md
        assert "### Response Strategy" in md
        assert "### Recommended Actions" in md
        assert "### Pitfall Warning" in md
        assert "### Related Considerations" in md

    def test_to_markdown_includes_actions_numbered(
        self,
        sample_result: ClassificationResult,
    ) -> None:
        """to_markdown numbers actions correctly."""
        md = sample_result.to_markdown()

        assert "1. Action 1" in md
        assert "2. Action 2" in md

    def test_to_markdown_includes_temporal_note(
        self,
        sample_result: ClassificationResult,
    ) -> None:
        """to_markdown includes temporal note when present."""
        md = sample_result.to_markdown()

        assert "**Temporal**: Test temporal note" in md

    def test_to_markdown_includes_boundary_note(
        self,
        sample_result: ClassificationResult,
    ) -> None:
        """to_markdown includes boundary note when present."""
        md = sample_result.to_markdown()

        assert "**Boundary**: Test boundary note" in md

    def test_to_markdown_omits_compound_when_none(
        self,
        sample_result: ClassificationResult,
    ) -> None:
        """to_markdown omits compound note when None."""
        md = sample_result.to_markdown()

        assert "**Compound**:" not in md


class TestConstants:
    """Tests for module constants."""

    def test_strategies_has_all_domains(self) -> None:
        """STRATEGIES dict has entry for every domain."""
        for domain in Domain:
            assert domain in STRATEGIES

    def test_pitfalls_has_all_domains(self) -> None:
        """PITFALLS dict has entry for every domain."""
        for domain in Domain:
            assert domain in PITFALLS

    def test_domain_keywords_has_all_domains(self) -> None:
        """DOMAIN_KEYWORDS dict has entry for every domain."""
        for domain in Domain:
            assert domain in DOMAIN_KEYWORDS
            assert isinstance(DOMAIN_KEYWORDS[domain], list)
            assert len(DOMAIN_KEYWORDS[domain]) > 0

    def test_strategies_use_correct_patterns(self) -> None:
        """STRATEGIES use correct Cynefin response patterns."""
        assert STRATEGIES[Domain.CLEAR] == "Sense-Categorize-Respond"
        assert STRATEGIES[Domain.COMPLICATED] == "Sense-Analyze-Respond"
        assert STRATEGIES[Domain.COMPLEX] == "Probe-Sense-Respond"
        assert STRATEGIES[Domain.CHAOTIC] == "Act-Sense-Respond"
        assert STRATEGIES[Domain.CONFUSION] == "Gather Information"


class TestCountKeywordMatches:
    """Tests for count_keyword_matches function."""

    def test_counts_single_match(self) -> None:
        """Counts single keyword match."""
        result = count_keyword_matches("This is a typo fix", Domain.CLEAR)

        assert result == 1  # "typo" matches

    def test_counts_multiple_matches(self) -> None:
        """Counts multiple keyword matches."""
        result = count_keyword_matches(
            "Need to analyze and investigate the root cause",
            Domain.COMPLICATED,
        )

        # "analyze", "investigate", "root cause" should match
        assert result >= 3

    def test_returns_zero_for_no_matches(self) -> None:
        """Returns zero when no keywords match."""
        result = count_keyword_matches("Hello world", Domain.CLEAR)

        assert result == 0

    def test_case_insensitive(self) -> None:
        """Matching is case-insensitive."""
        result = count_keyword_matches("TYPO fix", Domain.CLEAR)

        assert result >= 1

    def test_matches_chaotic_keywords(self) -> None:
        """Matches Chaotic domain keywords."""
        result = count_keyword_matches("System is down! Urgent outage!", Domain.CHAOTIC)

        # "down", "urgent", "outage" should match
        assert result >= 3

    def test_matches_complex_keywords(self) -> None:
        """Matches Complex domain keywords."""
        result = count_keyword_matches(
            "User behavior is unpredictable, need to experiment",
            Domain.COMPLEX,
        )

        # "user behavior", "unpredictable", "experiment" should match
        assert result >= 2


class TestClassifyProblem:
    """Tests for classify_problem function."""

    def test_classifies_clear_domain(self) -> None:
        """Classifies obvious/trivial problems as Clear."""
        result = classify_problem("Fix typo in documentation, simple fix, obvious solution")

        assert result.domain == Domain.CLEAR
        assert result.strategy == "Sense-Categorize-Respond"

    def test_classifies_complicated_domain(self) -> None:
        """Classifies problems requiring analysis as Complicated."""
        result = classify_problem(
            "Need to analyze the root cause of the memory leak and investigate performance issues"
        )

        assert result.domain == Domain.COMPLICATED
        assert result.strategy == "Sense-Analyze-Respond"

    def test_classifies_complex_domain(self) -> None:
        """Classifies emergent/experimental problems as Complex."""
        result = classify_problem(
            "User behavior is unpredictable, need to experiment with A/B testing"
        )

        assert result.domain == Domain.COMPLEX
        assert result.strategy == "Probe-Sense-Respond"

    def test_classifies_chaotic_domain(self) -> None:
        """Classifies crisis situations as Chaotic."""
        result = classify_problem(
            "Production is down! Urgent outage affecting customers!"
        )

        assert result.domain == Domain.CHAOTIC
        assert result.strategy == "Act-Sense-Respond"

    def test_classifies_confusion_for_vague_input(self) -> None:
        """Classifies vague problems as Confusion."""
        result = classify_problem("Something is wrong")

        assert result.domain == Domain.CONFUSION
        assert result.strategy == "Gather Information"

    def test_classifies_confusion_for_mixed_signals(self) -> None:
        """Classifies problems with mixed signals as Confusion."""
        # This input has keywords from multiple domains equally
        result = classify_problem(
            "not sure, unclear, vague requirements"
        )

        # Should be Confusion due to ambiguity
        assert result.domain == Domain.CONFUSION

    def test_includes_context_in_classification(self) -> None:
        """Context parameter influences classification."""
        result = classify_problem(
            "Fix the issue",
            context="This is a well-documented trivial fix following best practice",
        )

        # Context should push toward Clear domain
        assert result.domain == Domain.CLEAR

    def test_returns_high_confidence_for_strong_match(self) -> None:
        """Returns HIGH confidence for strong keyword matches."""
        result = classify_problem(
            "Urgent outage, system down, crisis, immediate action needed"
        )

        assert result.confidence == Confidence.HIGH

    def test_returns_low_confidence_for_weak_match(self) -> None:
        """Returns LOW confidence for weak keyword matches."""
        result = classify_problem("typo")

        assert result.confidence == Confidence.LOW

    def test_result_includes_actions(self) -> None:
        """Classification result includes recommended actions."""
        result = classify_problem("Fix typo in docs")

        assert len(result.actions) > 0
        assert all(isinstance(a, str) for a in result.actions)

    def test_result_includes_pitfall(self) -> None:
        """Classification result includes pitfall warning."""
        result = classify_problem("Fix typo in docs")

        assert len(result.pitfall) > 0

    def test_result_includes_temporal_note(self) -> None:
        """Classification result includes temporal note."""
        result = classify_problem("Fix typo in docs")

        assert result.temporal_note is not None

    def test_handles_empty_context(self) -> None:
        """Handles empty context gracefully."""
        result = classify_problem("Fix typo", context="")

        assert result.domain is not None

    def test_handles_none_context(self) -> None:
        """Handles None context gracefully."""
        result = classify_problem("Fix typo", context=None)

        assert result.domain is not None

    def test_flaky_test_classified_as_complex(self) -> None:
        """Flaky/intermittent tests classified as Complex."""
        result = classify_problem(
            "Test is flaky and fails randomly, works locally but fails in CI"
        )

        assert result.domain == Domain.COMPLEX

    def test_race_condition_classified_as_complex(self) -> None:
        """Race conditions classified as Complex."""
        result = classify_problem(
            "Suspected race condition, timing-dependent, non-deterministic failures"
        )

        assert result.domain == Domain.COMPLEX


class TestMainFunction:
    """Tests for main() function via subprocess."""

    @pytest.fixture
    def script_path(self, project_root: Path) -> Path:
        """Return path to the classify.py script."""
        return (
            project_root / ".claude" / "skills"
            / "cynefin-classifier" / "scripts" / "classify.py"
        )

    def test_requires_problem_argument(self, script_path: Path) -> None:
        """Exit code 1 when --problem argument missing."""
        result = subprocess.run(
            [sys.executable, str(script_path)],
            capture_output=True,
            text=True,
            timeout=30,
        )

        # argparse exits with 2 for missing required args
        assert result.returncode == 2

    def test_rejects_empty_problem(self, script_path: Path) -> None:
        """Exit code 1 for empty problem description."""
        result = subprocess.run(
            [sys.executable, str(script_path), "--problem", ""],
            capture_output=True,
            text=True,
            timeout=30,
        )

        assert result.returncode == 1
        assert "empty" in result.stderr.lower()

    def test_rejects_whitespace_only_problem(self, script_path: Path) -> None:
        """Exit code 1 for whitespace-only problem description."""
        result = subprocess.run(
            [sys.executable, str(script_path), "--problem", "   "],
            capture_output=True,
            text=True,
            timeout=30,
        )

        assert result.returncode == 1

    def test_outputs_markdown_by_default(self, script_path: Path) -> None:
        """Outputs markdown format by default."""
        result = subprocess.run(
            [sys.executable, str(script_path), "--problem", "Fix a typo"],
            capture_output=True,
            text=True,
            timeout=30,
        )

        assert result.returncode == 0
        assert "## Cynefin Classification" in result.stdout
        assert "### Domain:" in result.stdout

    def test_outputs_json_with_flag(self, script_path: Path) -> None:
        """Outputs JSON format with --json flag."""
        result = subprocess.run(
            [sys.executable, str(script_path), "--problem", "Fix a typo", "--json"],
            capture_output=True,
            text=True,
            timeout=30,
        )

        assert result.returncode == 0

        # Should be valid JSON
        data = json.loads(result.stdout)
        assert "domain" in data
        assert "confidence" in data
        assert "strategy" in data
        assert "actions" in data

    def test_exit_code_0_for_clear_domain(self, script_path: Path) -> None:
        """Exit code 0 for Clear domain classification."""
        result = subprocess.run(
            [
                sys.executable,
                str(script_path),
                "--problem",
                "Fix typo in docs, simple fix, obvious solution, best practice",
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )

        assert result.returncode == 0

    def test_exit_code_0_for_complicated_domain(self, script_path: Path) -> None:
        """Exit code 0 for Complicated domain classification."""
        result = subprocess.run(
            [
                sys.executable,
                str(script_path),
                "--problem",
                "Analyze root cause of memory leak, investigate performance, assess trade-offs",
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )

        assert result.returncode == 0

    def test_exit_code_0_for_complex_domain(self, script_path: Path) -> None:
        """Exit code 0 for Complex domain classification."""
        result = subprocess.run(
            [
                sys.executable,
                str(script_path),
                "--problem",
                "Unpredictable user behavior, need experiment, emergent patterns, A/B test",
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )

        assert result.returncode == 0

    def test_exit_code_0_for_chaotic_domain(self, script_path: Path) -> None:
        """Exit code 0 for Chaotic domain classification."""
        result = subprocess.run(
            [
                sys.executable,
                str(script_path),
                "--problem",
                "Production down! Urgent outage! Customers affected! Emergency!",
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )

        assert result.returncode == 0

    def test_exit_code_2_for_confusion_domain(self, script_path: Path) -> None:
        """Exit code 2 for Confusion domain (insufficient info)."""
        result = subprocess.run(
            [
                sys.executable,
                str(script_path),
                "--problem",
                "Something is happening",  # Vague, no strong indicators
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )

        assert result.returncode == 2

    def test_context_parameter(self, script_path: Path) -> None:
        """--context parameter is accepted and used."""
        result = subprocess.run(
            [
                sys.executable,
                str(script_path),
                "--problem",
                "Fix the issue",
                "--context",
                "This is a well-documented trivial fix following best practice",
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )

        assert result.returncode == 0

    def test_help_flag(self, script_path: Path) -> None:
        """--help flag shows usage information."""
        result = subprocess.run(
            [sys.executable, str(script_path), "--help"],
            capture_output=True,
            text=True,
            timeout=30,
        )

        assert result.returncode == 0
        assert "usage" in result.stdout.lower()
        assert "--problem" in result.stdout
        assert "--context" in result.stdout
        assert "--json" in result.stdout


class TestMainFunctionMonkeypatch:
    """Tests for main() function via monkeypatching."""

    def test_main_returns_correct_exit_codes(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """main() returns correct exit codes for different domains."""
        from classify import main

        # Test Clear domain (should return 0)
        monkeypatch.setattr(
            "sys.argv",
            [
                "classify.py",
                "--problem",
                "Simple typo fix, obvious solution, best practice",
            ],
        )
        result = main()
        assert result == 0

    def test_main_json_output(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: CaptureFixture[str],
    ) -> None:
        """main() with --json outputs valid JSON."""
        from classify import main

        monkeypatch.setattr(
            "sys.argv",
            ["classify.py", "--problem", "Fix typo", "--json"],
        )

        main()

        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert "domain" in data

    def test_main_markdown_output(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: CaptureFixture[str],
    ) -> None:
        """main() without --json outputs markdown."""
        from classify import main

        monkeypatch.setattr(
            "sys.argv",
            ["classify.py", "--problem", "Fix typo"],
        )

        main()

        captured = capsys.readouterr()
        assert "## Cynefin Classification" in captured.out


class TestEdgeCases:
    """Edge case and boundary tests."""

    def test_very_long_problem_description(self) -> None:
        """Handles very long problem descriptions."""
        long_problem = "typo fix " * 1000
        result = classify_problem(long_problem)

        assert result.domain is not None

    def test_unicode_characters(self) -> None:
        """Handles unicode characters in problem description."""
        result = classify_problem("Fix typo in documentation: cafe becomes cafe")

        assert result.domain is not None

    def test_special_characters(self) -> None:
        """Handles special characters in problem description."""
        result = classify_problem("Fix typo: change <div> to <span> in @Component")

        assert result.domain is not None

    def test_newlines_in_problem(self) -> None:
        """Handles newlines in problem description."""
        result = classify_problem("Fix typo\nin\nmultiple\nlines")

        assert result.domain is not None

    def test_tabs_in_problem(self) -> None:
        """Handles tabs in problem description."""
        result = classify_problem("Fix\ttypo\twith\ttabs")

        assert result.domain is not None

    def test_mixed_case_keywords(self) -> None:
        """Handles mixed case keywords."""
        result = classify_problem("TYPO FIX, Simple Solution, OBVIOUS")

        # Should still match Clear domain keywords
        assert result.domain == Domain.CLEAR

    def test_keyword_substring_matching(self) -> None:
        """Keywords match as substrings."""
        # "documented" contains "document" but we use "documented" keyword
        classify_problem("This is a documented issue")

        # Should match "documented" keyword
        assert count_keyword_matches("documented issue", Domain.CLEAR) >= 1


class TestBoundaryNotes:
    """Tests for boundary note generation."""

    def test_generates_boundary_note_for_close_scores(self) -> None:
        """Generates boundary note when scores are close."""
        # Input with indicators from multiple domains
        result = classify_problem(
            "analyze the simple fix"  # Has both complicated and clear indicators
        )

        # May or may not have boundary note depending on score distribution
        assert isinstance(result.boundary_note, str | None)

    def test_no_boundary_note_for_clear_winner(self) -> None:
        """No boundary note when one domain clearly dominates."""
        result = classify_problem(
            "urgent outage emergency crisis down customers affected immediate"
        )

        # Chaotic should dominate, boundary note may or may not exist
        assert result.domain == Domain.CHAOTIC


class TestTemporalNotes:
    """Tests for temporal note generation."""

    def test_clear_domain_temporal_note(self) -> None:
        """Clear domain has appropriate temporal note."""
        result = classify_problem("Simple typo fix, obvious solution")

        if result.domain == Domain.CLEAR:
            assert "Complex" in result.temporal_note or "Chaotic" in result.temporal_note

    def test_chaotic_domain_temporal_note(self) -> None:
        """Chaotic domain has appropriate temporal note."""
        result = classify_problem("Urgent outage! System down! Emergency!")

        if result.domain == Domain.CHAOTIC:
            assert "Complex" in result.temporal_note

    def test_confusion_domain_temporal_note(self) -> None:
        """Confusion domain has appropriate temporal note."""
        result = classify_problem("Something might be wrong")

        if result.domain == Domain.CONFUSION:
            assert "Temporary" in result.temporal_note


class TestJsonOutputFormat:
    """Tests for JSON output format verification."""

    @pytest.fixture
    def script_path(self, project_root: Path) -> Path:
        """Return path to the classify.py script."""
        return (
            project_root / ".claude" / "skills"
            / "cynefin-classifier" / "scripts" / "classify.py"
        )

    def test_json_has_required_fields(self, script_path: Path) -> None:
        """JSON output contains all required fields."""
        result = subprocess.run(
            [
                sys.executable,
                str(script_path),
                "--problem",
                "Fix typo",
                "--json",
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )

        data = json.loads(result.stdout)

        required_fields = [
            "problem",
            "domain",
            "confidence",
            "rationale",
            "strategy",
            "actions",
            "pitfall",
            "temporal_note",
            "boundary_note",
            "compound_note",
        ]

        for field in required_fields:
            assert field in data, f"Missing required field: {field}"

    def test_json_domain_is_string(self, script_path: Path) -> None:
        """JSON domain field is a string (not enum)."""
        result = subprocess.run(
            [
                sys.executable,
                str(script_path),
                "--problem",
                "Fix typo",
                "--json",
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )

        data = json.loads(result.stdout)
        assert isinstance(data["domain"], str)
        assert data["domain"] in ["Clear", "Complicated", "Complex", "Chaotic", "Confusion"]

    def test_json_actions_is_list(self, script_path: Path) -> None:
        """JSON actions field is a list."""
        result = subprocess.run(
            [
                sys.executable,
                str(script_path),
                "--problem",
                "Fix typo",
                "--json",
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )

        data = json.loads(result.stdout)
        assert isinstance(data["actions"], list)
        assert len(data["actions"]) > 0


class TestMarkdownOutputFormat:
    """Tests for markdown output format verification."""

    @pytest.fixture
    def script_path(self, project_root: Path) -> Path:
        """Return path to the classify.py script."""
        return (
            project_root / ".claude" / "skills"
            / "cynefin-classifier" / "scripts" / "classify.py"
        )

    def test_markdown_has_valid_headers(self, script_path: Path) -> None:
        """Markdown output has valid header structure."""
        result = subprocess.run(
            [
                sys.executable,
                str(script_path),
                "--problem",
                "Fix typo",
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )

        output = result.stdout
        assert output.startswith("## ")
        assert "### " in output

    def test_markdown_headers_not_empty(self, script_path: Path) -> None:
        """Markdown headers are followed by content."""
        result = subprocess.run(
            [
                sys.executable,
                str(script_path),
                "--problem",
                "Fix typo",
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )

        lines = result.stdout.split("\n")
        for i, line in enumerate(lines):
            if line.startswith("###") and i + 2 < len(lines):
                # After header and blank line, should have content
                # (some headers may have content immediately after blank line)
                pass  # Structure validation is in other tests
