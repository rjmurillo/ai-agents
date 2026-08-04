"""Unit tests for merge-tree ratchet baseline selection and diagnostics."""

from pathlib import Path

from scripts.ci import merge_tree_ratchet_check as _m


class TestEffectiveBaseline:
    """Unit coverage for the ceiling rule itself (issue #4538)."""

    def test_lower_of_the_two_wins_when_the_branch_lowers(self) -> None:
        assert _m._effective_baseline(308, 126) == 126

    def test_lower_of_the_two_wins_when_the_branch_raises(self) -> None:
        assert _m._effective_baseline(10, 100) == 10

    def test_equal_values_return_that_value(self) -> None:
        assert _m._effective_baseline(126, 126) == 126

    def test_unreadable_base_propagates_none(self) -> None:
        assert _m._effective_baseline(None, 126) is None

    def test_unreadable_merged_value_propagates_none(self) -> None:
        assert _m._effective_baseline(308, None) is None

    def test_both_unreadable_propagates_none(self) -> None:
        assert _m._effective_baseline(None, None) is None


class TestCheckOne:
    """Configuration failures identify the unreadable baseline source."""

    def test_unreadable_base_reports_merged_value(self) -> None:
        code, message = _m._check_one("ruff", 0, None, 126)
        assert code == _m.EXIT_CONFIG
        assert message.endswith(
            "baseline unreadable at the base ref (merged tree records 126)"
        )

    def test_unreadable_merged_tree_reports_base_value(self) -> None:
        code, message = _m._check_one("ruff", 0, 308, None)
        assert code == _m.EXIT_CONFIG
        assert message.endswith(
            "baseline unreadable in the merged tree (base ref records 308)"
        )

    def test_both_unreadable_reports_both_sources(self) -> None:
        code, message = _m._check_one("ruff", 0, None, None)
        assert code == _m.EXIT_CONFIG
        assert message.endswith(
            "baseline unreadable at the base ref and in the merged tree"
        )


class TestReadBaselineInTree:
    """The merged-tree reader must not fall back to the checked-out repo."""

    def test_reads_an_integer_from_the_extracted_tree(self, tmp_path: Path) -> None:
        rel = "scripts/ci/ruff_count_baseline.txt"
        (tmp_path / "scripts" / "ci").mkdir(parents=True)
        (tmp_path / rel).write_text("123\n", encoding="utf-8")
        assert _m._read_baseline_in_tree(tmp_path, rel) == 123

    def test_missing_file_returns_none(self, tmp_path: Path) -> None:
        assert _m._read_baseline_in_tree(tmp_path, "scripts/ci/nope.txt") is None

    def test_non_integer_returns_none(self, tmp_path: Path) -> None:
        rel = "scripts/ci/ruff_count_baseline.txt"
        (tmp_path / "scripts" / "ci").mkdir(parents=True)
        (tmp_path / rel).write_text("not-a-number\n", encoding="utf-8")
        assert _m._read_baseline_in_tree(tmp_path, rel) is None
