#!/usr/bin/env python3
"""Tests for validate_investigation_claims.py."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest import mock

# Add script directory to path
_SCRIPT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(_SCRIPT_DIR))

from validate_investigation_claims import (  # noqa: E402
    file_matches_allowlist,
    session_claims_investigation_only,
    validate_investigation_claims,
)


class TestFileMatchesAllowlist:
    """Tests for file_matches_allowlist function."""

    def test_agents_sessions_allowed(self):
        assert file_matches_allowlist(".agents/sessions/2026-01-01.json")

    def test_agents_analysis_allowed(self):
        assert file_matches_allowlist(".agents/analysis/report.md")

    def test_agents_retrospective_allowed(self):
        assert file_matches_allowlist(".agents/retrospective/retro.md")

    def test_serena_memories_allowed(self):
        assert file_matches_allowlist(".serena/memories/test.md")

    def test_agents_security_allowed(self):
        assert file_matches_allowlist(".agents/security/scan.md")

    def test_agents_memory_allowed(self):
        assert file_matches_allowlist(".agents/memory/graph.json")

    def test_review_docs_allowed(self):
        assert file_matches_allowlist(".agents/architecture/REVIEW-ADR-034.md")

    def test_critique_allowed(self):
        assert file_matches_allowlist(".agents/critique/debate.md")

    def test_code_file_rejected(self):
        assert not file_matches_allowlist("scripts/main.py")

    def test_src_file_rejected(self):
        assert not file_matches_allowlist("src/component.ts")

    def test_workflow_rejected(self):
        assert not file_matches_allowlist(".github/workflows/ci.yml")

    def test_agent_prompts_rejected(self):
        assert not file_matches_allowlist(".claude/agents/analyst.md")

    def test_planning_rejected(self):
        assert not file_matches_allowlist(".agents/planning/PRD.md")

    def test_architecture_adr_rejected(self):
        assert not file_matches_allowlist(".agents/architecture/ADR-001.md")


class TestSessionClaimsInvestigationOnly:
    """Tests for session_claims_investigation_only function."""

    def test_detects_investigation_claim_in_evidence(self, tmp_path):
        session = {
            "protocolCompliance": {
                "sessionEnd": {
                    "qaValidation": {
                        "complete": True,
                        "evidence": "SKIPPED: investigation-only",
                    }
                }
            }
        }
        path = tmp_path / "session.json"
        path.write_text(json.dumps(session))
        assert session_claims_investigation_only(path)

    def test_detects_claim_case_insensitive(self, tmp_path):
        session = {
            "protocolCompliance": {
                "sessionEnd": {
                    "qaValidation": {
                        "evidence": "skipped: INVESTIGATION-ONLY",
                    }
                }
            }
        }
        path = tmp_path / "session.json"
        path.write_text(json.dumps(session))
        assert session_claims_investigation_only(path)

    def test_no_claim_returns_false(self, tmp_path):
        session = {
            "protocolCompliance": {
                "sessionEnd": {
                    "qaValidation": {
                        "evidence": "QA report: .agents/qa/report.md",
                    }
                }
            }
        }
        path = tmp_path / "session.json"
        path.write_text(json.dumps(session))
        assert not session_claims_investigation_only(path)

    def test_invalid_json_returns_false(self, tmp_path):
        path = tmp_path / "session.json"
        path.write_text("not valid json")
        assert not session_claims_investigation_only(path)


class TestValidateInvestigationClaims:
    """Tests for validate_investigation_claims function."""

    def test_no_sessions_returns_valid(self, tmp_path):
        result = validate_investigation_claims(tmp_path)
        assert result.valid
        assert result.sessions_checked == 0

    def test_session_without_claim_is_valid(self, tmp_path):
        session = {"protocolCompliance": {"sessionEnd": {}}}
        (tmp_path / "session.json").write_text(json.dumps(session))

        result = validate_investigation_claims(tmp_path)
        assert result.valid
        assert result.claims_found == 0

    def test_valid_claim_passes(self, tmp_path):
        session = {
            "protocolCompliance": {
                "sessionEnd": {
                    "qaValidation": {
                        "evidence": "SKIPPED: investigation-only",
                    }
                }
            }
        }
        (tmp_path / "session.json").write_text(json.dumps(session))

        with mock.patch(
            "validate_investigation_claims.get_commit_for_session",
            return_value="abc1234",
        ):
            with mock.patch(
                "validate_investigation_claims.get_files_in_commit",
                return_value=[".agents/sessions/log.json", ".serena/memories/m.md"],
            ):
                result = validate_investigation_claims(tmp_path)

        assert result.valid
        assert result.claims_found == 1
        assert len(result.violations) == 0

    def test_invalid_claim_fails(self, tmp_path):
        session = {
            "protocolCompliance": {
                "sessionEnd": {
                    "qaValidation": {
                        "evidence": "SKIPPED: investigation-only",
                    }
                }
            }
        }
        (tmp_path / "session.json").write_text(json.dumps(session))

        with mock.patch(
            "validate_investigation_claims.get_commit_for_session",
            return_value="abc1234",
        ):
            with mock.patch(
                "validate_investigation_claims.get_files_in_commit",
                return_value=[".agents/sessions/log.json", "scripts/main.py"],
            ):
                result = validate_investigation_claims(tmp_path)

        assert not result.valid
        assert result.claims_found == 1
        assert len(result.violations) == 1
        assert result.violations[0].disallowed_files == ["scripts/main.py"]
