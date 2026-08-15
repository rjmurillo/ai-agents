"""Tests for validate_workspace_budget.py workspace file budget enforcement."""

from __future__ import annotations

from pathlib import Path

from scripts.validate_workspace_budget import (
    PER_FILE_BUDGET_BYTES,
    TOTAL_BUDGET_BYTES,
    WORKSPACE_FILES,
    FileMetric,
    main,
    measure_workspace_files,
    validate_budget,
)


class TestConstants:
    def test_total_budget_is_6600(self) -> None:
        assert TOTAL_BUDGET_BYTES == 6600

    def test_per_file_budget_is_3000(self) -> None:
        assert PER_FILE_BUDGET_BYTES == 3000

    def test_workspace_files_includes_expected(self) -> None:
        assert "CLAUDE.md" in WORKSPACE_FILES
        assert "AGENTS.md" in WORKSPACE_FILES
        assert ".claude/CLAUDE.md" in WORKSPACE_FILES


class TestMeasureWorkspaceFiles:
    def test_missing_files_report_zero_bytes(self, tmp_path: Path) -> None:
        metrics = measure_workspace_files(tmp_path)
        for m in metrics:
            assert m.size_bytes == 0
            assert not m.exists

    def test_existing_file_reports_size(self, tmp_path: Path) -> None:
        (tmp_path / "CLAUDE.md").write_text("hello", encoding="utf-8")
        metrics = measure_workspace_files(tmp_path, ["CLAUDE.md"])
        assert len(metrics) == 1
        assert metrics[0].exists is True
        assert metrics[0].size_bytes == 5

    def test_nested_file_path(self, tmp_path: Path) -> None:
        (tmp_path / ".claude").mkdir()
        (tmp_path / ".claude" / "CLAUDE.md").write_text("x" * 100, encoding="utf-8")
        metrics = measure_workspace_files(tmp_path, [".claude/CLAUDE.md"])
        assert metrics[0].exists is True
        assert metrics[0].size_bytes == 100

    def test_custom_file_list(self, tmp_path: Path) -> None:
        (tmp_path / "custom.md").write_text("data", encoding="utf-8")
        metrics = measure_workspace_files(tmp_path, ["custom.md"])
        assert len(metrics) == 1
        assert metrics[0].path == "custom.md"


class TestValidateBudget:
    def test_under_budget_passes(self) -> None:
        metrics = [FileMetric(path="a.md", size_bytes=1000, exists=True)]
        result = validate_budget(metrics)
        assert result.is_valid

    def test_per_file_over_budget_fails(self) -> None:
        metrics = [FileMetric(path="big.md", size_bytes=4000, exists=True)]
        result = validate_budget(metrics, per_file_budget=3000)
        assert not result.is_valid
        assert any("big.md" in e for e in result.errors)

    def test_total_over_budget_fails(self) -> None:
        metrics = [
            FileMetric(path="a.md", size_bytes=2500, exists=True),
            FileMetric(path="b.md", size_bytes=2500, exists=True),
            FileMetric(path="c.md", size_bytes=2500, exists=True),
        ]
        result = validate_budget(metrics, total_budget=6600)
        assert not result.is_valid
        assert any("Total" in e for e in result.errors)

    def test_missing_files_ignored(self) -> None:
        metrics = [FileMetric(path="gone.md", size_bytes=0, exists=False)]
        result = validate_budget(metrics)
        assert result.is_valid

    def test_total_bytes_property(self) -> None:
        metrics = [
            FileMetric(path="a.md", size_bytes=100, exists=True),
            FileMetric(path="b.md", size_bytes=200, exists=True),
        ]
        result = validate_budget(metrics)
        assert result.total_bytes == 300

    def test_exactly_at_budget_passes(self) -> None:
        metrics = [FileMetric(path="a.md", size_bytes=3000, exists=True)]
        result = validate_budget(metrics, total_budget=6600, per_file_budget=3000)
        assert result.is_valid

    def test_one_byte_over_per_file_fails(self) -> None:
        metrics = [FileMetric(path="a.md", size_bytes=3001, exists=True)]
        result = validate_budget(metrics, per_file_budget=3000)
        assert not result.is_valid


class TestMain:
    def test_nonexistent_path_returns_config_error(self) -> None:
        assert main(["--path", "/nonexistent/dir"]) == 2

    def test_under_budget_returns_0(self, tmp_path: Path) -> None:
        (tmp_path / "CLAUDE.md").write_text("small", encoding="utf-8")
        (tmp_path / "AGENTS.md").write_text("small", encoding="utf-8")
        (tmp_path / ".claude").mkdir()
        (tmp_path / ".claude" / "CLAUDE.md").write_text("small", encoding="utf-8")
        assert main(["--path", str(tmp_path)]) == 0

    def test_over_budget_returns_1(self, tmp_path: Path) -> None:
        (tmp_path / "CLAUDE.md").write_text("x" * 4000, encoding="utf-8")
        assert main(["--path", str(tmp_path)]) == 1

    def test_custom_budgets(self, tmp_path: Path) -> None:
        (tmp_path / "CLAUDE.md").write_text("x" * 500, encoding="utf-8")
        assert main(["--path", str(tmp_path), "--per-file-budget", "100"]) == 1
        assert main(["--path", str(tmp_path), "--per-file-budget", "1000"]) == 0

    def test_repo_workspace_files_within_budget(self) -> None:
        """E2E: Verify actual repo workspace files are within budget."""
        repo_root = Path(__file__).resolve().parent.parent
        result = main(["--path", str(repo_root)])
        assert result == 0, (
            "Workspace files exceed budget. Run: python scripts/validate_workspace_budget.py"
        )


class TestCustomCeilingDisplay:
    """Tests for issue #4883: display uses effective ceilings."""

    def test_custom_ceiling_file_above_generic_below_ratchet_passes(self) -> None:
        """A file above PER_FILE_BUDGET_BYTES but below its custom ceiling passes."""
        metrics = [
            FileMetric(path="special.md", size_bytes=4000, exists=True),
        ]
        # Custom ceiling of 5000 > 4000 > generic 3000
        result = validate_budget(
            metrics, per_file_budget=3000, file_ceilings={"special.md": 5000}
        )
        assert result.is_valid

    def test_custom_ceiling_file_above_ratchet_fails(self) -> None:
        """A file above its custom ceiling fails."""
        metrics = [
            FileMetric(path="special.md", size_bytes=6000, exists=True),
        ]
        result = validate_budget(
            metrics, per_file_budget=3000, file_ceilings={"special.md": 5000}
        )
        assert not result.is_valid

    def test_custom_ceiling_file_excluded_from_pool_total(self) -> None:
        """Custom-ceiling files do not count toward the shared pool budget."""
        metrics = [
            FileMetric(path="a.md", size_bytes=3000, exists=True),
            FileMetric(path="b.md", size_bytes=3000, exists=True),
            FileMetric(path="custom.md", size_bytes=4000, exists=True),
        ]
        # a + b = 6000 <= 6600 pool; custom excluded from pool
        result = validate_budget(
            metrics,
            total_budget=6600,
            per_file_budget=3000,
            file_ceilings={"custom.md": 5000},
        )
        assert result.is_valid

    def test_pool_exceeds_budget_when_custom_excluded(self) -> None:
        """Pool files alone can exceed budget even when custom file is fine."""
        metrics = [
            FileMetric(path="a.md", size_bytes=3000, exists=True),
            FileMetric(path="b.md", size_bytes=3000, exists=True),
            FileMetric(path="c.md", size_bytes=2000, exists=True),
            FileMetric(path="custom.md", size_bytes=4000, exists=True),
        ]
        # a + b + c = 8000 > 6600; custom excluded
        result = validate_budget(
            metrics,
            total_budget=6600,
            per_file_budget=3000,
            file_ceilings={"custom.md": 5000},
        )
        assert not result.is_valid
        assert any("Total" in e for e in result.errors)


class TestMainDisplayOutput:
    """Tests for issue #4883: main() output matches validation semantics."""

    def test_no_over_with_successful_validation(self, tmp_path: Path, capsys) -> None:
        """AC: cannot produce [OVER] followed by pass unless it names advisory threshold."""
        (tmp_path / "CLAUDE.md").write_text("x" * 100, encoding="utf-8")
        (tmp_path / "AGENTS.md").write_text("x" * 100, encoding="utf-8")
        (tmp_path / ".claude").mkdir()
        (tmp_path / ".claude" / "CLAUDE.md").write_text("x" * 100, encoding="utf-8")
        (tmp_path / ".github").mkdir()
        (tmp_path / ".github" / "copilot-instructions.md").write_text(
            "x" * 4000, encoding="utf-8"
        )
        rc = main(["--path", str(tmp_path)])
        out = capsys.readouterr().out
        if rc == 0:
            assert "[OVER]" not in out

    def test_pool_total_excludes_custom_ceiling_files(
        self, tmp_path: Path, capsys
    ) -> None:
        """AC: displayed aggregate uses same membership as pass/fail."""
        (tmp_path / "CLAUDE.md").write_text("x" * 2000, encoding="utf-8")
        (tmp_path / "AGENTS.md").write_text("x" * 2000, encoding="utf-8")
        (tmp_path / ".claude").mkdir()
        (tmp_path / ".claude" / "CLAUDE.md").write_text("x" * 100, encoding="utf-8")
        (tmp_path / ".github").mkdir()
        (tmp_path / ".github" / "copilot-instructions.md").write_text(
            "x" * 5000, encoding="utf-8"
        )
        rc = main(["--path", str(tmp_path)])
        out = capsys.readouterr().out
        assert rc == 0
        # Pool total should be 2000+2000+100 = 4100, not include the 5000
        assert "Pool total: 4,100 / 6,600 bytes" in out
