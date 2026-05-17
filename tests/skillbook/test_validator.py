"""Tests for the skillbook schema and referential-integrity validator."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from scripts.validation.validate_skillbook import (
    EXIT_CONFIG,
    EXIT_LOGIC,
    EXIT_OK,
    SchemaChecker,
    check_policy_integrity,
    check_tension_integrity,
    main,
    validate_skillbook,
)
from tests.skillbook.conftest import make_evidence, make_policy

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_SCHEMA_DIR = _PROJECT_ROOT / ".agents" / "schemas"
_SKILLBOOK_DIR = _PROJECT_ROOT / ".agents" / "skillbook"


class TestSchemaChecker:
    """The bundled draft-07 subset checker."""

    def test_accepts_a_valid_object(self) -> None:
        schema = {
            "type": "object",
            "required": ["name"],
            "additionalProperties": False,
            "properties": {"name": {"type": "string"}},
        }
        checker = SchemaChecker(schema, _SCHEMA_DIR)
        assert checker.check({"name": "ok"}, schema, "root") == []

    def test_flags_missing_required_field(self) -> None:
        schema = {"type": "object", "required": ["name"], "properties": {}}
        errors = SchemaChecker(schema, _SCHEMA_DIR).check({}, schema, "root")
        assert any("missing required" in err for err in errors)

    def test_flags_unexpected_field(self) -> None:
        schema = {
            "type": "object",
            "additionalProperties": False,
            "properties": {"name": {"type": "string"}},
        }
        errors = SchemaChecker(schema, _SCHEMA_DIR).check(
            {"name": "ok", "extra": 1}, schema, "root"
        )
        assert any("unexpected field" in err for err in errors)

    def test_flags_wrong_type(self) -> None:
        schema = {"type": "string"}
        errors = SchemaChecker(schema, _SCHEMA_DIR).check(123, schema, "root")
        assert any("expected type string" in err for err in errors)

    def test_integer_rejects_bool(self) -> None:
        # bool is a subclass of int; the checker must not accept True as integer.
        schema = {"type": "integer"}
        errors = SchemaChecker(schema, _SCHEMA_DIR).check(True, schema, "root")
        assert errors != []

    def test_flags_enum_violation(self) -> None:
        schema = {"enum": ["a", "b"]}
        errors = SchemaChecker(schema, _SCHEMA_DIR).check("c", schema, "root")
        assert any("not in enum" in err for err in errors)

    def test_flags_const_violation(self) -> None:
        schema = {"const": 1}
        errors = SchemaChecker(schema, _SCHEMA_DIR).check(2, schema, "root")
        assert any("const" in err for err in errors)

    def test_flags_pattern_violation(self) -> None:
        schema = {"type": "string", "pattern": "^pol-"}
        errors = SchemaChecker(schema, _SCHEMA_DIR).check("bad-id", schema, "root")
        assert any("does not match" in err for err in errors)

    def test_flags_minimum_violation(self) -> None:
        schema = {"type": "integer", "minimum": 0}
        errors = SchemaChecker(schema, _SCHEMA_DIR).check(-1, schema, "root")
        assert any("below minimum" in err for err in errors)

    def test_flags_min_items_violation(self) -> None:
        schema = {"type": "array", "minItems": 1, "items": {"type": "string"}}
        errors = SchemaChecker(schema, _SCHEMA_DIR).check([], schema, "root")
        assert any("fewer than" in err for err in errors)

    def test_resolves_local_ref(self) -> None:
        schema = {
            "$defs": {"named": {"type": "object", "required": ["x"], "properties": {}}},
            "$ref": "#/$defs/named",
        }
        errors = SchemaChecker(schema, _SCHEMA_DIR).check({}, schema, "root")
        assert any("missing required" in err for err in errors)


class TestRealSchemas:
    """The committed seed files validate against the committed schemas."""

    def test_seed_skillbook_files_pass_validation(self) -> None:
        errors = validate_skillbook(_SKILLBOOK_DIR, _SCHEMA_DIR)
        assert errors == [], f"seed data failed validation: {errors}"

    def test_policy_schema_resolves_evidence_entry_file_ref(self) -> None:
        # An invalid evidence entry must be caught via the cross-file $ref.
        schema_path = _SCHEMA_DIR / "policy.schema.json"
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        bad_policy = make_policy()
        bad_policy["evidence"] = [{"type": "confirmed"}]  # missing required fields
        instance = {
            "schema_version": 1,
            "policies": [bad_policy],
            "meta": {
                "total_discovered": 0,
                "total_retired": 0,
                "total_merged": 0,
                "last_promotion_at": 0,
                "promotion_count": 0,
            },
        }
        errors = SchemaChecker(schema, _SCHEMA_DIR).check(instance, schema, "policy")
        assert any("missing required" in err for err in errors)


class TestPolicyIntegrity:
    """check_policy_integrity verifies derived counts and cross-references."""

    def test_passes_when_counts_match_evidence(self) -> None:
        policy = make_policy(
            evidence=[make_evidence("confirmed", "e1")],
            confirms=1.0,
            contradicts=0,
            application_count=1,
        )
        assert check_policy_integrity({"policies": [policy]}) == []

    def test_flags_confirms_count_mismatch(self) -> None:
        policy = make_policy(
            evidence=[make_evidence("confirmed", "e1")],
            confirms=99,
            application_count=1,
        )
        errors = check_policy_integrity({"policies": [policy]})
        assert any("confirms" in err for err in errors)

    def test_flags_application_count_mismatch(self) -> None:
        policy = make_policy(
            evidence=[make_evidence("confirmed", "e1")],
            confirms=1.0,
            application_count=7,
        )
        errors = check_policy_integrity({"policies": [policy]})
        assert any("application_count" in err for err in errors)

    def test_flags_dangling_cross_reference(self) -> None:
        policy = make_policy(contradicts_policies=["pol-nonexistent"])
        errors = check_policy_integrity({"policies": [policy]})
        assert any("unknown policy" in err for err in errors)


class TestTensionIntegrity:
    """check_tension_integrity verifies tension references and resolutions."""

    def _policies(self) -> dict[str, Any]:
        return {"policies": [make_policy("pol-a"), make_policy("pol-b")]}

    def test_passes_for_valid_tension(self) -> None:
        tensions = {
            "tensions": [
                {
                    "id": "ten-a-b",
                    "policy_a": "pol-a",
                    "policy_b": "pol-b",
                    "preferred_in_context": {
                        "ctx": {
                            "preferred": "pol-a",
                            "confirmed_count": 1,
                            "evidence": ["e1"],
                        }
                    },
                    "status": "holding",
                    "detected_at": 1,
                }
            ]
        }
        assert check_tension_integrity(tensions, self._policies()) == []

    def test_flags_unknown_paired_policy(self) -> None:
        tensions = {
            "tensions": [
                {
                    "id": "ten-bad",
                    "policy_a": "pol-a",
                    "policy_b": "pol-ghost",
                    "preferred_in_context": {},
                    "status": "holding",
                    "detected_at": 1,
                }
            ]
        }
        errors = check_tension_integrity(tensions, self._policies())
        assert any("unknown policy" in err for err in errors)

    def test_flags_resolution_outside_pair(self) -> None:
        tensions = {
            "tensions": [
                {
                    "id": "ten-a-b",
                    "policy_a": "pol-a",
                    "policy_b": "pol-b",
                    "preferred_in_context": {
                        "ctx": {
                            "preferred": "pol-a",
                            "confirmed_count": 0,
                            "evidence": [],
                        }
                    },
                    "status": "holding",
                    "detected_at": 1,
                }
            ]
        }
        # Corrupt the resolution to prefer a policy not in the pair.
        tensions["tensions"][0]["preferred_in_context"]["ctx"]["preferred"] = "pol-b2"
        errors = check_tension_integrity(tensions, self._policies())
        assert any("not one of the paired" in err for err in errors)


class TestValidatorMain:
    """The validator CLI entry point and its exit codes."""

    def test_exit_ok_on_valid_seed_data(self) -> None:
        exit_code = main(
            ["--skillbook-dir", str(_SKILLBOOK_DIR), "--schema-dir", str(_SCHEMA_DIR)]
        )
        assert exit_code == EXIT_OK

    def test_exit_config_when_files_missing(self, tmp_path: Path) -> None:
        exit_code = main(
            ["--skillbook-dir", str(tmp_path), "--schema-dir", str(_SCHEMA_DIR)]
        )
        assert exit_code == EXIT_CONFIG

    def test_exit_logic_on_schema_violation(
        self, write_skillbook: Any, tmp_path: Path
    ) -> None:
        # A policy with a malformed id violates the id pattern.
        skillbook = write_skillbook(policies=[make_policy("BAD_ID")])
        exit_code = main(
            ["--skillbook-dir", str(skillbook), "--schema-dir", str(_SCHEMA_DIR)]
        )
        assert exit_code == EXIT_LOGIC
