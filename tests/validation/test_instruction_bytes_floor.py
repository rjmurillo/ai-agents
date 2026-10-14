"""Headroom floor for instruction_bytes (issue #6480)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from scripts.validation import instruction_bytes as ib
from scripts.validation.instruction_budget_constants import FIXTURE_HEADROOM_FLOOR_BYTES
from scripts.validation.instruction_bytes_report import format_table
from tests.validation._instruction_bytes_helpers import FIXTURE, build_repo, commit_all, init_git


@pytest.fixture
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    build_repo(tmp_path)
    monkeypatch.setattr(ib, "FIXTURES", (FIXTURE,))
    monkeypatch.setattr(ib, "FIXTURE_CEILINGS_BYTES", {"T1": 1_000_000})
    return tmp_path


def _floor_report(
    bytes_: int, ceiling: int | None, growth: int | None, fid: str = "A"
) -> dict[str, Any]:
    """A minimal report: one fixture, optionally with a base delta of ``growth`` bytes."""
    report: dict[str, Any] = {"fixtures": {fid: {"bytes": bytes_, "ceiling_bytes": ceiling}}}
    if growth is not None:
        report["delta"] = {"metrics": [{"name": f"fixtures.{fid}.bytes", "delta": growth}]}
    return report


class TestHeadroomFloor:
    """Issue #6480: a PR may not grow a fixture into the headroom floor."""

    def test_the_shipped_floor_is_one_hundred_bytes(self) -> None:
        assert FIXTURE_HEADROOM_FLOOR_BYTES == 100

    def test_below_the_floor_after_growth_is_named(self) -> None:
        got = ib.fixture_floor_breaches(_floor_report(9_950, 10_000, 5), 100)
        assert got == ["A: grew 5 bytes and leaves 50 bytes of headroom, under the 100 byte floor"]

    def test_headroom_equal_to_the_floor_passes(self) -> None:
        assert ib.fixture_floor_breaches(_floor_report(9_900, 10_000, 5), 100) == []

    def test_headroom_one_byte_under_the_floor_is_named(self) -> None:
        assert len(ib.fixture_floor_breaches(_floor_report(9_901, 10_000, 1), 100)) == 1

    def test_above_the_floor_after_growth_passes(self) -> None:
        assert ib.fixture_floor_breaches(_floor_report(9_000, 10_000, 500), 100) == []

    def test_a_fixture_already_under_the_floor_that_did_not_grow_passes(self) -> None:
        assert ib.fixture_floor_breaches(_floor_report(9_950, 10_000, 0), 100) == []

    def test_a_fixture_already_under_the_floor_that_shrank_passes(self) -> None:
        assert ib.fixture_floor_breaches(_floor_report(9_950, 10_000, -20), 100) == []

    def test_without_a_base_delta_nothing_is_named(self) -> None:
        assert ib.fixture_floor_breaches(_floor_report(9_950, 10_000, None), 100) == []

    def test_a_fixture_over_its_ceiling_is_left_to_the_ceiling_check(self) -> None:
        assert ib.fixture_floor_breaches(_floor_report(10_001, 10_000, 5), 100) == []

    def test_headroom_of_exactly_zero_after_growth_is_named(self) -> None:
        assert len(ib.fixture_floor_breaches(_floor_report(10_000, 10_000, 5), 100)) == 1

    def test_a_fixture_with_no_ceiling_is_skipped(self) -> None:
        assert ib.fixture_floor_breaches(_floor_report(9_950, None, 5), 100) == []

    def test_an_errored_fixture_is_skipped(self) -> None:
        report = {
            "fixtures": {"A": {"name": "n", "error": "x"}},
            "delta": {"metrics": []},
        }
        assert ib.fixture_floor_breaches(report, 100) == []

    def test_a_fixture_missing_from_the_delta_is_treated_as_unchanged(self) -> None:
        report = _floor_report(9_950, 10_000, 5, fid="A")
        report["delta"]["metrics"] = []
        assert ib.fixture_floor_breaches(report, 100) == []

    def test_a_zero_reserve_disables_the_floor(self) -> None:
        assert ib.fixture_floor_breaches(_floor_report(9_999, 10_000, 5), 0) == []

    def test_the_default_reserve_is_the_shipped_floor(self) -> None:
        under = 10_000 - FIXTURE_HEADROOM_FLOOR_BYTES + 1
        assert len(ib.fixture_floor_breaches(_floor_report(under, 10_000, 1))) == 1

    def test_names_every_fixture_in_sorted_order(self) -> None:
        report = {
            "fixtures": {
                "B": {"bytes": 95, "ceiling_bytes": 100},
                "A": {"bytes": 95, "ceiling_bytes": 100},
            },
            "delta": {
                "metrics": [
                    {"name": "fixtures.A.bytes", "delta": 1},
                    {"name": "fixtures.B.bytes", "delta": 1},
                ]
            },
        }
        assert [b.split(":")[0] for b in ib.fixture_floor_breaches(report, 100)] == ["A", "B"]


class TestHeadroomFloorCli:
    def _grow_into_floor(
        self, repo: Path, monkeypatch: pytest.MonkeyPatch, grow: bool = True
    ) -> str:
        """Commit a base, then optionally add 50 bytes to a skill T1 loads."""
        init_git(repo)
        base_sha = commit_all(repo, "base")
        if grow:
            beta = repo / ".claude/skills/beta/SKILL.md"
            beta.write_text(beta.read_text(encoding="utf-8") + "x" * 50, encoding="utf-8")
        return base_sha

    def _set_ceiling_with_headroom(
        self, repo: Path, monkeypatch: pytest.MonkeyPatch, headroom: int
    ) -> None:
        total = _measure_t1(repo)
        monkeypatch.setattr(ib, "FIXTURE_CEILINGS_BYTES", {"T1": total + headroom})

    def test_growth_into_the_floor_fails_in_ci_mode(
        self, repo: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        base_sha = self._grow_into_floor(repo, monkeypatch)
        self._set_ceiling_with_headroom(repo, monkeypatch, 50)
        capsys.readouterr()
        assert ib.main(["--path", str(repo), "--ci", "--base-ref", base_sha]) == 1
        assert "FAIL: fixture headroom floor breached" in capsys.readouterr().out

    def test_growth_into_the_floor_only_reports_outside_ci_mode(
        self, repo: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        base_sha = self._grow_into_floor(repo, monkeypatch)
        self._set_ceiling_with_headroom(repo, monkeypatch, 50)
        monkeypatch.delenv("CI", raising=False)
        capsys.readouterr()
        assert ib.main(["--path", str(repo), "--base-ref", base_sha]) == 0
        assert "FAIL: fixture headroom floor breached" in capsys.readouterr().out

    def test_growth_leaving_headroom_above_the_floor_passes(
        self, repo: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        base_sha = self._grow_into_floor(repo, monkeypatch)
        self._set_ceiling_with_headroom(repo, monkeypatch, 500)
        assert ib.main(["--path", str(repo), "--ci", "--base-ref", base_sha]) == 0

    def test_a_fixture_under_the_floor_with_no_growth_passes(
        self, repo: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        base_sha = self._grow_into_floor(repo, monkeypatch, grow=False)
        self._set_ceiling_with_headroom(repo, monkeypatch, 50)
        assert ib.main(["--path", str(repo), "--ci", "--base-ref", base_sha]) == 0

    def test_without_a_base_ref_the_floor_is_not_enforced(
        self, repo: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        self._set_ceiling_with_headroom(repo, monkeypatch, 50)
        assert ib.main(["--path", str(repo), "--ci"]) == 0

    def test_the_reserve_flag_lowers_the_floor(
        self, repo: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        base_sha = self._grow_into_floor(repo, monkeypatch)
        self._set_ceiling_with_headroom(repo, monkeypatch, 50)
        argv = ["--path", str(repo), "--ci", "--base-ref", base_sha, "--reserve", "10"]
        assert ib.main(argv) == 0

    def test_the_environment_overrides_the_default_reserve(
        self, repo: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        base_sha = self._grow_into_floor(repo, monkeypatch)
        self._set_ceiling_with_headroom(repo, monkeypatch, 50)
        monkeypatch.setenv("INSTRUCTION_BYTES_RESERVE", "0")
        assert ib.main(["--path", str(repo), "--ci", "--base-ref", base_sha]) == 0

    def test_the_json_report_lists_floor_breaches(
        self, repo: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        base_sha = self._grow_into_floor(repo, monkeypatch)
        self._set_ceiling_with_headroom(repo, monkeypatch, 50)
        capsys.readouterr()
        ib.main(["--path", str(repo), "--format", "json", "--base-ref", base_sha])
        breaches = json.loads(capsys.readouterr().out)["floor_breaches"]
        assert len(breaches) == 1
        assert breaches[0].startswith("T1: grew ")

    def test_a_negative_reserve_is_rejected(self) -> None:
        with pytest.raises(SystemExit) as exc:
            ib.build_parser().parse_args(["--reserve", "-1"])
        assert exc.value.code == 2


def _measure_t1(root: Path) -> int:
    """Return the activated bytes of the synthetic fixture T1 at ``root``."""
    report = ib.build_report(root)
    return int(report["fixtures"]["T1"]["bytes"])


class TestFloorRendering:
    def _report(self) -> dict[str, Any]:
        return {
            "estimator": "e",
            "canonical": {
                "groups": {"g": {"files": 1, "bytes": 2, "tokens": 3}},
                "total": {"files": 1, "bytes": 2, "tokens": 3},
                "top_contributors": [],
            },
            "generated": {"families": {}, "total": {"files": 0, "bytes": 0, "tokens": 0}},
            "always_on": {"claude_code": {"files": 1, "bytes": 2, "tokens": 3}},
            "fixtures": {},
            "ceiling_breaches": [],
            "findings": [],
        }

    def test_floor_breaches_render_a_fail_block(self) -> None:
        report = self._report()
        report["floor_breaches"] = ["A: grew 5 bytes and leaves 4 bytes of headroom"]
        out = format_table(report)
        assert "FAIL: fixture headroom floor breached\n  A: grew 5 bytes" in out

    def test_no_floor_breaches_renders_no_floor_block(self) -> None:
        report = self._report()
        report["floor_breaches"] = []
        assert "headroom floor" not in format_table(report)
