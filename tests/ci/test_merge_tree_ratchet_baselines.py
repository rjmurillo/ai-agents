"""Unit tests for merge-tree ratchet baseline selection and diagnostics."""

import subprocess
from pathlib import Path
from unittest.mock import patch

from scripts.ci import merge_tree_ratchet_check as _m


def _value(number: int) -> _m.BaselineRead:
    return _m.BaselineRead(_m.BaselineState.VALUE, number)


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
    """Failure diagnostics identify unreadable sources or effective ceilings."""

    def test_new_baseline_missing_from_base_is_allowed(self) -> None:
        code, message = _m._check_one(
            "ruff",
            126,
            _m.BaselineRead(_m.BaselineState.MISSING),
            _value(126),
        )
        assert code == _m.EXIT_OK
        assert message.endswith("126 <= 126.")

    def test_unreadable_merged_tree_reports_base_value(self) -> None:
        code, message = _m._check_one(
            "ruff",
            0,
            _value(308),
            _m.BaselineRead(_m.BaselineState.MISSING),
        )
        assert code == _m.EXIT_CONFIG
        assert message.endswith("baseline missing in merged tree")

    def test_both_unreadable_reports_both_sources(self) -> None:
        code, message = _m._check_one(
            "ruff",
            0,
            _m.BaselineRead(_m.BaselineState.MISSING),
            _m.BaselineRead(_m.BaselineState.MISSING),
        )
        assert code == _m.EXIT_CONFIG
        assert message.endswith("baseline missing in merged tree")

    def test_malformed_base_is_configuration_failure(self) -> None:
        code, message = _m._check_one(
            "ruff",
            0,
            _m.BaselineRead(_m.BaselineState.MALFORMED),
            _value(10),
        )
        assert code == _m.EXIT_CONFIG
        assert message.endswith("malformed baseline in base ref")

    def test_git_failure_is_external_and_preserves_sanitized_detail(self) -> None:
        code, message = _m._check_one(
            "ruff",
            0,
            _m.BaselineRead(
                _m.BaselineState.EXTERNAL,
                diagnostic="fatal: bad ref control removed",
            ),
            _value(10),
        )
        assert code == _m.EXIT_EXTERNAL
        assert message.endswith("fatal: bad ref control removed")

    def test_regression_reports_both_values_and_effective_ceiling(self) -> None:
        code, message = _m._check_one("ruff", 140, _value(308), _value(126))
        assert code == _m.EXIT_REGRESSION
        assert message.endswith(
            "140 > effective baseline 126 (+14); base ref records 308, "
            "merged tree records 126."
        )


class TestReadBaselineInTree:
    """The merged-tree reader must not fall back to the checked-out repo."""

    def test_reads_an_integer_from_the_extracted_tree(self, tmp_path: Path) -> None:
        rel = "scripts/ci/ruff_count_baseline.txt"
        (tmp_path / "scripts" / "ci").mkdir(parents=True)
        (tmp_path / rel).write_text("123\n", encoding="utf-8")
        assert _m._read_baseline_in_tree(tmp_path, rel) == _value(123)

    def test_missing_file_returns_none(self, tmp_path: Path) -> None:
        result = _m._read_baseline_in_tree(tmp_path, "scripts/ci/nope.txt")
        assert result.state is _m.BaselineState.MISSING

    def test_non_integer_returns_none(self, tmp_path: Path) -> None:
        rel = "scripts/ci/ruff_count_baseline.txt"
        (tmp_path / "scripts" / "ci").mkdir(parents=True)
        (tmp_path / rel).write_text("not-a-number\n", encoding="utf-8")
        result = _m._read_baseline_in_tree(tmp_path, rel)
        assert result.state is _m.BaselineState.MALFORMED


def test_git_show_failure_is_external_with_sanitized_stderr(tmp_path: Path) -> None:
    listed = subprocess.CompletedProcess(
        args=["git"], returncode=0, stdout="scripts/ci/x.txt\n", stderr=""
    )
    failed = subprocess.CompletedProcess(
        args=["git"],
        returncode=128,
        stdout="",
        stderr="fatal:\x00 secret\nsecond line",
    )
    with patch.object(_m, "_git", side_effect=[listed, failed]):
        result = _m._read_baseline_at_ref(tmp_path, "a" * 40, "scripts/ci/x.txt")
    assert result.state is _m.BaselineState.EXTERNAL
    assert result.diagnostic == "fatal: secret second line"
