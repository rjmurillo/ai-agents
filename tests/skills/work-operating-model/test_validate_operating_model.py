#!/usr/bin/env python3
"""Tests for validate_operating_model module."""

from __future__ import annotations

import io
import json
import sys
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

import pytest

TESTS_SKILLS_DIR = str(Path(__file__).resolve().parents[1])
if TESTS_SKILLS_DIR not in sys.path:
    sys.path.insert(0, TESTS_SKILLS_DIR)

from claude_skills_import import import_skill_script  # noqa: E402

mod = import_skill_script(".claude/skills/work-operating-model/scripts/validate_operating_model.py")
validate = mod.validate
load_document = mod.load_document
main = mod.main


def _minimal_valid_document() -> dict:
    return {
        "schema_version": "1.0.0",
        "team": {"name": "Platform"},
        "rhythms": {"cadences": [], "milestones": []},
        "decisions": {"decision_rights": [], "review_triggers": []},
        "dependencies": {"upstream": [], "downstream": []},
        "institutional_knowledge": {"tacit": []},
        "friction": {"blockers": []},
        "metadata": {
            "interview_date": "2026-04-27",
            "interview_status": "complete",
            "completed_layers": list(mod.CANONICAL_LAYERS),
        },
    }


class TestValidateMinimum:
    """Tests for the minimum valid document."""

    def test_minimum_valid_document_passes(self) -> None:
        assert validate(_minimal_valid_document()) == []

    def test_in_progress_status_passes(self) -> None:
        document = _minimal_valid_document()
        document["metadata"]["interview_status"] = "in_progress"
        document["metadata"]["completed_layers"] = ["rhythms", "decisions"]
        assert validate(document) == []

    def test_root_must_be_object(self) -> None:
        errors = validate(["not", "an", "object"])
        assert errors == ["root: must be a JSON object"]

    def test_root_string_rejected(self) -> None:
        errors = validate("nope")
        assert errors == ["root: must be a JSON object"]


class TestRequiredKeys:
    """Tests for the required top-level keys."""

    @pytest.mark.parametrize("missing_key", list(mod.REQUIRED_TOP_LEVEL))
    def test_missing_required_key_reported(self, missing_key: str) -> None:
        document = _minimal_valid_document()
        del document[missing_key]
        errors = validate(document)
        assert any(missing_key in error for error in errors)

    def test_wrong_schema_version_rejected(self) -> None:
        document = _minimal_valid_document()
        document["schema_version"] = "2.0.0"
        errors = validate(document)
        assert any("schema_version" in error for error in errors)


class TestTeamSection:
    """Tests for the team section."""

    def test_team_must_be_object(self) -> None:
        document = _minimal_valid_document()
        document["team"] = "Platform"
        errors = validate(document)
        assert "team: must be an object" in errors

    def test_team_name_required(self) -> None:
        document = _minimal_valid_document()
        document["team"] = {}
        errors = validate(document)
        assert "team.name: must be a non-empty string" in errors

    def test_team_name_empty_string_rejected(self) -> None:
        document = _minimal_valid_document()
        document["team"]["name"] = "   "
        errors = validate(document)
        assert "team.name: must be a non-empty string" in errors

    def test_team_size_optional(self) -> None:
        document = _minimal_valid_document()
        document["team"]["size"] = 8
        assert validate(document) == []

    def test_team_size_null_allowed(self) -> None:
        document = _minimal_valid_document()
        document["team"]["size"] = None
        assert validate(document) == []

    def test_team_size_negative_rejected(self) -> None:
        document = _minimal_valid_document()
        document["team"]["size"] = -1
        errors = validate(document)
        assert any("team.size" in error for error in errors)

    def test_team_size_bool_rejected(self) -> None:
        document = _minimal_valid_document()
        document["team"]["size"] = True
        errors = validate(document)
        assert any("team.size" in error for error in errors)


class TestRhythmsSection:
    """Tests for the rhythms section."""

    def test_rhythms_must_be_object(self) -> None:
        document = _minimal_valid_document()
        document["rhythms"] = []
        errors = validate(document)
        assert "rhythms: must be an object" in errors

    def test_cadences_must_be_list(self) -> None:
        document = _minimal_valid_document()
        document["rhythms"]["cadences"] = "weekly"
        errors = validate(document)
        assert "rhythms.cadences: must be a list" in errors

    def test_cadence_source_enum_enforced(self) -> None:
        document = _minimal_valid_document()
        document["rhythms"]["cadences"] = [{"name": "standup", "source": "rumored"}]
        errors = validate(document)
        assert any("rhythms.cadences[0].source" in error for error in errors)

    def test_cadence_with_documented_source_passes(self) -> None:
        document = _minimal_valid_document()
        document["rhythms"]["cadences"] = [
            {"name": "standup", "frequency": "daily", "source": "documented"},
        ]
        assert validate(document) == []


class TestDecisionsSection:
    """Tests for the decisions section."""

    def test_formality_enum_enforced(self) -> None:
        document = _minimal_valid_document()
        document["decisions"]["decision_rights"] = [
            {"decision_type": "arch", "formality": "ad-hoc"}
        ]
        errors = validate(document)
        assert any("decisions.decision_rights[0].formality" in error for error in errors)

    def test_review_triggers_must_be_list(self) -> None:
        document = _minimal_valid_document()
        document["decisions"]["review_triggers"] = "quarterly"
        errors = validate(document)
        assert "decisions.review_triggers: must be a list" in errors


class TestDependenciesSection:
    """Tests for the dependencies section."""

    def test_criticality_enum_enforced(self) -> None:
        document = _minimal_valid_document()
        document["dependencies"]["upstream"] = [{"name": "auth", "criticality": "huge"}]
        errors = validate(document)
        assert any("dependencies.upstream[0].criticality" in error for error in errors)

    def test_downstream_must_be_list(self) -> None:
        document = _minimal_valid_document()
        document["dependencies"]["downstream"] = {}
        errors = validate(document)
        assert "dependencies.downstream: must be a list" in errors


class TestInstitutionalKnowledge:
    """Tests for the institutional_knowledge section."""

    def test_documentation_status_enum_enforced(self) -> None:
        document = _minimal_valid_document()
        document["institutional_knowledge"]["tacit"] = [
            {"topic": "deploy ritual", "documentation_status": "vague"},
        ]
        errors = validate(document)
        assert any(
            "institutional_knowledge.tacit[0].documentation_status" in error for error in errors
        )


class TestFrictionSection:
    """Tests for the friction section."""

    def test_impact_enum_enforced(self) -> None:
        document = _minimal_valid_document()
        document["friction"]["blockers"] = [{"description": "slow ci", "impact": "huge"}]
        errors = validate(document)
        assert any("friction.blockers[0].impact" in error for error in errors)

    def test_category_enum_enforced(self) -> None:
        document = _minimal_valid_document()
        document["friction"]["blockers"] = [
            {"description": "slow ci", "category": "vibes"},
        ]
        errors = validate(document)
        assert any("friction.blockers[0].category" in error for error in errors)


class TestMetadataSection:
    """Tests for the metadata section."""

    def test_metadata_must_be_object(self) -> None:
        document = _minimal_valid_document()
        document["metadata"] = "2026-04-27"
        errors = validate(document)
        assert "metadata: must be an object" in errors

    @pytest.mark.parametrize("bad_date", ["2026/04/27", "27-04-2026", "2026-4-27", "today", ""])
    def test_interview_date_must_be_iso(self, bad_date: str) -> None:
        document = _minimal_valid_document()
        document["metadata"]["interview_date"] = bad_date
        errors = validate(document)
        assert any("metadata.interview_date" in error for error in errors)

    def test_interview_status_must_be_allowed(self) -> None:
        document = _minimal_valid_document()
        document["metadata"]["interview_status"] = "draft"
        errors = validate(document)
        assert any("metadata.interview_status" in error for error in errors)

    def test_completed_layers_must_be_list(self) -> None:
        document = _minimal_valid_document()
        document["metadata"]["completed_layers"] = "rhythms"
        errors = validate(document)
        assert "metadata.completed_layers: must be a list" in errors

    def test_unknown_layer_rejected(self) -> None:
        document = _minimal_valid_document()
        document["metadata"]["completed_layers"] = ["rhythms", "vibes"]
        errors = validate(document)
        assert any("vibes" in error for error in errors)


class TestLoadDocument:
    """Tests for load_document helper."""

    def test_load_from_file(self, tmp_path: Path) -> None:
        target = tmp_path / "model.json"
        target.write_text(json.dumps(_minimal_valid_document()))
        document = load_document(str(target))
        assert document["team"]["name"] == "Platform"

    def test_load_from_stdin(self) -> None:
        payload = json.dumps(_minimal_valid_document())
        with patch("sys.stdin", io.StringIO(payload)):
            document = load_document("-")
        assert document["schema_version"] == "1.0.0"

    def test_load_missing_file_raises(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            load_document(str(tmp_path / "missing.json"))

    def test_load_invalid_json_raises(self, tmp_path: Path) -> None:
        target = tmp_path / "bad.json"
        target.write_text("{not json")
        with pytest.raises(json.JSONDecodeError):
            load_document(str(target))


class TestMainCLI:
    """Tests for main CLI entry point."""

    def test_main_passes_for_valid_document(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        target = tmp_path / "model.json"
        target.write_text(json.dumps(_minimal_valid_document()))
        rc = main([str(target)])
        captured = capsys.readouterr()
        assert rc == 0
        assert "ok" in captured.out

    def test_main_fails_for_invalid_document(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        target = tmp_path / "model.json"
        bad = _minimal_valid_document()
        del bad["team"]
        target.write_text(json.dumps(bad))
        rc = main([str(target)])
        captured = capsys.readouterr()
        assert rc == 1
        assert "team" in captured.err

    def test_main_returns_2_for_missing_file(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        rc = main([str(tmp_path / "missing.json")])
        captured = capsys.readouterr()
        assert rc == 2
        assert "file not found" in captured.err

    def test_main_returns_1_for_invalid_json(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        target = tmp_path / "bad.json"
        target.write_text("{not json")
        rc = main([str(target)])
        captured = capsys.readouterr()
        assert rc == 1
        assert "invalid JSON" in captured.err

    def test_main_no_args_exits_2(self, capsys: pytest.CaptureFixture[str]) -> None:
        with pytest.raises(SystemExit) as excinfo:
            main([])
        assert excinfo.value.code == 2

    def test_main_reads_stdin(self, capsys: pytest.CaptureFixture[str]) -> None:
        payload = json.dumps(_minimal_valid_document())
        with patch("sys.stdin", io.StringIO(payload)):
            rc = main(["-"])
        captured = capsys.readouterr()
        assert rc == 0
        assert "ok" in captured.out


class TestRoundTripFullDocument:
    """Tests that a richer, populated document validates."""

    def test_populated_document_passes(self) -> None:
        document = deepcopy(_minimal_valid_document())
        document["team"] = {"name": "Platform", "scope": "billing", "size": 8}
        document["rhythms"]["cadences"] = [
            {
                "name": "standup",
                "frequency": "daily",
                "owner": "tech lead",
                "purpose": "sync blockers",
                "source": "documented",
            },
        ]
        document["decisions"]["decision_rights"] = [
            {
                "decision_type": "architecture",
                "decider": "principal eng",
                "informed": ["product", "platform"],
                "formality": "formal",
                "source": "documented",
            },
        ]
        document["dependencies"]["upstream"] = [
            {"name": "auth-svc", "role": "identity", "criticality": "high", "source": "documented"},
        ]
        document["dependencies"]["downstream"] = [
            {"name": "billing-ui", "role": "consumer", "criticality": "medium", "source": "tacit"},
        ]
        document["institutional_knowledge"]["tacit"] = [
            {"topic": "fallback billing path", "owner": "alex", "documentation_status": "none"},
        ]
        document["friction"]["blockers"] = [
            {"description": "slow ci", "impact": "high", "category": "tooling"},
        ]
        document["metadata"]["skipped_layers"] = []
        document["metadata"]["revisions"] = [
            {"date": "2026-04-27", "section": "decisions", "note": "revised after Q2 reorg"},
        ]
        assert validate(document) == []
