"""Tests for scripts.memory_enhancement.reflection module."""

from __future__ import annotations

import json

import pytest

from scripts.memory_enhancement.reflection import (
    DECAY_PENALTY,
    REINFORCE_BOOST,
    ReflectionResult,
    SessionFact,
    SkillCandidate,
    decay_unverified_memories,
    extract_session_facts,
    generate_skill_candidates,
    main,
    reinforce_memories,
    run_reflection,
    save_skill_candidates,
)


class TestReinforceMemories:
    """Tests for reinforce_memories function."""

    @pytest.mark.unit
    def test_reinforces_accessed_on_success(self):
        result = reinforce_memories(["mem-1", "mem-2"], ["task completed"])
        assert len(result) == 2
        assert result[0] == ("mem-1", REINFORCE_BOOST)
        assert result[1] == ("mem-2", REINFORCE_BOOST)

    @pytest.mark.unit
    def test_no_reinforcement_without_successes(self):
        result = reinforce_memories(["mem-1", "mem-2"], [])
        assert result == []

    @pytest.mark.unit
    def test_empty_accessed_memories(self):
        result = reinforce_memories([], ["task completed"])
        assert result == []

    @pytest.mark.unit
    def test_skips_empty_memory_ids(self):
        result = reinforce_memories(["mem-1", "", "mem-3"], ["success"])
        assert len(result) == 2
        ids = [r[0] for r in result]
        assert "" not in ids

    @pytest.mark.unit
    def test_both_empty(self):
        result = reinforce_memories([], [])
        assert result == []


class TestGenerateSkillCandidates:
    """Tests for generate_skill_candidates function."""

    @pytest.mark.unit
    def test_clusters_similar_failures(self):
        failures = [
            "import error in module X",
            "import error in module Y",
        ]
        result = generate_skill_candidates(failures, "session-1")
        assert len(result) == 1
        assert result[0].governance_gate is True
        assert result[0].session_id == "session-1"
        assert len(result[0].source_failures) == 2

    @pytest.mark.unit
    def test_no_candidates_below_threshold(self):
        failures = ["unique error A", "different problem B"]
        result = generate_skill_candidates(failures, "session-1")
        assert result == []

    @pytest.mark.unit
    def test_empty_failures(self):
        result = generate_skill_candidates([], "session-1")
        assert result == []

    @pytest.mark.unit
    def test_skips_blank_failures(self):
        failures = ["", "  ", "import error once"]
        result = generate_skill_candidates(failures, "session-1")
        assert result == []

    @pytest.mark.unit
    def test_candidate_name_format(self):
        failures = ["test failure reason", "test failure reason"]
        result = generate_skill_candidates(failures, "s1")
        assert len(result) == 1
        assert result[0].name.startswith("skill-candidate-")
        assert " " not in result[0].name

    @pytest.mark.unit
    def test_multiple_clusters(self):
        failures = [
            "import error A",
            "import error B",
            "timeout waiting for X",
            "timeout waiting for Y",
        ]
        result = generate_skill_candidates(failures, "s1")
        assert len(result) == 2

    @pytest.mark.unit
    def test_serialization(self):
        failures = ["test fail 1", "test fail 2"]
        candidates = generate_skill_candidates(failures, "s1")
        assert len(candidates) == 1
        d = candidates[0].to_dict()
        assert "name" in d
        assert "governance_gate" in d
        assert d["governance_gate"] is True


class TestExtractSessionFacts:
    """Tests for extract_session_facts function."""

    @pytest.mark.unit
    def test_extracts_string_decisions(self):
        log = {"decisions": ["Use pattern X", "Avoid approach Y"]}
        facts = extract_session_facts(log, "s1")
        decision_facts = [f for f in facts if f.key == "decision"]
        assert len(decision_facts) == 2
        assert decision_facts[0].value == "Use pattern X"
        assert decision_facts[0].session_id == "s1"

    @pytest.mark.unit
    def test_extracts_dict_decisions(self):
        log = {"decisions": [{"description": "Chose strategy A"}]}
        facts = extract_session_facts(log, "s1")
        assert len(facts) == 1
        assert facts[0].value == "Chose strategy A"

    @pytest.mark.unit
    def test_extracts_tools_used(self):
        log = {"tools_used": ["grep", "read", "edit"]}
        facts = extract_session_facts(log, "s1")
        tool_facts = [f for f in facts if f.key == "tools_used"]
        assert len(tool_facts) == 1
        assert "grep" in tool_facts[0].value

    @pytest.mark.unit
    def test_extracts_outcome(self):
        log = {"outcome": "PR created successfully"}
        facts = extract_session_facts(log, "s1")
        outcome_facts = [f for f in facts if f.key == "outcome"]
        assert len(outcome_facts) == 1
        assert outcome_facts[0].confidence == 0.8

    @pytest.mark.unit
    def test_empty_session_log(self):
        facts = extract_session_facts({}, "s1")
        assert facts == []

    @pytest.mark.unit
    def test_skips_empty_strings(self):
        log = {"decisions": ["", "  "], "outcome": ""}
        facts = extract_session_facts(log, "s1")
        assert facts == []

    @pytest.mark.unit
    def test_fact_serialization(self):
        fact = SessionFact(key="test", value="val", session_id="s1")
        d = fact.to_dict()
        assert d["key"] == "test"
        assert d["session_id"] == "s1"


class TestDecayUnverifiedMemories:
    """Tests for decay_unverified_memories function."""

    @pytest.mark.unit
    def test_decays_unverified(self):
        result = decay_unverified_memories(
            ["mem-1", "mem-2", "mem-3"],
            ["mem-2"],
        )
        assert len(result) == 2
        ids = [r[0] for r in result]
        assert "mem-1" in ids
        assert "mem-3" in ids
        assert all(r[1] == DECAY_PENALTY for r in result)

    @pytest.mark.unit
    def test_no_decay_all_verified(self):
        result = decay_unverified_memories(["mem-1"], ["mem-1"])
        assert result == []

    @pytest.mark.unit
    def test_all_decayed_no_verified(self):
        result = decay_unverified_memories(["mem-1", "mem-2"], None)
        assert len(result) == 2

    @pytest.mark.unit
    def test_empty_accessed(self):
        result = decay_unverified_memories([], ["mem-1"])
        assert result == []

    @pytest.mark.unit
    def test_skips_empty_ids(self):
        result = decay_unverified_memories(["", "mem-1"], None)
        assert len(result) == 1
        assert result[0][0] == "mem-1"


class TestRunReflection:
    """Tests for run_reflection orchestrator function."""

    @pytest.mark.unit
    def test_full_reflection(self):
        session_log = {
            "accessed_memories": ["mem-1", "mem-2"],
            "successes": ["task completed"],
            "failures": [
                "import error A",
                "import error B",
            ],
            "verified_memories": ["mem-1"],
            "decisions": ["Used pattern X"],
            "outcome": "Done",
        }
        result = run_reflection(session_log, "session-1")
        assert isinstance(result, ReflectionResult)
        assert result.reinforced_count == 2
        assert len(result.skill_candidates) == 1
        assert len(result.facts_captured) >= 1
        assert result.decayed_count == 1

    @pytest.mark.unit
    def test_empty_session_log(self):
        result = run_reflection({}, "session-empty")
        assert result.reinforced_count == 0
        assert result.skill_candidates == []
        assert result.facts_captured == []
        assert result.decayed_count == 0


class TestSaveSkillCandidates:
    """Tests for save_skill_candidates function."""

    @pytest.mark.unit
    def test_saves_candidates_as_json(self, tmp_path):
        candidates = [
            SkillCandidate(
                name="skill-candidate-test",
                description="Test candidate",
                source_failures=["fail1", "fail2"],
                session_id="s1",
            )
        ]
        saved = save_skill_candidates(candidates, tmp_path / "candidates")
        assert len(saved) == 1
        assert saved[0].exists()
        data = json.loads(saved[0].read_text(encoding="utf-8"))
        assert data["name"] == "skill-candidate-test"
        assert data["governance_gate"] is True

    @pytest.mark.unit
    def test_creates_output_dir(self, tmp_path):
        target = tmp_path / "new" / "dir"
        save_skill_candidates([], target)
        assert target.is_dir()

    @pytest.mark.unit
    def test_empty_candidates(self, tmp_path):
        saved = save_skill_candidates([], tmp_path / "empty")
        assert saved == []


class TestMainCli:
    """Tests for main() CLI entry point."""

    @pytest.mark.unit
    def test_missing_args(self, capsys):
        code = main([])
        assert code == 1
        captured = capsys.readouterr()
        assert "Usage" in captured.err

    @pytest.mark.unit
    def test_missing_file(self, capsys):
        code = main(["/nonexistent/session.json"])
        assert code == 1
        captured = capsys.readouterr()
        assert "not found" in captured.err

    @pytest.mark.unit
    def test_invalid_json(self, tmp_path, capsys):
        bad_file = tmp_path / "bad.json"
        bad_file.write_text("not json", encoding="utf-8")
        code = main([str(bad_file)])
        assert code == 1
        captured = capsys.readouterr()
        assert "Failed to read" in captured.err

    @pytest.mark.unit
    def test_valid_session(self, tmp_path, capsys):
        session_file = tmp_path / "session.json"
        # Create a .git marker so _find_project_root works
        (tmp_path / ".git").mkdir()
        session_log = {
            "session_id": "test-session",
            "accessed_memories": ["mem-1"],
            "successes": ["done"],
            "failures": [],
            "decisions": ["chose X"],
        }
        session_file.write_text(
            json.dumps(session_log), encoding="utf-8"
        )
        code = main([str(session_file)])
        assert code == 0
        captured = capsys.readouterr()
        assert "Reflection:" in captured.err
