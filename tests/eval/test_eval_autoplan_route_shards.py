"""Tests for loading the autoplan route eval fixtures from a shard directory.

Split from `test_eval_autoplan_routes.py` at the 500-line file-size limit.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from tests.eval.test_eval_autoplan_routes import _scenario, ev


def _shard(directory: Path, name: str, *scenarios: dict[str, Any]) -> None:
    directory.mkdir(exist_ok=True)
    payload = {"schema_version": 1, "scenarios": list(scenarios)}
    (directory / name).write_text(json.dumps(payload), encoding="utf-8")


def test_directory_loads_every_shard_in_name_order(tmp_path: Path) -> None:
    shards = tmp_path / "routes"
    _shard(shards, "b.json", _scenario(id="from-b"))
    _shard(shards, "a.json", _scenario(id="from-a"))
    (shards / "notes.txt").write_text("not a shard", encoding="utf-8")
    assert [s.id for s in ev.load_scenarios(shards)] == ["from-a", "from-b"]


def test_duplicate_id_across_shards_fails(tmp_path: Path) -> None:
    shards = tmp_path / "routes"
    _shard(shards, "a.json", _scenario(id="same"))
    _shard(shards, "b.json", _scenario(id="same"))
    with pytest.raises(
        ev.EvalConfigError, match=r"duplicate scenario ids across shards: \['same'\]"
    ):
        ev.load_scenarios(shards)


def test_empty_directory_fails(tmp_path: Path) -> None:
    with pytest.raises(ev.EvalConfigError, match="no \\*.json fixture files"):
        ev.load_scenarios(tmp_path)


def test_bad_shard_names_its_file(tmp_path: Path) -> None:
    shards = tmp_path / "routes"
    _shard(shards, "a.json", _scenario(id="ok"))
    (shards / "b.json").write_text("{", encoding="utf-8")
    with pytest.raises(ev.EvalConfigError, match="b.json"):
        ev.load_scenarios(shards)


def test_shipped_adr_shard_routes_plan_steps_to_adr_generator() -> None:
    shard = ev.load_scenarios(ev.DEFAULT_FIXTURES / "adr-generator.json")
    positives = [s for s in shard if s.kind == "specialist"]
    assert positives and all(ev.bare(s.route) == "adr-generator" for s in positives)
    assert any(s.kind == "none" for s in shard)
