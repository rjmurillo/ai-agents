"""Tests for pr_branch_mapping module.

Verifies PR-to-branch mapping operations used to prevent cross-PR commits
during multi-PR sessions (Issue #683).
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from scripts.pr_branch_mapping import (
    MEMORY_RELATIVE_PATH,
    PRBranchEntry,
    PRBranchMapping,
    add_mapping,
    get_branch_for_pr,
    get_pr_for_branch,
    load_mapping,
    main,
    remove_merged_entries,
    save_mapping,
    validate_branch_pr_consistency,
)


@pytest.fixture
def empty_mapping() -> PRBranchMapping:
    """Create an empty mapping."""
    return PRBranchMapping()


@pytest.fixture
def sample_mapping() -> PRBranchMapping:
    """Create a mapping with sample entries."""
    return PRBranchMapping(
        mappings=[
            PRBranchEntry(
                pr_number=100,
                branch_name="feat/add-widget",
                created_at="2026-01-01T00:00:00Z",
                status="open",
                last_session="2026-01-01-session-01",
            ),
            PRBranchEntry(
                pr_number=200,
                branch_name="fix/broken-thing",
                created_at="2026-01-02T00:00:00Z",
                status="merged",
                last_session="2026-01-02-session-01",
            ),
        ],
    )


class TestLoadMapping:
    """Tests for load_mapping function."""

    def test_returns_empty_when_file_missing(self, tmp_path: Path) -> None:
        result = load_mapping(tmp_path)

        assert result.mappings == []
        assert result.current_session is None

    def test_loads_valid_mapping(self, tmp_path: Path) -> None:
        data = {
            "mappings": [
                {
                    "pr_number": 42,
                    "branch_name": "feat/test",
                    "created_at": "2026-01-01T00:00:00Z",
                    "status": "open",
                    "last_session": "session-01",
                },
            ],
            "current_session": {
                "session_id": "session-01",
                "pr_number": 42,
                "branch_name": "feat/test",
            },
        }
        _write_memory_file(tmp_path, data)

        result = load_mapping(tmp_path)

        assert len(result.mappings) == 1
        assert result.mappings[0].pr_number == 42
        assert result.mappings[0].branch_name == "feat/test"
        assert result.current_session is not None
        assert result.current_session.pr_number == 42

    def test_returns_empty_when_no_json_block(self, tmp_path: Path) -> None:
        memory_path = tmp_path / MEMORY_RELATIVE_PATH
        memory_path.parent.mkdir(parents=True)
        memory_path.write_text("# No JSON here\n", encoding="utf-8")

        result = load_mapping(tmp_path)

        assert result.mappings == []

    def test_loads_mapping_without_current_session(self, tmp_path: Path) -> None:
        data = {"mappings": []}
        _write_memory_file(tmp_path, data)

        result = load_mapping(tmp_path)

        assert result.current_session is None


class TestSaveMapping:
    """Tests for save_mapping function."""

    def test_creates_file_and_directories(self, tmp_path: Path) -> None:
        mapping = PRBranchMapping()

        save_mapping(tmp_path, mapping)

        memory_path = tmp_path / MEMORY_RELATIVE_PATH
        assert memory_path.exists()

    def test_roundtrip_preserves_data(self, tmp_path: Path) -> None:
        mapping = PRBranchMapping()
        add_mapping(mapping, pr_number=99, branch_name="feat/roundtrip", session_id="s1")

        save_mapping(tmp_path, mapping)
        loaded = load_mapping(tmp_path)

        assert len(loaded.mappings) == 1
        assert loaded.mappings[0].pr_number == 99
        assert loaded.mappings[0].branch_name == "feat/roundtrip"
        assert loaded.current_session is not None
        assert loaded.current_session.session_id == "s1"


class TestAddMapping:
    """Tests for add_mapping function."""

    def test_adds_new_entry(self, empty_mapping: PRBranchMapping) -> None:
        result = add_mapping(empty_mapping, pr_number=10, branch_name="feat/new")

        assert len(result.mappings) == 1
        assert result.mappings[0].pr_number == 10
        assert result.mappings[0].branch_name == "feat/new"

    def test_updates_existing_entry(self, sample_mapping: PRBranchMapping) -> None:
        result = add_mapping(
            sample_mapping,
            pr_number=100,
            branch_name="feat/updated-widget",
            session_id="s2",
        )

        assert len(result.mappings) == 2
        entry = next(m for m in result.mappings if m.pr_number == 100)
        assert entry.branch_name == "feat/updated-widget"
        assert entry.last_session == "s2"

    def test_sets_current_session(self, empty_mapping: PRBranchMapping) -> None:
        result = add_mapping(
            empty_mapping,
            pr_number=5,
            branch_name="fix/bug",
            session_id="session-99",
        )

        assert result.current_session is not None
        assert result.current_session.pr_number == 5
        assert result.current_session.session_id == "session-99"

    def test_sets_created_at_timestamp(self, empty_mapping: PRBranchMapping) -> None:
        add_mapping(empty_mapping, pr_number=1, branch_name="test")

        assert empty_mapping.mappings[0].created_at != ""

    def test_removes_other_pr_with_same_branch(
        self, empty_mapping: PRBranchMapping
    ) -> None:
        """Ensure branch uniqueness: adding a new PR with an existing branch removes the old mapping."""
        add_mapping(empty_mapping, pr_number=100, branch_name="feat/shared")
        add_mapping(empty_mapping, pr_number=200, branch_name="feat/shared")

        # Should only have one entry (PR 200), not two
        assert len(empty_mapping.mappings) == 1
        assert empty_mapping.mappings[0].pr_number == 200
        assert empty_mapping.mappings[0].branch_name == "feat/shared"

    def test_preserves_other_entries_when_removing_duplicate_branch(
        self, empty_mapping: PRBranchMapping
    ) -> None:
        """Other mappings with different branches should be preserved."""
        add_mapping(empty_mapping, pr_number=100, branch_name="feat/first")
        add_mapping(empty_mapping, pr_number=101, branch_name="feat/second")
        add_mapping(empty_mapping, pr_number=200, branch_name="feat/first")  # Takes over feat/first

        # Should have PR 200 (feat/first) and PR 101 (feat/second)
        assert len(empty_mapping.mappings) == 2
        pr_numbers = {m.pr_number for m in empty_mapping.mappings}
        assert pr_numbers == {101, 200}


class TestGetBranchForPR:
    """Tests for get_branch_for_pr function."""

    def test_returns_branch_when_found(self, sample_mapping: PRBranchMapping) -> None:
        result = get_branch_for_pr(sample_mapping, pr_number=100)

        assert result == "feat/add-widget"

    def test_returns_none_when_not_found(self, sample_mapping: PRBranchMapping) -> None:
        result = get_branch_for_pr(sample_mapping, pr_number=999)

        assert result is None


class TestGetPRForBranch:
    """Tests for get_pr_for_branch function."""

    def test_returns_pr_when_found(self, sample_mapping: PRBranchMapping) -> None:
        result = get_pr_for_branch(sample_mapping, branch_name="fix/broken-thing")

        assert result == 200

    def test_returns_none_when_not_found(self, sample_mapping: PRBranchMapping) -> None:
        result = get_pr_for_branch(sample_mapping, branch_name="nonexistent")

        assert result is None


class TestValidateBranchPRConsistency:
    """Tests for validate_branch_pr_consistency function."""

    def test_passes_with_no_active_session(
        self, empty_mapping: PRBranchMapping
    ) -> None:
        is_ok, msg = validate_branch_pr_consistency(empty_mapping, current_branch="main")

        assert is_ok is True
        assert "No active session" in msg

    def test_passes_when_branch_matches(
        self, sample_mapping: PRBranchMapping
    ) -> None:
        from scripts.pr_branch_mapping import CurrentSession

        sample_mapping.current_session = CurrentSession(
            session_id="s1", pr_number=100, branch_name="feat/add-widget"
        )

        is_ok, msg = validate_branch_pr_consistency(
            sample_mapping, current_branch="feat/add-widget"
        )

        assert is_ok is True

    def test_fails_when_branch_mismatches(
        self, sample_mapping: PRBranchMapping
    ) -> None:
        from scripts.pr_branch_mapping import CurrentSession

        sample_mapping.current_session = CurrentSession(
            session_id="s1", pr_number=100, branch_name="feat/add-widget"
        )

        is_ok, msg = validate_branch_pr_consistency(
            sample_mapping, current_branch="fix/wrong-branch"
        )

        assert is_ok is False
        assert "Branch mismatch" in msg

    @patch("scripts.pr_branch_mapping._get_current_branch", return_value=None)
    def test_fails_when_git_branch_unavailable(
        self, _mock_branch: object, sample_mapping: PRBranchMapping
    ) -> None:
        from scripts.pr_branch_mapping import CurrentSession

        sample_mapping.current_session = CurrentSession(
            session_id="s1", pr_number=100, branch_name="feat/add-widget"
        )

        is_ok, msg = validate_branch_pr_consistency(sample_mapping)

        assert is_ok is False
        assert "Could not determine" in msg


class TestRemoveMergedEntries:
    """Tests for remove_merged_entries function."""

    def test_removes_merged_entries(self, sample_mapping: PRBranchMapping) -> None:
        removed = remove_merged_entries(sample_mapping)

        assert removed == 1
        assert len(sample_mapping.mappings) == 1
        assert sample_mapping.mappings[0].pr_number == 100

    def test_removes_closed_entries(self) -> None:
        mapping = PRBranchMapping(
            mappings=[
                PRBranchEntry(
                    pr_number=1,
                    branch_name="a",
                    created_at="t",
                    status="closed",
                ),
            ],
        )

        removed = remove_merged_entries(mapping)

        assert removed == 1
        assert len(mapping.mappings) == 0

    def test_returns_zero_when_nothing_to_remove(
        self, empty_mapping: PRBranchMapping
    ) -> None:
        removed = remove_merged_entries(empty_mapping)

        assert removed == 0


class TestToDict:
    """Tests for PRBranchMapping.to_dict method."""

    def test_serializes_empty_mapping(self) -> None:
        mapping = PRBranchMapping()
        result = mapping.to_dict()

        assert result == {"mappings": []}

    def test_serializes_with_current_session(self) -> None:
        from scripts.pr_branch_mapping import CurrentSession

        mapping = PRBranchMapping(
            current_session=CurrentSession("s1", 42, "feat/test"),
        )
        result = mapping.to_dict()

        assert result["current_session"]["session_id"] == "s1"
        assert result["current_session"]["pr_number"] == 42


class TestMainCLI:
    """Tests for main() CLI entry point."""

    def test_add_creates_mapping(self, tmp_path: Path) -> None:
        exit_code = main([
            "--project-root", str(tmp_path),
            "add", "--pr", "42", "--branch", "feat/test",
        ])

        assert exit_code == 0
        loaded = load_mapping(tmp_path)
        assert len(loaded.mappings) == 1

    def test_query_by_pr(self, tmp_path: Path, capsys: object) -> None:
        mapping = PRBranchMapping()
        add_mapping(mapping, 42, "feat/test")
        save_mapping(tmp_path, mapping)

        exit_code = main([
            "--project-root", str(tmp_path),
            "query", "--pr", "42",
        ])

        assert exit_code == 0

    def test_query_not_found(self, tmp_path: Path) -> None:
        save_mapping(tmp_path, PRBranchMapping())

        exit_code = main([
            "--project-root", str(tmp_path),
            "query", "--pr", "999",
        ])

        assert exit_code == 1

    def test_query_by_branch(self, tmp_path: Path) -> None:
        mapping = PRBranchMapping()
        add_mapping(mapping, 42, "feat/test")
        save_mapping(tmp_path, mapping)

        exit_code = main([
            "--project-root", str(tmp_path),
            "query", "--branch", "feat/test",
        ])

        assert exit_code == 0

    def test_list_empty(self, tmp_path: Path) -> None:
        exit_code = main([
            "--project-root", str(tmp_path),
            "list",
        ])

        assert exit_code == 0

    def test_list_with_entries(self, tmp_path: Path) -> None:
        mapping = PRBranchMapping()
        add_mapping(mapping, 42, "feat/test")
        save_mapping(tmp_path, mapping)

        exit_code = main([
            "--project-root", str(tmp_path),
            "list",
        ])

        assert exit_code == 0

    @patch("scripts.pr_branch_mapping._get_current_branch", return_value="feat/test")
    def test_validate_passes(self, _mock: object, tmp_path: Path) -> None:
        mapping = PRBranchMapping()
        add_mapping(mapping, 42, "feat/test", "s1")
        save_mapping(tmp_path, mapping)

        exit_code = main([
            "--project-root", str(tmp_path),
            "validate",
        ])

        assert exit_code == 0

    @patch(
        "scripts.pr_branch_mapping._get_current_branch",
        return_value="wrong-branch",
    )
    def test_validate_fails_on_mismatch(self, _mock: object, tmp_path: Path) -> None:
        mapping = PRBranchMapping()
        add_mapping(mapping, 42, "feat/test", "s1")
        save_mapping(tmp_path, mapping)

        exit_code = main([
            "--project-root", str(tmp_path),
            "validate",
        ])

        assert exit_code == 1

    def test_cleanup_removes_merged(self, tmp_path: Path) -> None:
        mapping = PRBranchMapping(
            mappings=[
                PRBranchEntry(1, "a", "t", status="merged"),
                PRBranchEntry(2, "b", "t", status="open"),
            ],
        )
        save_mapping(tmp_path, mapping)

        exit_code = main([
            "--project-root", str(tmp_path),
            "cleanup",
        ])

        assert exit_code == 0
        loaded = load_mapping(tmp_path)
        assert len(loaded.mappings) == 1

    def test_corrupt_json_returns_exit_3(self, tmp_path: Path) -> None:
        memory_path = tmp_path / MEMORY_RELATIVE_PATH
        memory_path.parent.mkdir(parents=True)
        memory_path.write_text(
            "# Bad\n```json\n{invalid json\n```\n", encoding="utf-8"
        )

        exit_code = main([
            "--project-root", str(tmp_path),
            "list",
        ])

        assert exit_code == 3


# --- Helper ---


def _write_memory_file(project_root: Path, data: dict) -> None:
    """Write a memory file with a JSON block for testing."""
    memory_path = project_root / MEMORY_RELATIVE_PATH
    memory_path.parent.mkdir(parents=True, exist_ok=True)
    json_str = json.dumps(data, indent=2)
    content = f"# PR-to-Branch Mapping\n\n```json\n{json_str}\n```\n"
    memory_path.write_text(content, encoding="utf-8")
