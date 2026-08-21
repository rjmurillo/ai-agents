#!/usr/bin/env python3
"""Tests for detect_adr_changes module."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any, cast
from unittest.mock import MagicMock, patch

import pytest

TESTS_SKILLS_DIR = str(Path(__file__).resolve().parents[1])
PROJECT_ROOT = str(Path(__file__).resolve().parents[3])
if TESTS_SKILLS_DIR not in sys.path:
    sys.path.insert(0, TESTS_SKILLS_DIR)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from claude_skills_import import import_skill_script

mod = import_skill_script(".claude/skills/adr-review/scripts/detect_adr_changes.py")

_get_adr_status = mod._get_adr_status
_get_dependent_adrs = mod._get_dependent_adrs
_run_git = mod._run_git
_split_frontmatter = mod._split_frontmatter
_is_frontmatter_only_change = mod._is_frontmatter_only_change
_frontmatter_fields = mod._parse_frontmatter
_only_non_decision_fields_changed = mod._only_non_decision_fields_changed
main = mod.main


class TestGetAdrStatus:
    """Tests for _get_adr_status function.

    The function reads ONLY the leading ``---`` fenced YAML frontmatter block
    (issue #5189). Every state in which the record declares no status returns
    the distinct ``unknown`` sentinel; ``proposed`` is returned only when the
    frontmatter literally says ``status: proposed``.
    """

    def test_returns_unknown_for_missing_file(self, tmp_path: Path) -> None:
        result = _get_adr_status(tmp_path / "nonexistent.md")
        assert result == "unknown"

    def test_extracts_status_from_frontmatter(self, tmp_path: Path) -> None:
        adr = tmp_path / "ADR-001.md"
        adr.write_text("---\nstatus: accepted\n---\n# Title\n")
        result = _get_adr_status(adr)
        assert result == "accepted"

    def test_returns_proposed_only_when_frontmatter_declares_it(self, tmp_path: Path) -> None:
        adr = tmp_path / "ADR-001.md"
        adr.write_text("---\nstatus: proposed\n---\n# Title\n")
        result = _get_adr_status(adr)
        assert result == "proposed"

    def test_returns_unknown_when_no_frontmatter_block(self, tmp_path: Path) -> None:
        """A record that declares nothing is not a record that declares proposed."""
        adr = tmp_path / "ADR-001.md"
        adr.write_text("# ADR-001\nSome content\n")
        result = _get_adr_status(adr)
        assert result == "unknown"
        assert result != "proposed"

    def test_returns_unknown_when_frontmatter_is_unterminated(self, tmp_path: Path) -> None:
        adr = tmp_path / "ADR-001.md"
        adr.write_text("---\nstatus: accepted\n\n# Title\nNo closing delimiter\n")
        assert _get_adr_status(adr) == "unknown"

    def test_returns_unknown_when_frontmatter_omits_status(self, tmp_path: Path) -> None:
        adr = tmp_path / "ADR-001.md"
        adr.write_text("---\nid: ADR-001\nimplemented: false\n---\n# Title\n")
        assert _get_adr_status(adr) == "unknown"

    def test_returns_unknown_for_empty_frontmatter_block(self, tmp_path: Path) -> None:
        adr = tmp_path / "ADR-001.md"
        adr.write_text("---\n---\n# Title\n")
        assert _get_adr_status(adr) == "unknown"

    def test_returns_unknown_for_explicit_null_status(self, tmp_path: Path) -> None:
        adr = tmp_path / "ADR-001.md"
        adr.write_text("---\nstatus: null\n---\n# Title\n")
        assert _get_adr_status(adr) == "unknown"

    def test_fenced_yaml_example_in_body_does_not_win(self, tmp_path: Path) -> None:
        """Regression guard for ADR-073, which embeds the enum in a fenced example."""
        adr = tmp_path / "ADR-001.md"
        adr.write_text("---\nstatus: proposed\n---\n# Title\n\n```yaml\nstatus: accepted\n```\n")
        assert _get_adr_status(adr) == "proposed"

    def test_bare_status_line_in_body_does_not_win(self, tmp_path: Path) -> None:
        adr = tmp_path / "ADR-001.md"
        adr.write_text("---\nstatus: proposed\n---\n# Title\n\nstatus: accepted\n")
        assert _get_adr_status(adr) == "proposed"

    def test_body_status_line_without_frontmatter_is_ignored(self, tmp_path: Path) -> None:
        adr = tmp_path / "ADR-001.md"
        adr.write_text("# ADR-001\n\nstatus: accepted\n")
        assert _get_adr_status(adr) == "unknown"

    def test_malformed_yaml_returns_unknown_without_raising(self, tmp_path: Path) -> None:
        """Malformed frontmatter must not crash the caller (documented behavior)."""
        adr = tmp_path / "ADR-001.md"
        adr.write_text("---\nstatus: [unclosed\n---\n# Title\n")
        assert _get_adr_status(adr) == "unknown"

    def test_non_mapping_frontmatter_returns_unknown(self, tmp_path: Path) -> None:
        adr = tmp_path / "ADR-001.md"
        adr.write_text("---\n- just\n- a list\n---\n# Title\n")
        assert _get_adr_status(adr) == "unknown"

    def test_returns_unknown_when_file_is_unreadable(self, tmp_path: Path) -> None:
        adr = tmp_path / "ADR-001.md"
        adr.write_text("---\nstatus: accepted\n---\n")
        with patch.object(Path, "read_text", side_effect=OSError("boom")):
            assert _get_adr_status(adr) == "unknown"

    def test_normalizes_status_to_lowercase(self, tmp_path: Path) -> None:
        adr = tmp_path / "ADR-001.md"
        adr.write_text("---\nstatus: DEPRECATED\n---\n")
        result = _get_adr_status(adr)
        assert result == "deprecated"

    def test_strips_whitespace(self, tmp_path: Path) -> None:
        adr = tmp_path / "ADR-001.md"
        adr.write_text("---\nstatus:   accepted  \n---\n")
        result = _get_adr_status(adr)
        assert result == "accepted"

    def test_reads_the_real_adr_073_record(self) -> None:
        """ADR-073 declares ``accepted`` and embeds the enum in a fenced example.

        Independent end-to-end check against the canonical corpus rather than a
        synthetic fixture: the body fence must not override the frontmatter.
        """
        adr = (
            Path(PROJECT_ROOT)
            / ".agents"
            / "architecture"
            / ("ADR-073-adr-lifecycle-frontmatter.md")
        )
        if not adr.is_file():
            pytest.skip(f"canonical ADR not present at {adr}")
        assert _get_adr_status(adr) == "accepted"


class TestGetDependentAdrs:
    """Tests for _get_dependent_adrs function."""

    def test_finds_references(self, tmp_path: Path) -> None:
        arch_dir = tmp_path / ".agents" / "architecture"
        arch_dir.mkdir(parents=True)
        (arch_dir / "ADR-001.md").write_text("# ADR-001\nReferences ADR-002")
        (arch_dir / "ADR-002.md").write_text("# ADR-002\nNo references")
        # _get_dependent_adrs returns all ADR files containing the search
        # string, including the target ADR itself (ADR-002.md matches "ADR-002").
        result = _get_dependent_adrs("ADR-002", tmp_path)
        assert len(result) == 2
        names = [Path(r).name for r in result]
        assert "ADR-001.md" in names
        assert "ADR-002.md" in names

    def test_returns_empty_for_no_references(self, tmp_path: Path) -> None:
        arch_dir = tmp_path / ".agents" / "architecture"
        arch_dir.mkdir(parents=True)
        (arch_dir / "ADR-001.md").write_text("# ADR-001\nNo references")
        result = _get_dependent_adrs("ADR-999", tmp_path)
        assert result == []

    def test_handles_missing_directory(self, tmp_path: Path) -> None:
        result = _get_dependent_adrs("ADR-001", tmp_path)
        assert result == []


class TestRunGit:
    """Tests for _run_git function."""

    def test_returns_completed_process(self, tmp_path: Path) -> None:
        subprocess.run(["git", "init"], cwd=str(tmp_path), capture_output=True, check=True)
        result = _run_git(["status"], cwd=tmp_path)
        assert result.returncode == 0
        assert isinstance(result, subprocess.CompletedProcess)

    def test_returns_error_code_on_failure(self, tmp_path: Path) -> None:
        result = _run_git(["log", "--oneline", "-1"], cwd=tmp_path)
        assert result.returncode != 0

    @patch("subprocess.run", side_effect=FileNotFoundError())
    def test_handles_missing_git(self, mock_run: MagicMock) -> None:
        with pytest.raises(FileNotFoundError):
            _run_git(["status"], cwd=Path("/tmp"))


class TestMain:
    """Tests for main entry point via argparse."""

    @pytest.fixture
    def git_repo(self, tmp_path: Path) -> Path:
        subprocess.run(["git", "init"], cwd=str(tmp_path), capture_output=True, check=True)
        subprocess.run(
            ["git", "config", "core.hooksPath", "/dev/null"],
            cwd=str(tmp_path),
            capture_output=True,
            check=True,
        )
        subprocess.run(
            ["git", "config", "user.email", "test@test.com"],
            cwd=str(tmp_path),
            capture_output=True,
            check=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Test"],
            cwd=str(tmp_path),
            capture_output=True,
            check=True,
        )
        (tmp_path / "README.md").write_text("init")
        subprocess.run(["git", "add", "."], cwd=str(tmp_path), capture_output=True, check=True)
        subprocess.run(
            ["git", "commit", "-m", "init"],
            cwd=str(tmp_path),
            capture_output=True,
            check=True,
        )
        (tmp_path / "README.md").write_text("updated")
        subprocess.run(["git", "add", "."], cwd=str(tmp_path), capture_output=True, check=True)
        subprocess.run(
            ["git", "commit", "-m", "update readme"],
            cwd=str(tmp_path),
            capture_output=True,
            check=True,
        )
        return tmp_path

    def test_no_changes(self, git_repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
        exit_code = main(["--base-path", str(git_repo)])
        assert exit_code == 0
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert data["HasChanges"] is False
        assert data["RecommendedAction"] == "none"

    def test_detects_created_adr(self, git_repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
        arch_dir = git_repo / ".agents" / "architecture"
        arch_dir.mkdir(parents=True)
        (arch_dir / "ADR-001.md").write_text("# ADR-001")
        subprocess.run(["git", "add", "."], cwd=str(git_repo), capture_output=True, check=True)
        subprocess.run(
            ["git", "commit", "-m", "add ADR"],
            cwd=str(git_repo),
            capture_output=True,
            check=True,
        )
        exit_code = main(["--base-path", str(git_repo)])
        assert exit_code == 0
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert data["HasChanges"] is True
        assert len(data["Created"]) == 1
        assert data["RecommendedAction"] == "review"

    def test_result_has_timestamp(self, git_repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
        exit_code = main(["--base-path", str(git_repo)])
        assert exit_code == 0
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert "Timestamp" in data
        assert "SinceCommit" in data

    def test_exits_for_non_git_repo(self, tmp_path: Path) -> None:
        exit_code = main(["--base-path", str(tmp_path)])
        assert exit_code == 1

    def test_result_structure(self, git_repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
        exit_code = main(["--base-path", str(git_repo)])
        assert exit_code == 0
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        required_keys = [
            "Created",
            "Modified",
            "Deleted",
            "DeletedDetails",
            "HasChanges",
            "RecommendedAction",
            "Timestamp",
            "SinceCommit",
        ]
        for key in required_keys:
            assert key in data

    def test_outputs_json(self, git_repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
        exit_code = main(["--base-path", str(git_repo)])
        assert exit_code == 0
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert "HasChanges" in data


class TestSplitFrontmatter:
    """Tests for _split_frontmatter helper."""

    def test_splits_frontmatter_and_body(self) -> None:
        content = "---\nstatus: proposed\n---\n\n# Body\n\nText.\n"
        frontmatter, body = _split_frontmatter(content)
        assert "status: proposed" in frontmatter
        assert body == "\n# Body\n\nText.\n"

    def test_no_frontmatter_returns_empty_and_full_content(self) -> None:
        content = "# Body only\n\nNo frontmatter.\n"
        frontmatter, body = _split_frontmatter(content)
        assert frontmatter == ""
        assert body == content

    def test_unterminated_frontmatter_treated_as_body(self) -> None:
        content = "---\nstatus: proposed\n# never closes\n"
        frontmatter, body = _split_frontmatter(content)
        assert frontmatter == ""
        assert body == content


class TestOnlyNonDecisionFieldsChanged:
    """Tests for the frontmatter allowlist gate (#2845, ADR-073)."""

    def test_implemented_flip_is_exempt(self) -> None:
        old = "status: proposed\nimplemented: false\n"
        new = "status: proposed\nimplemented: true\n"
        assert _only_non_decision_fields_changed(old, new) is True

    def test_status_flip_is_not_exempt(self) -> None:
        # A hand-edit to accepted MUST still trip the gate (ADR-073:61).
        old = "status: proposed\nimplemented: true\n"
        new = "status: accepted\nimplemented: true\n"
        assert _only_non_decision_fields_changed(old, new) is False

    def test_supersession_change_is_not_exempt(self) -> None:
        old = "status: accepted\nsuperseded-by: null\n"
        new = "status: accepted\nsuperseded-by: ADR-099\n"
        assert _only_non_decision_fields_changed(old, new) is False

    def test_block_style_supersedes_change_is_not_exempt(self) -> None:
        # A block-list supersedes change must be detected, not just scalars.
        old = "status: accepted\nsupersedes:\n  - ADR-001\n"
        new = "status: accepted\nsupersedes:\n  - ADR-002\n"
        assert _only_non_decision_fields_changed(old, new) is False

    def test_block_style_with_blank_line_change_is_not_exempt(self) -> None:
        # YAML permits blank lines inside a block list; a change after the blank
        # line must still be detected (review round-4 LOW finding).
        old = "status: accepted\nsupersedes:\n  - ADR-001\n\n  - ADR-002\n"
        new = "status: accepted\nsupersedes:\n  - ADR-001\n\n  - ADR-003\n"
        assert _only_non_decision_fields_changed(old, new) is False

    def test_malformed_frontmatter_fails_closed(self) -> None:
        # Unparseable YAML must not be treated as an exempt no-op change.
        old = "status: accepted\n"
        new = "status: accepted\nsupersedes: [ADR-001\n"
        assert _only_non_decision_fields_changed(old, new) is False

    def test_no_field_change_is_exempt(self) -> None:
        fm = "status: proposed\nimplemented: false\n"
        assert _only_non_decision_fields_changed(fm, fm) is True

    def test_governance_and_allowed_change_together_is_not_exempt(self) -> None:
        old = "status: proposed\nimplemented: false\n"
        new = "status: accepted\nimplemented: true\n"
        assert _only_non_decision_fields_changed(old, new) is False

    def test_duplicate_key_fails_closed(self) -> None:
        # A duplicated status line could hide an acceptance from the last-wins
        # map; fail closed so the gate still fires (review LOW finding).
        old = "status: proposed\nimplemented: false\n"
        new = "status: accepted\nimplemented: true\nstatus: proposed\n"
        assert _only_non_decision_fields_changed(old, new) is False


class TestFrontmatterFields:
    """Tests for the YAML frontmatter field parser."""

    def test_parses_top_level_scalars(self) -> None:
        fields = _frontmatter_fields("status: proposed\nimplemented: false\n")
        assert fields == {"status": "proposed", "implemented": False}

    def test_captures_indented_block_value(self) -> None:
        fields = _frontmatter_fields("supersedes:\n  - ADR-001\n  - ADR-002\nstatus: proposed\n")
        assert fields["supersedes"] == ["ADR-001", "ADR-002"]
        assert fields["status"] == "proposed"

    def test_malformed_returns_none(self) -> None:
        assert _frontmatter_fields("supersedes: [ADR-001\n") is None


class TestFrontmatterOnlyDetection:
    """Integration tests for frontmatter-only ADR change exemption (#2845)."""

    ADR_REL = ".agents/architecture/ADR-001.md"
    BODY = "\n# ADR-001: Example\n\n## Decision\n\nWe do X.\n"

    @pytest.fixture
    def adr_repo(self, tmp_path: Path) -> Path:
        def _git(*args: str) -> None:
            subprocess.run(["git", *args], cwd=str(tmp_path), capture_output=True, check=True)

        _git("init")
        _git("config", "core.hooksPath", "/dev/null")
        _git("config", "user.email", "test@test.com")
        _git("config", "user.name", "Test")
        adr = tmp_path / self.ADR_REL
        adr.parent.mkdir(parents=True)
        adr.write_text("---\nstatus: proposed\nimplemented: false\n---" + self.BODY)
        _git("add", ".")
        _git("commit", "-m", "add ADR-001")
        # Second commit on an unrelated file so HEAD~1 is the ADR commit.
        (tmp_path / "README.md").write_text("readme\n")
        _git("add", ".")
        _git("commit", "-m", "readme")
        return tmp_path

    def _run(self, repo: Path, capsys: pytest.CaptureFixture[str]) -> dict[str, Any]:
        exit_code = main(["--base-path", str(repo)])
        assert exit_code == 0
        return cast("dict[str, Any]", json.loads(capsys.readouterr().out))

    def test_frontmatter_only_flip_does_not_trigger(
        self, adr_repo: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        adr = adr_repo / self.ADR_REL
        adr.write_text("---\nstatus: proposed\nimplemented: true\n---" + self.BODY)
        data = self._run(adr_repo, capsys)
        assert data["HasChanges"] is False
        assert data["RecommendedAction"] == "none"
        assert data["Modified"] == []
        assert data["ModifiedFrontmatterOnly"] == [self.ADR_REL]

    def test_body_change_triggers_review(
        self, adr_repo: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        adr = adr_repo / self.ADR_REL
        new_body = self.BODY.replace("We do X.", "We do Y.")
        adr.write_text("---\nstatus: proposed\nimplemented: false\n---" + new_body)
        data = self._run(adr_repo, capsys)
        assert data["HasChanges"] is True
        assert data["Modified"] == [self.ADR_REL]
        assert data["ModifiedFrontmatterOnly"] == []
        assert data["RecommendedAction"] == "review"

    def test_path_traversal_fails_closed(self, adr_repo: Path) -> None:
        assert _is_frontmatter_only_change("../outside.md", "HEAD~1", adr_repo) is False

    def test_status_flip_triggers_review(
        self, adr_repo: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        # Frontmatter-only status flip to accepted MUST still fire the gate so
        # the author binds it to adr-review evidence (ADR-073:61, #2845 review).
        adr = adr_repo / self.ADR_REL
        adr.write_text("---\nstatus: accepted\nimplemented: false\n---" + self.BODY)
        data = self._run(adr_repo, capsys)
        assert data["HasChanges"] is True
        assert data["Modified"] == [self.ADR_REL]
        assert data["ModifiedFrontmatterOnly"] == []
        assert data["RecommendedAction"] == "review"

    def test_mixed_change_lists_only_substantive_as_modified(
        self, adr_repo: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        # ADR-001: frontmatter-only flip. ADR-002: new body change.
        adr2_rel = ".agents/architecture/ADR-002.md"
        adr2 = adr_repo / adr2_rel
        adr2.write_text("---\nstatus: proposed\n---\n# ADR-002\n\nOriginal.\n")
        subprocess.run(["git", "add", "."], cwd=str(adr_repo), capture_output=True, check=True)
        subprocess.run(
            ["git", "commit", "-m", "add ADR-002"],
            cwd=str(adr_repo),
            capture_output=True,
            check=True,
        )
        # Unrelated commit so HEAD~1 contains ADR-002 (else it reads as Created).
        (adr_repo / "README.md").write_text("readme2\n")
        subprocess.run(["git", "add", "."], cwd=str(adr_repo), capture_output=True, check=True)
        subprocess.run(
            ["git", "commit", "-m", "readme2"],
            cwd=str(adr_repo),
            capture_output=True,
            check=True,
        )
        # Working-tree edits (uncommitted): ADR-001 frontmatter-only flip,
        # ADR-002 body change.
        (adr_repo / self.ADR_REL).write_text(
            "---\nstatus: proposed\nimplemented: true\n---" + self.BODY
        )
        adr2.write_text("---\nstatus: proposed\n---\n# ADR-002\n\nChanged.\n")
        data = self._run(adr_repo, capsys)
        assert data["HasChanges"] is True
        assert data["Modified"] == [adr2_rel]
        assert data["ModifiedFrontmatterOnly"] == [self.ADR_REL]
        assert data["RecommendedAction"] == "review"
