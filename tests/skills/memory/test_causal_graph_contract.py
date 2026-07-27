"""The causal graph, its schema, and its two writers must agree.

Before #3356 they did not. The schema required node ids matching ``^n\\d{3,}$``
and allowed five node types; the live writer emitted 12-hex ids and seven types.
Every one of the 1861 committed nodes violated the contract, and nothing failed,
because the only validator in the tree checked top-level keys and never
descended into the arrays.

These tests make each half of that drift fail the build:

* the shipped graph is validated against the shipped schema, so data drift is
  visible;
* the writer's accepted type set is compared to the schema's enum, so code
  drift is visible;
* the retired writer's path to the live writer is resolved, so a rename cannot
  silently restore a second identity scheme.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import jsonschema
import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
SKILL_ROOT = REPO_ROOT / ".claude" / "skills" / "memory"
SCHEMA_FILE = SKILL_ROOT / "resources" / "schemas" / "causal-graph.schema.json"
GRAPH_FILE = REPO_ROOT / ".agents" / "memory" / "causality" / "causal-graph.json"
WRITER_FILE = SKILL_ROOT / "scripts" / "update_causal_graph.py"


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_writer() -> Any:
    spec = importlib.util.spec_from_file_location("_ucg_contract", WRITER_FILE)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def schema() -> Any:
    return _load(SCHEMA_FILE)


@pytest.fixture(scope="module")
def graph() -> Any:
    return _load(GRAPH_FILE)


class TestTheShippedSchemaIsUsable:
    def test_the_schema_is_a_valid_draft_07_schema(self, schema: Any) -> None:
        jsonschema.Draft7Validator.check_schema(schema)

    def test_the_schema_constrains_the_arrays_it_declares(
        self, schema: Any
    ) -> None:
        # A bare {"type": "array"} passes anything. That is how 1861 bad rows
        # went unnoticed, so the contract must reach the items.
        for section in ("nodes", "edges", "patterns"):
            items = schema["properties"][section].get("items")
            assert items, f"{section} declares no item schema"
            assert items.get("required"), f"{section} items require nothing"


class TestTheShippedGraphMatchesTheShippedSchema:
    def test_the_graph_is_not_empty(self, graph: Any) -> None:
        # Without this an emptied graph would make the next test vacuous.
        assert len(graph["nodes"]) > 100
        assert len(graph["edges"]) > 0
        assert len(graph["patterns"]) > 0

    def test_the_graph_validates_with_zero_errors(
        self, graph: Any, schema: Any
    ) -> None:
        errors = sorted(
            jsonschema.Draft7Validator(schema).iter_errors(graph),
            key=lambda err: list(err.absolute_path),
        )
        rendered = "\n".join(
            f"{'/'.join(str(part) for part in err.absolute_path)}: {err.message}"
            for err in errors[:20]
        )
        assert not errors, f"{len(errors)} schema violations:\n{rendered}"


class TestTheWriterAndTheSchemaAgree:
    def test_the_accepted_node_types_are_exactly_the_schema_enum(
        self, schema: Any
    ) -> None:
        writer = _load_writer()
        enum = set(schema["properties"]["nodes"]["items"]["properties"]["type"]["enum"])
        assert set(writer.NODE_TYPES) == enum

    def test_generated_ids_match_the_schema_pattern(self, schema: Any) -> None:
        writer = _load_writer()
        pattern = schema["properties"]["nodes"]["items"]["properties"]["id"]["pattern"]
        validator = jsonschema.Draft7Validator(
            {"type": "string", "pattern": pattern}
        )
        for node_type in sorted(writer.NODE_TYPES):
            validator.validate(writer.generate_node_id(node_type, "a label"))

    def test_generated_pattern_ids_match_the_schema_pattern(
        self, schema: Any
    ) -> None:
        writer = _load_writer()
        pattern = schema["properties"]["patterns"]["items"]["properties"]["id"][
            "pattern"
        ]
        jsonschema.Draft7Validator({"type": "string", "pattern": pattern}).validate(
            writer.generate_pattern_id("some pattern")
        )


class TestTheRetiredWriterBorrowsTheLiveIdentity:
    def test_it_can_still_reach_the_live_writer(self) -> None:
        sys.path.insert(0, str(SKILL_ROOT))
        try:
            from memory_core import reflexion_memory
        finally:
            sys.path.pop(0)

        live = reflexion_memory._live_writer()
        assert live.generate_node_id(
            "decision", "shared"
        ) == _load_writer().generate_node_id("decision", "shared")

    def test_it_no_longer_allocates_sequential_ids(self) -> None:
        source = (
            SKILL_ROOT / "memory_core" / "reflexion_memory.py"
        ).read_text(encoding="utf-8")
        # The old allocators returned these literals when the graph was empty.
        assert 'return "n001"' not in source
        assert 'return "p001"' not in source
