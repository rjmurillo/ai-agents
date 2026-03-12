"""Tests for .serena/scripts/import_observations_to_forgetful.py observation parsing."""

from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

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
assert _spec is not None, "Failed to find import_observations_to_forgetful.py"
_mod = importlib.util.module_from_spec(_spec)
sys.modules[_mod_name] = _mod
assert _spec.loader is not None, "Module spec has no loader"
_spec.loader.exec_module(_mod)

get_domain_from_filename = _mod.get_domain_from_filename
get_project_info = _mod.get_project_info
safe_title = _mod.safe_title
parse_observation_file = _mod.parse_observation_file
build_memory_payload = _mod.build_memory_payload
main = _mod.main
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


class TestBuildMemoryPayload:
    def test_builds_payload_with_required_fields(self) -> None:
        learning = _mod.Learning(
            domain="testing",
            project_name="testing",
            base_keywords=["testing", "validation"],
            confidence_level="HIGH",
            learning_type="constraint",
            text="Always run tests before committing.",
            source_file=".serena/memories/testing-observations.md",
        )
        payload = build_memory_payload(learning, project_id=0)
        assert payload["title"] == "Always run tests before committing."
        assert "testing" in payload["keywords"]
        assert payload["confidence"] == 1.0
        assert payload["source_repo"] == "rjmurillo/ai-agents"

    def test_includes_evidence_in_content(self) -> None:
        learning = _mod.Learning(
            domain="security",
            project_name="security",
            base_keywords=["security"],
            confidence_level="MED",
            learning_type="edge-case",
            text="Check for CWE-20.",
            evidence=["Found in PR #200"],
            source_file=".serena/memories/security-observations.md",
        )
        payload = build_memory_payload(learning, project_id=0)
        assert "Found in PR #200" in payload["content"]


class TestMainMcpIntegration:
    """Verify non-dry-run path calls McpClient.call_tool('create_memory', ...)."""

    @staticmethod
    def _observation_file(tmp_path: Path) -> Path:
        content = (
            "## Constraints\n\n"
            "- Always validate input before processing\n"
        )
        f = tmp_path / "testing-observations.md"
        f.write_text(content, encoding="utf-8")
        return f

    def test_non_dry_run_calls_create_memory(self, tmp_path: Path) -> None:
        obs_file = self._observation_file(tmp_path)
        mock_client = MagicMock()
        mock_client.call_tool.return_value = {"content": [{"text": "ok"}]}

        mock_cls = MagicMock()
        mock_cls.create.return_value = mock_client
        mock_cls.is_available.return_value = True

        with patch.object(_mod, "_get_mcp_client_class", return_value=mock_cls):
            result = main([
                "--observation-file", str(obs_file),
                "--confidence-levels", "HIGH",
                "--output-path", str(tmp_path / "results.json"),
            ])

        assert result == 0
        mock_client.call_tool.assert_called_once()
        call_args = mock_client.call_tool.call_args
        assert call_args[0][0] == "create_memory"
        assert "title" in call_args[0][1]
        mock_client.close.assert_called_once()

    def test_dry_run_does_not_create_client(self, tmp_path: Path) -> None:
        obs_file = self._observation_file(tmp_path)

        with patch.object(_mod, "_get_mcp_client_class") as mock_get_cls:
            result = main([
                "--observation-file", str(obs_file),
                "--confidence-levels", "HIGH",
                "--dry-run",
                "--output-path", str(tmp_path / "results.json"),
            ])

        assert result == 0
        mock_get_cls.assert_not_called()

    def test_mcp_error_tracked_in_results(self, tmp_path: Path) -> None:
        obs_file = self._observation_file(tmp_path)
        mock_client = MagicMock()
        mock_client.call_tool.side_effect = Exception("Connection refused")

        mock_cls = MagicMock()
        mock_cls.create.return_value = mock_client
        mock_cls.is_available.return_value = True

        output_path = tmp_path / "results.json"
        with patch.object(_mod, "_get_mcp_client_class", return_value=mock_cls):
            result = main([
                "--observation-file", str(obs_file),
                "--confidence-levels", "HIGH",
                "--output-path", str(output_path),
            ])

        assert result == 1
        import json
        results = json.loads(output_path.read_text())
        assert len(results["errors"]) == 1
        assert "Connection refused" in results["errors"][0]["error"]
        mock_client.close.assert_called_once()
