"""Tests for the skillbook CLI: status, confirm, contradict, promote, tension, select."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from scripts.skillbook import EXIT_CONFIG, EXIT_LOGIC, EXIT_OK, main
from tests.skillbook.conftest import make_policy


def _run(skillbook_dir: Path, *args: str) -> int:
    """Invoke the CLI against a skillbook directory."""
    return main(["--skillbook-dir", str(skillbook_dir), *args])


def _load_policies(skillbook_dir: Path) -> list[dict[str, Any]]:
    """Read the policies array back from disk."""
    data = json.loads((skillbook_dir / "policies.json").read_text(encoding="utf-8"))
    return data["policies"]


class TestStatus:
    """The status command lists policies."""

    def test_lists_registered_policies(
        self, write_skillbook: Callable[..., Path], capsys: pytest.CaptureFixture[str]
    ) -> None:
        skillbook = write_skillbook(policies=[make_policy("pol-a")])
        assert _run(skillbook, "status") == EXIT_OK
        assert "pol-a" in capsys.readouterr().out

    def test_json_output_is_parseable(
        self, write_skillbook: Callable[..., Path], capsys: pytest.CaptureFixture[str]
    ) -> None:
        skillbook = write_skillbook(policies=[make_policy("pol-a")])
        assert _run(skillbook, "status", "--json") == EXIT_OK
        payload = json.loads(capsys.readouterr().out)
        assert payload[0]["id"] == "pol-a"

    def test_empty_registry_reports_none(
        self, write_skillbook: Callable[..., Path], capsys: pytest.CaptureFixture[str]
    ) -> None:
        skillbook = write_skillbook(policies=[])
        assert _run(skillbook, "status") == EXIT_OK
        assert "No policies" in capsys.readouterr().out

    def test_missing_file_is_config_error(self, tmp_path: Path) -> None:
        # No skillbook files written: status must report a config error.
        assert _run(tmp_path, "status") == EXIT_CONFIG


class TestConfirmContradict:
    """confirm and contradict append eval-grounded evidence."""

    def test_confirm_appends_confirmed_evidence(
        self, write_skillbook: Callable[..., Path]
    ) -> None:
        skillbook = write_skillbook(policies=[make_policy("pol-a")])
        assert _run(skillbook, "confirm", "pol-a", "--eval", "run::F0") == EXIT_OK
        policy = _load_policies(skillbook)[0]
        assert policy["evidence"][0]["type"] == "confirmed"
        assert policy["confirms"] == 1.0

    def test_contradict_appends_contradicted_evidence_with_reason(
        self, write_skillbook: Callable[..., Path]
    ) -> None:
        skillbook = write_skillbook(policies=[make_policy("pol-a")])
        exit_code = _run(
            skillbook,
            "contradict",
            "pol-a",
            "--eval",
            "run::F1",
            "--reason",
            "fixture failed",
        )
        assert exit_code == EXIT_OK
        policy = _load_policies(skillbook)[0]
        assert policy["evidence"][0]["type"] == "contradicted"
        assert policy["evidence"][0]["reason"] == "fixture failed"

    def test_confirm_unknown_policy_is_logic_error(
        self, write_skillbook: Callable[..., Path]
    ) -> None:
        skillbook = write_skillbook(policies=[make_policy("pol-a")])
        assert _run(skillbook, "confirm", "pol-missing", "--eval", "e1") == EXIT_LOGIC

    def test_confirm_is_idempotent_on_eval_id(
        self, write_skillbook: Callable[..., Path]
    ) -> None:
        skillbook = write_skillbook(policies=[make_policy("pol-a")])
        _run(skillbook, "confirm", "pol-a", "--eval", "run::F0")
        _run(skillbook, "confirm", "pol-a", "--eval", "run::F0")
        policy = _load_policies(skillbook)[0]
        assert policy["application_count"] == 1

    def test_self_referential_evidence_is_discounted(
        self, write_skillbook: Callable[..., Path]
    ) -> None:
        skillbook = write_skillbook(policies=[make_policy("pol-a")])
        _run(
            skillbook,
            "confirm",
            "pol-a",
            "--eval",
            "self-1",
            "--context-type",
            "self-referential",
        )
        assert _load_policies(skillbook)[0]["confirms"] == 0.25


class TestPromote:
    """The promote command re-evaluates tiers and statuses."""

    def test_promote_raises_tier_after_enough_confirms(
        self, write_skillbook: Callable[..., Path]
    ) -> None:
        skillbook = write_skillbook(policies=[make_policy("pol-a", tier="hypothesis")])
        for index in range(5):
            _run(skillbook, "confirm", "pol-a", "--eval", f"run::F{index}")
        assert _run(skillbook, "promote") == EXIT_OK
        assert _load_policies(skillbook)[0]["tier"] == "validated"

    def test_promote_with_no_changes_reports_noop(
        self, write_skillbook: Callable[..., Path], capsys: pytest.CaptureFixture[str]
    ) -> None:
        skillbook = write_skillbook(policies=[make_policy("pol-a")])
        assert _run(skillbook, "promote") == EXIT_OK
        assert "No policy" in capsys.readouterr().out


class TestTension:
    """tension list and tension prefer."""

    def _tension_skillbook(self, write_skillbook: Callable[..., Path]) -> Path:
        return write_skillbook(
            policies=[make_policy("pol-a"), make_policy("pol-b")],
            tensions=[
                {
                    "id": "ten-a-b",
                    "policy_a": "pol-a",
                    "policy_b": "pol-b",
                    "preferred_in_context": {},
                    "status": "holding",
                    "detected_at": 1778976000,
                }
            ],
        )

    def test_list_shows_tensions(
        self, write_skillbook: Callable[..., Path], capsys: pytest.CaptureFixture[str]
    ) -> None:
        skillbook = self._tension_skillbook(write_skillbook)
        assert _run(skillbook, "tension", "list") == EXIT_OK
        assert "ten-a-b" in capsys.readouterr().out

    def test_list_empty_reports_none(
        self, write_skillbook: Callable[..., Path], capsys: pytest.CaptureFixture[str]
    ) -> None:
        skillbook = write_skillbook(tensions=[])
        assert _run(skillbook, "tension", "list") == EXIT_OK
        assert "No tensions" in capsys.readouterr().out

    def test_prefer_records_context_resolution(
        self, write_skillbook: Callable[..., Path]
    ) -> None:
        skillbook = self._tension_skillbook(write_skillbook)
        exit_code = _run(
            skillbook, "tension", "prefer", "ten-a-b", "bug_repro", "pol-b",
            "--eval", "run::F0",
        )
        assert exit_code == EXIT_OK
        data = json.loads((skillbook / "tensions.json").read_text(encoding="utf-8"))
        resolution = data["tensions"][0]["preferred_in_context"]["bug_repro"]
        assert resolution["preferred"] == "pol-b"
        assert resolution["confirmed_count"] == 1

    def test_prefer_unknown_tension_is_logic_error(
        self, write_skillbook: Callable[..., Path]
    ) -> None:
        skillbook = self._tension_skillbook(write_skillbook)
        exit_code = _run(
            skillbook, "tension", "prefer", "ten-missing", "ctx", "pol-a",
            "--eval", "e1",
        )
        assert exit_code == EXIT_LOGIC

    def test_prefer_policy_outside_tension_is_logic_error(
        self, write_skillbook: Callable[..., Path]
    ) -> None:
        skillbook = self._tension_skillbook(write_skillbook)
        # pol-c is not part of ten-a-b.
        exit_code = _run(
            skillbook, "tension", "prefer", "ten-a-b", "ctx", "pol-c",
            "--eval", "e1",
        )
        assert exit_code == EXIT_LOGIC


class TestSelect:
    """select returns an agent's active policies with tension resolution."""

    def test_returns_agent_and_shared_policies(
        self, write_skillbook: Callable[..., Path], capsys: pytest.CaptureFixture[str]
    ) -> None:
        skillbook = write_skillbook(
            policies=[
                make_policy("pol-arch", owner_agent="architect"),
                make_policy("pol-shared-x", owner_agent="shared"),
                make_policy("pol-sec", owner_agent="security"),
            ]
        )
        assert _run(skillbook, "select", "architect", "greenfield") == EXIT_OK
        out = capsys.readouterr().out
        assert "pol-arch" in out
        assert "pol-shared-x" in out
        assert "pol-sec" not in out

    def test_hides_retired_policies(
        self, write_skillbook: Callable[..., Path], capsys: pytest.CaptureFixture[str]
    ) -> None:
        skillbook = write_skillbook(
            policies=[
                make_policy("pol-live", owner_agent="qa"),
                make_policy("pol-dead", owner_agent="qa", status="retired"),
            ]
        )
        _run(skillbook, "select", "qa", "any")
        out = capsys.readouterr().out
        assert "pol-live" in out
        assert "pol-dead" not in out

    def test_questioning_policies_listed_after_active(
        self, write_skillbook: Callable[..., Path]
    ) -> None:
        skillbook = write_skillbook(
            policies=[
                make_policy("pol-q", owner_agent="qa", tier="validated",
                            status="questioning"),
                make_policy("pol-ok", owner_agent="qa", status="active"),
            ]
        )
        assert _run(skillbook, "select", "qa", "any", "--json") == EXIT_OK

    def test_select_json_orders_active_before_questioning(
        self, write_skillbook: Callable[..., Path], capsys: pytest.CaptureFixture[str]
    ) -> None:
        skillbook = write_skillbook(
            policies=[
                make_policy("pol-q", owner_agent="qa", tier="validated",
                            status="questioning"),
                make_policy("pol-ok", owner_agent="qa", status="active"),
            ]
        )
        _run(skillbook, "select", "qa", "any", "--json")
        results = json.loads(capsys.readouterr().out)
        assert [r["id"] for r in results] == ["pol-ok", "pol-q"]

    def test_select_works_without_a_tensions_file(
        self, write_skillbook: Callable[..., Path], capsys: pytest.CaptureFixture[str]
    ) -> None:
        # An absent tensions table just means no resolution annotations.
        skillbook = write_skillbook(policies=[make_policy("pol-a", owner_agent="qa")])
        (skillbook / "tensions.json").unlink()
        assert _run(skillbook, "select", "qa", "any") == EXIT_OK
        assert "pol-a" in capsys.readouterr().out

    def test_select_annotates_tension_resolution(
        self, write_skillbook: Callable[..., Path], capsys: pytest.CaptureFixture[str]
    ) -> None:
        skillbook = write_skillbook(
            policies=[
                make_policy("pol-a", owner_agent="architect"),
                make_policy("pol-b", owner_agent="architect"),
            ],
            tensions=[
                {
                    "id": "ten-a-b",
                    "policy_a": "pol-a",
                    "policy_b": "pol-b",
                    "preferred_in_context": {
                        "bug_repro": {
                            "preferred": "pol-b",
                            "confirmed_count": 1,
                            "evidence": ["run::F0"],
                        }
                    },
                    "status": "holding",
                    "detected_at": 1778976000,
                }
            ],
        )
        _run(skillbook, "select", "architect", "bug_repro", "--json")
        results = json.loads(capsys.readouterr().out)
        verdicts = {r["id"]: r["tension"]["verdict"] for r in results}
        assert verdicts["pol-b"] == "wins"
        assert verdicts["pol-a"] == "yields"

    def test_select_marks_unresolved_tension(
        self, write_skillbook: Callable[..., Path], capsys: pytest.CaptureFixture[str]
    ) -> None:
        skillbook = write_skillbook(
            policies=[
                make_policy("pol-a", owner_agent="architect"),
                make_policy("pol-b", owner_agent="architect"),
            ],
            tensions=[
                {
                    "id": "ten-a-b",
                    "policy_a": "pol-a",
                    "policy_b": "pol-b",
                    "preferred_in_context": {},
                    "status": "holding",
                    "detected_at": 1778976000,
                }
            ],
        )
        assert _run(skillbook, "select", "architect", "novel_context") == EXIT_OK
        assert "unresolved" in capsys.readouterr().out


class TestCorruptInput:
    """Corrupt registry files surface as logic errors, not crashes."""

    def test_confirm_on_corrupt_policies_file_is_logic_error(
        self, write_skillbook: Callable[..., Path]
    ) -> None:
        skillbook = write_skillbook(policies=[make_policy("pol-a")])
        (skillbook / "policies.json").write_text("{ not json", encoding="utf-8")
        assert _run(skillbook, "confirm", "pol-a", "--eval", "e1") == EXIT_LOGIC

    def test_status_on_corrupt_policies_file_is_logic_error(
        self, write_skillbook: Callable[..., Path]
    ) -> None:
        skillbook = write_skillbook(policies=[make_policy("pol-a")])
        (skillbook / "policies.json").write_text("garbage", encoding="utf-8")
        assert _run(skillbook, "status") == EXIT_LOGIC
