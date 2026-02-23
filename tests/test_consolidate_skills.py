"""Tests for scripts/consolidate_skills.py."""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

from scripts.consolidate_skills import (
    ConsolidationConfig,
    ConsolidationReport,
    PatternOccurrence,
    PatternStats,
    SkillCandidate,
    build_skill_title,
    check_duplicates,
    classify_category,
    consolidate,
    extract_actions,
    find_patterns,
    generate_skill_id,
    infer_success,
    load_existing_skill_titles,
    load_sessions,
    normalize_action,
    render_skill_markdown,
    write_skills,
)


class TestNormalizeAction:
    def test_strips_sha_hashes(self) -> None:
        result = normalize_action("Committed abc1234 to branch")
        assert "<sha>" in result
        assert "abc1234" not in result

    def test_strips_issue_numbers(self) -> None:
        result = normalize_action("Fixed #123 and #456")
        assert "<issue>" in result
        assert "#123" not in result

    def test_strips_file_paths(self) -> None:
        result = normalize_action("Updated scripts/foo.py with changes")
        assert "<path>" in result
        assert "scripts/foo.py" not in result

    def test_strips_dates(self) -> None:
        result = normalize_action("Session on 2026-02-20 completed")
        assert "<date>" in result
        assert "2026-02-20" not in result

    def test_strips_session_references(self) -> None:
        result = normalize_action("Created session-5 log")
        assert "<session>" in result

    def test_collapses_whitespace(self) -> None:
        result = normalize_action("  multiple   spaces   here  ")
        assert "  " not in result

    def test_lowercases(self) -> None:
        result = normalize_action("UPPER Case Text")
        assert result == "upper case text"


class TestClassifyCategory:
    def test_security_keywords(self) -> None:
        assert classify_category("Run security scan") == "security"
        assert classify_category("CWE-78 detected") == "security"

    def test_testing_keywords(self) -> None:
        assert classify_category("Run pytest suite") == "testing"
        assert classify_category("Check test coverage") == "testing"

    def test_git_keywords(self) -> None:
        assert classify_category("Commit changes to branch") == "git-operations"

    def test_default_category(self) -> None:
        assert classify_category("Something unrelated entirely") == "general"


class TestInferSuccess:
    def test_explicit_failed_status(self) -> None:
        assert infer_success({"status": "failed"}) is False

    def test_explicit_error_status(self) -> None:
        assert infer_success({"status": "error"}) is False

    def test_no_status_defaults_success(self) -> None:
        assert infer_success({}) is True

    def test_incomplete_must_items(self) -> None:
        session = {
            "protocolCompliance": {
                "sessionEnd": {
                    "checklistComplete": {
                        "level": "MUST",
                        "Complete": False,
                    }
                }
            }
        }
        assert infer_success(session) is False

    def test_complete_must_items(self) -> None:
        session = {
            "protocolCompliance": {
                "sessionEnd": {
                    "checklistComplete": {
                        "level": "MUST",
                        "Complete": True,
                    }
                }
            }
        }
        assert infer_success(session) is True

    def test_failure_in_outcomes(self) -> None:
        session = {"outcomes": ["Task completed", "Build failed with errors"]}
        assert infer_success(session) is False

    def test_success_in_outcomes(self) -> None:
        session = {"outcomes": ["All tasks completed", "PR merged"]}
        assert infer_success(session) is True


class TestExtractActions:
    def test_extracts_from_work_log(self) -> None:
        session = {
            "workLog": [
                {"action": "Created new script"},
                {"action": "Updated tests"},
            ]
        }
        actions = extract_actions(session)
        assert actions == ["Created new script", "Updated tests"]

    def test_extracts_from_work_key(self) -> None:
        session = {"work": [{"action": "Fixed bug"}]}
        actions = extract_actions(session)
        assert actions == ["Fixed bug"]

    def test_extracts_from_agent_activities(self) -> None:
        session = {
            "agentActivities": [
                {"agent": "security", "action": "Scanned for CWE-78"},
            ]
        }
        actions = extract_actions(session)
        assert actions == ["security: Scanned for CWE-78"]

    def test_skips_empty_actions(self) -> None:
        session = {"workLog": [{"action": ""}, {"action": "  "}]}
        actions = extract_actions(session)
        assert actions == []

    def test_empty_session(self) -> None:
        assert extract_actions({}) == []


class TestPatternStats:
    def test_use_count(self) -> None:
        stats = PatternStats(
            normalized="test",
            category="general",
            occurrences=[
                PatternOccurrence("2026-01-01", "s1.json", "test", True),
                PatternOccurrence("2026-01-02", "s2.json", "test", False),
            ],
        )
        assert stats.use_count == 2

    def test_success_rate(self) -> None:
        stats = PatternStats(
            normalized="test",
            category="general",
            occurrences=[
                PatternOccurrence("2026-01-01", "s1.json", "test", True),
                PatternOccurrence("2026-01-02", "s2.json", "test", True),
                PatternOccurrence("2026-01-03", "s3.json", "test", False),
            ],
        )
        assert abs(stats.success_rate - 2 / 3) < 0.001

    def test_success_rate_empty(self) -> None:
        stats = PatternStats(normalized="test", category="general")
        assert stats.success_rate == 0.0

    def test_meets_criteria(self) -> None:
        config = ConsolidationConfig(min_uses=2, min_success_rate=0.50)
        stats = PatternStats(
            normalized="test",
            category="general",
            occurrences=[
                PatternOccurrence("2026-01-01", "s1.json", "test", True),
                PatternOccurrence("2026-01-02", "s2.json", "test", True),
            ],
        )
        assert stats.meets_criteria(config) is True

    def test_does_not_meet_criteria_uses(self) -> None:
        config = ConsolidationConfig(min_uses=3, min_success_rate=0.50)
        stats = PatternStats(
            normalized="test",
            category="general",
            occurrences=[
                PatternOccurrence("2026-01-01", "s1.json", "test", True),
            ],
        )
        assert stats.meets_criteria(config) is False

    def test_does_not_meet_criteria_rate(self) -> None:
        config = ConsolidationConfig(min_uses=2, min_success_rate=0.80)
        stats = PatternStats(
            normalized="test",
            category="general",
            occurrences=[
                PatternOccurrence("2026-01-01", "s1.json", "test", True),
                PatternOccurrence("2026-01-02", "s2.json", "test", False),
                PatternOccurrence("2026-01-03", "s3.json", "test", False),
            ],
        )
        assert stats.meets_criteria(config) is False


class TestLoadSessions:
    def test_loads_recent_sessions(self, tmp_path: Path) -> None:
        today = datetime.now(UTC).strftime("%Y-%m-%d")
        session = {
            "session": {"date": today, "number": 1, "branch": "main",
                        "startingCommit": "abc", "objective": "test"},
            "workLog": [{"action": "Did something"}],
        }
        (tmp_path / f"{today}-session-1.json").write_text(json.dumps(session))

        cutoff = datetime.now(UTC) - timedelta(days=7)
        results = load_sessions(tmp_path, cutoff)
        assert len(results) == 1

    def test_skips_old_sessions(self, tmp_path: Path) -> None:
        old_date = (datetime.now(UTC) - timedelta(days=30)).strftime("%Y-%m-%d")
        session = {"session": {"date": old_date}}
        (tmp_path / f"{old_date}-session-1.json").write_text(json.dumps(session))

        cutoff = datetime.now(UTC) - timedelta(days=7)
        results = load_sessions(tmp_path, cutoff)
        assert len(results) == 0

    def test_skips_malformed_json(self, tmp_path: Path) -> None:
        (tmp_path / "bad.json").write_text("not json")
        cutoff = datetime.now(UTC) - timedelta(days=7)
        results = load_sessions(tmp_path, cutoff)
        assert len(results) == 0

    def test_empty_dir(self, tmp_path: Path) -> None:
        cutoff = datetime.now(UTC) - timedelta(days=7)
        results = load_sessions(tmp_path, cutoff)
        assert len(results) == 0

    def test_nonexistent_dir(self) -> None:
        cutoff = datetime.now(UTC) - timedelta(days=7)
        results = load_sessions(Path("/nonexistent"), cutoff)
        assert len(results) == 0


class TestFindPatterns:
    def test_aggregates_identical_patterns(self) -> None:
        sessions = [
            (
                {
                    "session": {"date": "2026-02-20"},
                    "workLog": [{"action": "Run pytest suite"}],
                },
                "s1.json",
            ),
            (
                {
                    "session": {"date": "2026-02-21"},
                    "workLog": [{"action": "Run pytest suite"}],
                },
                "s2.json",
            ),
        ]
        patterns = find_patterns(sessions)
        # Both should normalize to the same key
        assert len(patterns) >= 1
        for stats in patterns.values():
            if "pytest" in stats.normalized:
                assert stats.use_count == 2

    def test_skips_short_actions(self) -> None:
        sessions = [
            ({"session": {"date": "2026-02-20"}, "workLog": [{"action": "hi"}]}, "s1.json"),
        ]
        patterns = find_patterns(sessions)
        assert len(patterns) == 0


class TestLoadExistingSkillTitles:
    def test_extracts_titles_from_markdown(self, tmp_path: Path) -> None:
        (tmp_path / "skill.md").write_text("# Skill: Run Security Scans\n\nContent here.")
        titles = load_existing_skill_titles(tmp_path)
        assert "skill: run security scans" in titles

    def test_handles_subdirectories(self, tmp_path: Path) -> None:
        subdir = tmp_path / "security"
        subdir.mkdir()
        (subdir / "skill.md").write_text("# Deep Skill Title\n")
        titles = load_existing_skill_titles(subdir.parent)
        assert "deep skill title" in titles

    def test_empty_dir(self, tmp_path: Path) -> None:
        titles = load_existing_skill_titles(tmp_path)
        assert len(titles) == 0

    def test_nonexistent_dir(self) -> None:
        titles = load_existing_skill_titles(Path("/nonexistent"))
        assert len(titles) == 0


class TestGenerateSkillId:
    def test_generates_unique_ids(self) -> None:
        used: set[str] = set()
        id1 = generate_skill_id("security", used)
        id2 = generate_skill_id("security", used)
        assert id1 != id2
        assert id1.startswith("Skill-Security-")
        assert id2.startswith("Skill-Security-")

    def test_starts_at_001(self) -> None:
        used: set[str] = set()
        skill_id = generate_skill_id("testing", used)
        assert skill_id == "Skill-Testing-001"


class TestBuildSkillTitle:
    def test_removes_placeholders(self) -> None:
        stats = PatternStats(normalized="updated <path> with <sha>", category="general")
        title = build_skill_title(stats)
        assert "<path>" not in title
        assert "<sha>" not in title

    def test_truncates_long_titles(self) -> None:
        stats = PatternStats(normalized="a" * 100, category="general")
        title = build_skill_title(stats)
        assert len(title) <= 80


class TestCheckDuplicates:
    def test_exact_match(self) -> None:
        result = check_duplicates("run security scans", {"run security scans"})
        assert result == "run security scans"

    def test_no_match(self) -> None:
        result = check_duplicates("totally new skill", {"existing skill"})
        assert result is None

    def test_substring_match(self) -> None:
        result = check_duplicates(
            "run security scans for cwe detection",
            {"run security scans for cwe"},
        )
        # Both > 15 chars and one contains the other
        assert result is not None

    def test_short_strings_no_substring_match(self) -> None:
        result = check_duplicates("short", {"shor"})
        assert result is None


class TestConsolidate:
    def test_full_pipeline(self, tmp_path: Path) -> None:
        sessions_dir = tmp_path / "sessions"
        sessions_dir.mkdir()
        memories_dir = tmp_path / "memories"
        memories_dir.mkdir()

        today = datetime.now(UTC).strftime("%Y-%m-%d")
        for i in range(4):
            session = {
                "session": {"date": today, "number": i + 1, "branch": "main",
                            "startingCommit": "abc", "objective": "test"},
                "workLog": [{"action": "Run the full pytest test suite"}],
                "outcomes": ["All tests passed"],
            }
            (sessions_dir / f"{today}-session-{i + 1}.json").write_text(
                json.dumps(session)
            )

        config = ConsolidationConfig(min_uses=3, min_success_rate=0.70, lookback_days=7)
        report = consolidate(sessions_dir, memories_dir, config)

        assert report.sessions_scanned == 4
        assert report.patterns_found >= 1
        assert len(report.candidates) >= 1
        assert report.candidates[0].pattern.use_count >= 3

    def test_no_sessions(self, tmp_path: Path) -> None:
        sessions_dir = tmp_path / "sessions"
        sessions_dir.mkdir()
        memories_dir = tmp_path / "memories"
        memories_dir.mkdir()

        config = ConsolidationConfig()
        report = consolidate(sessions_dir, memories_dir, config)
        assert report.sessions_scanned == 0
        assert len(report.candidates) == 0

    def test_below_threshold(self, tmp_path: Path) -> None:
        sessions_dir = tmp_path / "sessions"
        sessions_dir.mkdir()
        memories_dir = tmp_path / "memories"
        memories_dir.mkdir()

        today = datetime.now(UTC).strftime("%Y-%m-%d")
        # Only 1 session, below min_uses=3
        session = {
            "session": {"date": today, "number": 1, "branch": "main",
                        "startingCommit": "abc", "objective": "test"},
            "workLog": [{"action": "Run the full pytest test suite"}],
        }
        (sessions_dir / f"{today}-session-1.json").write_text(json.dumps(session))

        config = ConsolidationConfig(min_uses=3, min_success_rate=0.70, lookback_days=7)
        report = consolidate(sessions_dir, memories_dir, config)
        assert len(report.candidates) == 0


class TestRenderSkillMarkdown:
    def test_contains_key_sections(self) -> None:
        stats = PatternStats(
            normalized="run pytest test suite",
            category="testing",
            occurrences=[
                PatternOccurrence("2026-02-20", "s1.json", "Run pytest", True),
                PatternOccurrence("2026-02-21", "s2.json", "Run pytest", True),
                PatternOccurrence("2026-02-22", "s3.json", "Run pytest", True),
            ],
        )
        candidate = SkillCandidate(
            pattern=stats,
            skill_id="Skill-Testing-001",
            title="Run pytest test suite",
        )
        md = render_skill_markdown(candidate)
        assert "# Skill:" in md
        assert "## Statement" in md
        assert "## Context" in md
        assert "## Pattern" in md
        assert "## Evidence" in md
        assert "testing" in md
        assert "100%" in md


class TestWriteSkills:
    def test_writes_new_skills(self, tmp_path: Path) -> None:
        stats = PatternStats(
            normalized="run security scan",
            category="security",
            occurrences=[
                PatternOccurrence("2026-02-20", "s1.json", "scan", True),
            ],
        )
        candidate = SkillCandidate(
            pattern=stats,
            skill_id="Skill-Security-001",
            title="Run security scan",
        )
        written = write_skills([candidate], tmp_path)
        assert len(written) == 1
        assert written[0].exists()
        content = written[0].read_text()
        assert "# Skill:" in content

    def test_skips_duplicates(self, tmp_path: Path) -> None:
        stats = PatternStats(normalized="test", category="general")
        candidate = SkillCandidate(
            pattern=stats,
            skill_id="Skill-General-001",
            title="Test",
            duplicate_of="existing skill",
        )
        written = write_skills([candidate], tmp_path)
        assert len(written) == 0


class TestConsolidationReport:
    def test_to_dict(self) -> None:
        report = ConsolidationReport(sessions_scanned=5, patterns_found=10)
        d = report.to_dict()
        assert d["sessions_scanned"] == 5
        assert d["patterns_found"] == 10
        assert d["candidates_total"] == 0
        assert d["candidates_new"] == 0


class TestCli:
    def test_dry_run_exits_zero(self, tmp_path: Path) -> None:
        sessions_dir = tmp_path / "sessions"
        sessions_dir.mkdir()
        memories_dir = tmp_path / "memories"
        memories_dir.mkdir()

        result = subprocess.run(
            [
                sys.executable,
                "scripts/consolidate_skills.py",
                "--sessions-dir", str(sessions_dir),
                "--memories-dir", str(memories_dir),
                "--dry-run",
                "--project-root", str(tmp_path),
            ],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0

    def test_json_output(self, tmp_path: Path) -> None:
        sessions_dir = tmp_path / "sessions"
        sessions_dir.mkdir()
        memories_dir = tmp_path / "memories"
        memories_dir.mkdir()

        result = subprocess.run(
            [
                sys.executable,
                "scripts/consolidate_skills.py",
                "--sessions-dir", str(sessions_dir),
                "--memories-dir", str(memories_dir),
                "--format", "json",
                "--project-root", str(tmp_path),
            ],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert "sessions_scanned" in data

    def test_path_containment_rejects_outside_root(self, tmp_path: Path) -> None:
        result = subprocess.run(
            [
                sys.executable,
                "scripts/consolidate_skills.py",
                "--sessions-dir", "/tmp/outside",
                "--project-root", str(tmp_path),
            ],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 2
