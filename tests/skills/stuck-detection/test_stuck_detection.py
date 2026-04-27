#!/usr/bin/env python3
"""Tests for stuck_detection module."""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest

TESTS_SKILLS_DIR = str(Path(__file__).resolve().parents[1])
if TESTS_SKILLS_DIR not in sys.path:
    sys.path.insert(0, TESTS_SKILLS_DIR)

from claude_skills_import import import_skill_script

mod = import_skill_script(".claude/skills/stuck-detection/stuck_detection.py")
extract_topic_signature = mod.extract_topic_signature
jaccard_similarity = mod.jaccard_similarity
check_stuck = mod.check_stuck
reset_history = mod.reset_history
get_status = mod.get_status
default_history_path = mod.default_history_path
build_nudge = mod.build_nudge
main = mod.main


@pytest.fixture
def history_path(tmp_path: Path) -> Path:
    return tmp_path / "history.json"


class TestExtractTopicSignature:
    """Tests for extract_topic_signature."""

    def test_returns_none_for_empty_text(self) -> None:
        assert extract_topic_signature("") is None

    def test_returns_none_for_short_text(self) -> None:
        assert extract_topic_signature("too short") is None

    def test_extracts_significant_words(self) -> None:
        text = (
            "The deployment pipeline failed during the canary rollout. "
            "Pipeline errors keep blocking the deployment retries today."
        )
        sig = extract_topic_signature(text)
        assert sig is not None
        words = sig.split(",")
        assert "pipeline" in words
        assert "deployment" in words

    def test_signature_is_sorted(self) -> None:
        text = (
            "Pipeline pipeline pipeline build build deploy deploy retries failure retry "
            "and the deployment of the build pipeline failed today loud."
        )
        sig = extract_topic_signature(text)
        assert sig is not None
        words = sig.split(",")
        assert words == sorted(words)

    def test_filters_stop_words(self) -> None:
        text = (
            "The and but for are was were been being have has had does did "
            "this that these those with from your what which who whom please "
            "actually genuine concrete concrete concrete distinct."
        )
        sig = extract_topic_signature(text)
        assert sig is not None
        for stop in ("with", "from", "your", "what"):
            assert stop not in sig.split(",")

    def test_returns_none_when_too_few_significant_words(self) -> None:
        text = "the the the the the the the the the the the the the and and and"
        assert extract_topic_signature(text) is None


class TestJaccardSimilarity:
    """Tests for jaccard_similarity."""

    def test_identical_signatures(self) -> None:
        assert jaccard_similarity("a,b,c", "a,b,c") == 1.0

    def test_disjoint_signatures(self) -> None:
        assert jaccard_similarity("a,b,c", "x,y,z") == 0.0

    def test_partial_overlap(self) -> None:
        result = jaccard_similarity("a,b,c", "b,c,d")
        assert result == pytest.approx(2 / 4)

    def test_empty_signatures(self) -> None:
        assert jaccard_similarity("", "") == 0.0


class TestCheckStuck:
    """Tests for check_stuck."""

    def _generate_text(self, theme: str) -> str:
        return (
            f"The {theme} pipeline failed during the {theme} canary rollout. "
            f"{theme.capitalize()} errors keep blocking the {theme} retries today."
        )

    def test_warming_up_returns_not_stuck(self, history_path: Path) -> None:
        result = check_stuck(self._generate_text("deployment"), history_path)
        assert result["stuck"] is False
        assert result["reason"] == "warming-up"

    def test_no_signature_returns_not_stuck(self, history_path: Path) -> None:
        result = check_stuck("short", history_path)
        assert result["stuck"] is False
        assert result["signature"] is None

    def test_three_similar_turns_trigger_stuck(self, history_path: Path) -> None:
        text = self._generate_text("deployment")
        check_stuck(text, history_path)
        check_stuck(text, history_path)
        result = check_stuck(text, history_path)
        assert result["stuck"] is True
        assert "nudge" in result
        assert "<stuck-detection>" in result["nudge"]

    def test_topic_change_does_not_trigger(self, history_path: Path) -> None:
        check_stuck(
            "Deployment pipeline collapsed when canary rollout exceeded "
            "queue capacity overnight during the regional failover drill.",
            history_path,
        )
        check_stuck(
            "Authentication tokens expire too aggressively. Refresh handler "
            "loops on stale cookies and signs users out unexpectedly midsession.",
            history_path,
        )
        result = check_stuck(
            "Inventory reconciliation found duplicate SKUs across warehouses "
            "after the partner integration imported overlapping vendor catalogs.",
            history_path,
        )
        assert result["stuck"] is False

    def test_history_is_persisted(self, history_path: Path) -> None:
        check_stuck(self._generate_text("payment"), history_path)
        assert history_path.exists()
        data = json.loads(history_path.read_text())
        assert len(data) == 1
        assert "signature" in data[0]
        assert "timestamp" in data[0]

    def test_history_trims_to_max(self, history_path: Path) -> None:
        for i in range(15):
            check_stuck(self._generate_text(f"theme{i}"), history_path)
        data = json.loads(history_path.read_text())
        assert len(data) <= 10

    def test_threshold_override(self, history_path: Path) -> None:
        text = self._generate_text("queue")
        check_stuck(text, history_path, stuck_threshold=2)
        result = check_stuck(text, history_path, stuck_threshold=2)
        assert result["stuck"] is True

    def test_now_parameter_used(self, history_path: Path) -> None:
        fixed = datetime(2026, 1, 1, tzinfo=UTC)
        check_stuck(self._generate_text("storage"), history_path, now=fixed)
        data = json.loads(history_path.read_text())
        assert data[0]["timestamp"] == fixed.isoformat()


class TestLoadHistorySchema:
    """Schema-validation tests for load_history."""

    def _write(self, path: Path, content: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    def test_dict_payload_returns_empty(self, history_path: Path) -> None:
        from claude_skills_import import import_skill_script
        load_history = import_skill_script(
            ".claude/skills/stuck-detection/stuck_detection.py"
        ).load_history
        self._write(history_path, '{"signature": "a,b", "timestamp": "t"}')
        assert load_history(history_path) == []

    def test_non_dict_entries_returns_empty(self, history_path: Path) -> None:
        from claude_skills_import import import_skill_script
        load_history = import_skill_script(
            ".claude/skills/stuck-detection/stuck_detection.py"
        ).load_history
        self._write(history_path, '["just a string"]')
        assert load_history(history_path) == []

    def test_missing_keys_returns_empty(self, history_path: Path) -> None:
        from claude_skills_import import import_skill_script
        load_history = import_skill_script(
            ".claude/skills/stuck-detection/stuck_detection.py"
        ).load_history
        self._write(history_path, '[{"signature": "a,b"}]')
        assert load_history(history_path) == []

    def test_non_string_values_returns_empty(self, history_path: Path) -> None:
        from claude_skills_import import import_skill_script
        load_history = import_skill_script(
            ".claude/skills/stuck-detection/stuck_detection.py"
        ).load_history
        self._write(history_path, '[{"signature": 1, "timestamp": "t"}]')
        assert load_history(history_path) == []

    def test_corrupt_history_does_not_propagate(self, history_path: Path) -> None:
        text = (
            "Deployment pipeline collapsed when canary rollout exceeded queue "
            "capacity overnight during the regional failover drill."
        )
        self._write(history_path, '{"corrupt": true}')
        result = check_stuck(text, history_path)
        assert result["stuck"] is False
        assert result.get("reason") == "warming-up"


class TestSaveHistoryAtomicity:
    """Verify save_history leaves no partial files behind."""

    def test_no_temp_files_after_write(self, history_path: Path) -> None:
        from claude_skills_import import import_skill_script
        save_history = import_skill_script(
            ".claude/skills/stuck-detection/stuck_detection.py"
        ).save_history
        save_history(history_path, [{"signature": "a", "timestamp": "t"}], 10)
        leftovers = [p for p in history_path.parent.iterdir() if ".tmp" in p.name]
        assert leftovers == []

    def test_overwrite_preserves_prior_on_replace(self, history_path: Path) -> None:
        from claude_skills_import import import_skill_script
        save_history = import_skill_script(
            ".claude/skills/stuck-detection/stuck_detection.py"
        ).save_history
        save_history(history_path, [{"signature": "a", "timestamp": "t"}], 10)
        save_history(history_path, [{"signature": "b", "timestamp": "t"}], 10)
        data = json.loads(history_path.read_text())
        assert data == [{"signature": "b", "timestamp": "t"}]


class TestCheckStuckArgValidation:
    """check_stuck must reject incoherent threshold/max_history combinations."""

    def test_max_history_below_threshold_raises(self, history_path: Path) -> None:
        text = (
            "Deployment pipeline collapsed when canary rollout exceeded queue "
            "capacity overnight during the regional failover drill."
        )
        with pytest.raises(ValueError, match="max_history"):
            check_stuck(text, history_path, stuck_threshold=5, max_history=3)


class TestResetHistory:
    """Tests for reset_history."""

    def test_reset_clears_existing(self, history_path: Path) -> None:
        history_path.parent.mkdir(parents=True, exist_ok=True)
        history_path.write_text(json.dumps([{"signature": "a,b", "timestamp": "t"}]))
        result = reset_history(history_path)
        assert result == {"reset": True}
        assert json.loads(history_path.read_text()) == []

    def test_reset_creates_file_if_missing(self, history_path: Path) -> None:
        reset_history(history_path)
        assert history_path.exists()


class TestGetStatus:
    """Tests for get_status."""

    def test_status_empty_history(self, history_path: Path) -> None:
        status = get_status(history_path)
        assert status["history_length"] == 0
        assert status["recent_signatures"] == []

    def test_status_recent_signatures(self, history_path: Path) -> None:
        history_path.parent.mkdir(parents=True, exist_ok=True)
        entries = [{"signature": f"sig{i}", "timestamp": "t"} for i in range(5)]
        history_path.write_text(json.dumps(entries))
        status = get_status(history_path)
        assert status["history_length"] == 5
        assert status["recent_signatures"] == ["sig2", "sig3", "sig4"]


class TestDefaultHistoryPath:
    """Tests for default_history_path resolution."""

    def test_env_override(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        target = tmp_path / "custom.json"
        monkeypatch.setenv("STUCK_DETECTION_HISTORY", str(target))
        assert default_history_path() == target

    def test_xdg_state_home(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        monkeypatch.delenv("STUCK_DETECTION_HISTORY", raising=False)
        monkeypatch.delenv("STUCK_DETECTION_SESSION", raising=False)
        monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
        result = default_history_path()
        assert result == tmp_path / "claude-stuck-detection" / "history.json"

    def test_session_scoped_path(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.delenv("STUCK_DETECTION_HISTORY", raising=False)
        monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
        monkeypatch.setenv("STUCK_DETECTION_SESSION", "session-A/42")
        result = default_history_path()
        assert result == tmp_path / "claude-stuck-detection" / "history-session-A_42.json"

    def test_home_fallback(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("STUCK_DETECTION_HISTORY", raising=False)
        monkeypatch.delenv("STUCK_DETECTION_SESSION", raising=False)
        monkeypatch.delenv("XDG_STATE_HOME", raising=False)
        result = default_history_path()
        assert ".local/state/claude-stuck-detection/history.json" in str(result)


class TestBuildNudge:
    """Tests for build_nudge."""

    def test_nudge_contains_words(self) -> None:
        nudge = build_nudge("deploy,error,pipeline")
        assert "deploy" in nudge
        assert "error" in nudge
        assert "pipeline" in nudge
        assert "<stuck-detection>" in nudge
        assert "</stuck-detection>" in nudge

    def test_nudge_no_personal_names(self) -> None:
        """Nudge must not leak the contributor's personal config."""
        nudge = build_nudge("a,b,c")
        assert "Richard" not in nudge
        assert "OpenClaw" not in nudge


class TestMain:
    """Tests for main CLI entry point."""

    def test_check_command(
        self, capsys: pytest.CaptureFixture[str], history_path: Path
    ) -> None:
        text = (
            "The deployment pipeline failed during the canary rollout. "
            "Pipeline errors keep blocking the deployment retries today."
        )
        exit_code = main(["--history", str(history_path), "check", text])
        assert exit_code == 0
        captured = capsys.readouterr()
        result = json.loads(captured.out)
        assert "stuck" in result
        assert "signature" in result

    def test_status_command(
        self, capsys: pytest.CaptureFixture[str], history_path: Path
    ) -> None:
        exit_code = main(["--history", str(history_path), "status"])
        assert exit_code == 0
        captured = capsys.readouterr()
        result = json.loads(captured.out)
        assert result["history_length"] == 0

    def test_reset_command(
        self, capsys: pytest.CaptureFixture[str], history_path: Path
    ) -> None:
        exit_code = main(["--history", str(history_path), "reset"])
        assert exit_code == 0
        captured = capsys.readouterr()
        assert json.loads(captured.out) == {"reset": True}

    def test_extract_command(
        self, capsys: pytest.CaptureFixture[str], history_path: Path
    ) -> None:
        text = (
            "The deployment pipeline failed during the canary rollout. "
            "Pipeline errors keep blocking the deployment retries today."
        )
        exit_code = main(["--history", str(history_path), "extract", text])
        assert exit_code == 0
        captured = capsys.readouterr()
        assert "pipeline" in captured.out

    def test_missing_command_errors(self) -> None:
        with pytest.raises(SystemExit) as excinfo:
            main([])
        assert excinfo.value.code == 2
