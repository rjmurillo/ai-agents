"""Tests for the post-eval hook that turns eval outcomes into skillbook evidence."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from scripts.skillbook import EXIT_CONFIG, EXIT_LOGIC, EXIT_OK
from tests.skillbook.conftest import make_policy


def _write_run(tmp_path: Path, run_id: str, records: list[dict[str, Any]]) -> Path:
    """Create an eval run directory with a runs.jsonl file."""
    run_dir = tmp_path / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    lines = "\n".join(json.dumps(record) for record in records)
    (run_dir / "runs.jsonl").write_text(lines + "\n", encoding="utf-8")
    return run_dir


def _write_fixtures(tmp_path: Path, mapping: dict[str, str | None]) -> Path:
    """Create a fixtures directory; mapping is fixture_id -> policy_id (or None)."""
    fixtures_dir = tmp_path / "fixtures"
    fixtures_dir.mkdir(parents=True, exist_ok=True)
    for fixture_id, policy_id in mapping.items():
        fixture: dict[str, Any] = {"schemaVersion": 1, "id": fixture_id}
        if policy_id is not None:
            fixture["policy_id"] = policy_id
        (fixtures_dir / f"{fixture_id}.json").write_text(
            json.dumps(fixture), encoding="utf-8"
        )
    return fixtures_dir


class TestAggregateFixtureOutcomes:
    """aggregate_fixture_outcomes collapses per-trial records into per-fixture results."""

    def test_majority_pass_marks_fixture_passed(
        self, post_eval_module: ModuleType, tmp_path: Path
    ) -> None:
        run_dir = _write_run(
            tmp_path,
            "run-x",
            [
                {"fixture_id": "F0", "passed": True},
                {"fixture_id": "F0", "passed": True},
                {"fixture_id": "F0", "passed": False},
            ],
        )
        outcomes = post_eval_module.aggregate_fixture_outcomes(run_dir / "runs.jsonl")
        assert outcomes == {"F0": True}

    def test_tie_does_not_count_as_passed(
        self, post_eval_module: ModuleType, tmp_path: Path
    ) -> None:
        # A 1-1 split is not a strict majority, so the fixture did not pass.
        run_dir = _write_run(
            tmp_path,
            "run-x",
            [
                {"fixture_id": "F0", "passed": True},
                {"fixture_id": "F0", "passed": False},
            ],
        )
        outcomes = post_eval_module.aggregate_fixture_outcomes(run_dir / "runs.jsonl")
        assert outcomes == {"F0": False}

    def test_record_without_fixture_id_raises(
        self, post_eval_module: ModuleType, tmp_path: Path
    ) -> None:
        run_dir = _write_run(tmp_path, "run-x", [{"passed": True}])
        with pytest.raises(ValueError, match="fixture_id"):
            post_eval_module.aggregate_fixture_outcomes(run_dir / "runs.jsonl")


class TestApplyEvalRun:
    """apply_eval_run logs evidence for tagged fixtures and runs promotion."""

    def test_passing_fixture_confirms_its_policy(
        self,
        post_eval_module: ModuleType,
        write_skillbook: Callable[..., Path],
        tmp_path: Path,
    ) -> None:
        skillbook = write_skillbook(policies=[make_policy("pol-a")])
        run_dir = _write_run(tmp_path, "run-1", [{"fixture_id": "F0", "passed": True}])
        fixtures = _write_fixtures(tmp_path, {"F0": "pol-a"})

        summary = post_eval_module.apply_eval_run(
            run_dir / "runs.jsonl", fixtures, skillbook, "run-1", now=9000
        )
        assert summary["confirmed"] == ["pol-a"]
        policy = json.loads(
            (skillbook / "policies.json").read_text(encoding="utf-8")
        )["policies"][0]
        assert policy["confirms"] == 1.0
        assert policy["evidence"][0]["eval_id"] == "run-1::F0"

    def test_failing_fixture_contradicts_its_policy(
        self,
        post_eval_module: ModuleType,
        write_skillbook: Callable[..., Path],
        tmp_path: Path,
    ) -> None:
        skillbook = write_skillbook(policies=[make_policy("pol-a")])
        run_dir = _write_run(tmp_path, "run-1", [{"fixture_id": "F0", "passed": False}])
        fixtures = _write_fixtures(tmp_path, {"F0": "pol-a"})

        summary = post_eval_module.apply_eval_run(
            run_dir / "runs.jsonl", fixtures, skillbook, "run-1", now=9000
        )
        assert summary["contradicted"] == ["pol-a"]

    def test_untagged_fixture_is_skipped(
        self,
        post_eval_module: ModuleType,
        write_skillbook: Callable[..., Path],
        tmp_path: Path,
    ) -> None:
        skillbook = write_skillbook(policies=[make_policy("pol-a")])
        run_dir = _write_run(tmp_path, "run-1", [{"fixture_id": "F9", "passed": True}])
        fixtures = _write_fixtures(tmp_path, {"F9": None})

        summary = post_eval_module.apply_eval_run(
            run_dir / "runs.jsonl", fixtures, skillbook, "run-1", now=9000
        )
        assert summary["skipped_untagged"] == ["F9"]
        assert summary["confirmed"] == []

    def test_unknown_policy_is_skipped(
        self,
        post_eval_module: ModuleType,
        write_skillbook: Callable[..., Path],
        tmp_path: Path,
    ) -> None:
        skillbook = write_skillbook(policies=[make_policy("pol-a")])
        run_dir = _write_run(tmp_path, "run-1", [{"fixture_id": "F0", "passed": True}])
        fixtures = _write_fixtures(tmp_path, {"F0": "pol-ghost"})

        summary = post_eval_module.apply_eval_run(
            run_dir / "runs.jsonl", fixtures, skillbook, "run-1", now=9000
        )
        assert summary["skipped_unknown_policy"] == ["F0:pol-ghost"]

    def test_five_passing_fixtures_promote_policy_to_validated(
        self,
        post_eval_module: ModuleType,
        write_skillbook: Callable[..., Path],
        tmp_path: Path,
    ) -> None:
        skillbook = write_skillbook(
            policies=[make_policy("pol-a", tier="hypothesis")]
        )
        records = [{"fixture_id": f"F{i}", "passed": True} for i in range(5)]
        run_dir = _write_run(tmp_path, "run-1", records)
        fixtures = _write_fixtures(tmp_path, {f"F{i}": "pol-a" for i in range(5)})

        summary = post_eval_module.apply_eval_run(
            run_dir / "runs.jsonl", fixtures, skillbook, "run-1", now=9000
        )
        assert summary["promoted"] == ["pol-a"]
        policy = json.loads(
            (skillbook / "policies.json").read_text(encoding="utf-8")
        )["policies"][0]
        assert policy["tier"] == "validated"

    def test_reapplying_same_run_is_idempotent(
        self,
        post_eval_module: ModuleType,
        write_skillbook: Callable[..., Path],
        tmp_path: Path,
    ) -> None:
        skillbook = write_skillbook(policies=[make_policy("pol-a")])
        run_dir = _write_run(tmp_path, "run-1", [{"fixture_id": "F0", "passed": True}])
        fixtures = _write_fixtures(tmp_path, {"F0": "pol-a"})

        post_eval_module.apply_eval_run(
            run_dir / "runs.jsonl", fixtures, skillbook, "run-1", now=9000
        )
        second = post_eval_module.apply_eval_run(
            run_dir / "runs.jsonl", fixtures, skillbook, "run-1", now=9100
        )
        assert second["confirmed"] == []
        policy = json.loads(
            (skillbook / "policies.json").read_text(encoding="utf-8")
        )["policies"][0]
        assert policy["application_count"] == 1


class TestPostEvalMain:
    """The post-eval CLI entry point and its exit codes."""

    def test_exit_ok_on_valid_run(
        self,
        post_eval_module: ModuleType,
        write_skillbook: Callable[..., Path],
        tmp_path: Path,
    ) -> None:
        skillbook = write_skillbook(policies=[make_policy("pol-a")])
        run_dir = _write_run(tmp_path, "run-1", [{"fixture_id": "F0", "passed": True}])
        fixtures = _write_fixtures(tmp_path, {"F0": "pol-a"})

        exit_code = post_eval_module.main(
            [
                "--run",
                str(run_dir),
                "--fixtures",
                str(fixtures),
                "--skillbook-dir",
                str(skillbook),
            ]
        )
        assert exit_code == EXIT_OK

    def test_exit_config_when_run_dir_missing(
        self, post_eval_module: ModuleType, tmp_path: Path
    ) -> None:
        exit_code = post_eval_module.main(
            [
                "--run",
                str(tmp_path / "no-such-run"),
                "--fixtures",
                str(tmp_path),
            ]
        )
        assert exit_code == EXIT_CONFIG

    def test_exit_config_when_fixtures_dir_missing(
        self, post_eval_module: ModuleType, tmp_path: Path
    ) -> None:
        run_dir = _write_run(tmp_path, "run-1", [{"fixture_id": "F0", "passed": True}])
        exit_code = post_eval_module.main(
            [
                "--run",
                str(run_dir),
                "--fixtures",
                str(tmp_path / "no-such-fixtures"),
            ]
        )
        assert exit_code == EXIT_CONFIG

    def test_exit_logic_on_malformed_run_records(
        self,
        post_eval_module: ModuleType,
        write_skillbook: Callable[..., Path],
        tmp_path: Path,
    ) -> None:
        skillbook = write_skillbook(policies=[make_policy("pol-a")])
        run_dir = _write_run(tmp_path, "run-1", [{"passed": True}])  # no fixture_id
        fixtures = _write_fixtures(tmp_path, {"F0": "pol-a"})
        exit_code = post_eval_module.main(
            [
                "--run",
                str(run_dir),
                "--fixtures",
                str(fixtures),
                "--skillbook-dir",
                str(skillbook),
            ]
        )
        assert exit_code == EXIT_LOGIC
