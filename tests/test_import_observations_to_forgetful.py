"""Tests for .serena/scripts/import_observations_to_forgetful.py observation parsing."""

from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

_mod_name = "import_observations_to_forgetful"
_spec = importlib.util.spec_from_file_location(
    _mod_name,
    os.path.join(
        os.path.dirname(__file__),
        "..",
        ".serena",
        "scripts",
        "import_observations_to_forgetful.py",
    ),
)
_mod = importlib.util.module_from_spec(_spec)
sys.modules[_mod_name] = _mod
_spec.loader.exec_module(_mod)

get_domain_from_filename = _mod.get_domain_from_filename
get_project_info = _mod.get_project_info
safe_title = _mod.safe_title
parse_observation_file = _mod.parse_observation_file
DOMAIN_MAP = _mod.DOMAIN_MAP
CONFIDENCE_MAPPING = _mod.CONFIDENCE_MAPPING


class TestGetDomainFromFilename:
    def test_extracts_domain_from_observations_file(self) -> None:
        assert get_domain_from_filename("testing-observations.md") == "testing"

    def test_extracts_skills_domain(self) -> None:
        assert get_domain_from_filename("skills-testing-observations.md") == "skills-testing"

    def test_returns_stem_for_non_observation(self) -> None:
        assert get_domain_from_filename("random-file.md") == "random-file"

    def test_complex_domain_name(self) -> None:
        assert get_domain_from_filename("ci-infrastructure-observations.md") == "ci-infrastructure"


class TestGetProjectInfo:
    def test_known_domain_returns_mapped_info(self) -> None:
        info = get_project_info("testing")
        assert info["project_name"] == "testing"
        assert "testing" in info["keywords"]

    def test_unknown_domain_returns_default(self) -> None:
        info = get_project_info("unknown-domain-xyz")
        assert info["project_name"] == "unknown-domain-xyz"


class TestSafeTitle:
    def test_extracts_first_sentence(self) -> None:
        result = safe_title("Always run tests first. More detail here.")
        assert result == "Always run tests first."

    def test_strips_session_info(self) -> None:
        result = safe_title("Test point (Session 42, 2025-01-01)")
        assert "Session" not in result

    def test_truncates_long_titles(self) -> None:
        result = safe_title("x" * 200)
        assert len(result) <= 100

    def test_handles_exclamation(self) -> None:
        result = safe_title("Never do this! It will break things.")
        assert result == "Never do this!"


class TestParseObservationFile:
    def test_parses_constraints_section(self, tmp_path: Path) -> None:
        content = (
            "# Testing Observations\n\n"
            "## Constraints\n\n"
            "- Always run tests before committing\n"
            "  - Evidence: PR #100 broke CI\n"
            "- Never skip test coverage checks\n\n"
            "## Purpose\n\n"
            "Documentation.\n"
        )
        f = tmp_path / "testing-observations.md"
        f.write_text(content, encoding="utf-8")

        learnings = parse_observation_file(f, ["HIGH"])
        assert len(learnings) == 2
        assert learnings[0].confidence_level == "HIGH"
        assert learnings[0].learning_type == "constraint"

    def test_parses_preferences_section(self, tmp_path: Path) -> None:
        content = (
            "## Preferences\n\n"
            "- Use pytest over unittest\n"
        )
        f = tmp_path / "testing-observations.md"
        f.write_text(content, encoding="utf-8")

        learnings = parse_observation_file(f, ["MED"])
        assert len(learnings) == 1
        assert learnings[0].confidence_level == "MED"

    def test_filters_by_confidence(self, tmp_path: Path) -> None:
        content = (
            "## Constraints\n\n"
            "- High confidence item\n\n"
            "## Preferences\n\n"
            "- Medium confidence item\n"
        )
        f = tmp_path / "testing-observations.md"
        f.write_text(content, encoding="utf-8")

        # Only HIGH
        high = parse_observation_file(f, ["HIGH"])
        assert len(high) == 1

        # Only MED
        med = parse_observation_file(f, ["MED"])
        assert len(med) == 1

    def test_skips_none_items(self, tmp_path: Path) -> None:
        content = "## Constraints\n\n- None yet\n"
        f = tmp_path / "testing-observations.md"
        f.write_text(content, encoding="utf-8")

        learnings = parse_observation_file(f, ["HIGH"])
        assert len(learnings) == 0

    def test_captures_evidence(self, tmp_path: Path) -> None:
        content = (
            "## Constraints\n\n"
            "- Always validate input\n"
            "  - Evidence: CWE-20 input validation\n"
        )
        f = tmp_path / "testing-observations.md"
        f.write_text(content, encoding="utf-8")

        learnings = parse_observation_file(f, ["HIGH"])
        assert len(learnings) == 1
        assert len(learnings[0].evidence) == 1
        assert "CWE-20" in learnings[0].evidence[0]


class TestConfidenceMapping:
    def test_high_has_highest_importance(self) -> None:
        assert CONFIDENCE_MAPPING["HIGH"]["importance_min"] >= 9

    def test_low_has_lowest_confidence(self) -> None:
        assert CONFIDENCE_MAPPING["LOW"]["confidence"] < CONFIDENCE_MAPPING["HIGH"]["confidence"]
