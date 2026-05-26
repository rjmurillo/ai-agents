#!/usr/bin/env python3
"""Validate the skillbook registry files against their JSON schemas.

Validates .agents/skillbook/{policies,tensions,workflows}.json against
.agents/schemas/{policy,tension,workflow}.schema.json (policy.schema.json
references evidence-entry.schema.json). After schema conformance, it runs
referential-integrity checks the schema cannot express:

  - Derived counts: confirms / contradicts / application_count must equal the
    values recomputed from the evidence array (the system of record).
  - Cross-references: contradicts_policies, related_policies, supersedes, and
    tension policy_a / policy_b must point to real policy ids.
  - Tension resolutions: each preferred policy must be one of the tension's
    two paired policies.

This is invoked by .github/workflows/skillbook-validation.yml on every PR.

The bundled schema checker covers the draft-07 subset the skillbook schemas
use (type, required, properties, additionalProperties, items, enum, const,
pattern, minimum, maximum, minItems, minLength, $ref). It is intentionally
small and purpose-built; it is not a general JSON Schema implementation.

EXIT CODES (ADR-035):
  0  - Success: all files valid
  1  - Logic error: a file failed schema or integrity validation
  2  - Config error: a skillbook or schema file is missing or unparseable

See: ADR-035 Exit Code Standardization.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

from scripts.skillbook import evidence_weight  # noqa: E402

EXIT_OK = 0
EXIT_LOGIC = 1
EXIT_CONFIG = 2

# skillbook file -> schema file that validates it.
FILE_SCHEMA_MAP = {
    "policies.json": "policy.schema.json",
    "tensions.json": "tension.schema.json",
    "workflows.json": "workflow.schema.json",
}


# --------------------------------------------------------------------------
# Minimal draft-07 schema checker (skillbook subset only)
# --------------------------------------------------------------------------

_TYPE_CHECKS = {
    "object": lambda v: isinstance(v, dict),
    "array": lambda v: isinstance(v, list),
    "string": lambda v: isinstance(v, str),
    "boolean": lambda v: isinstance(v, bool),
    "integer": lambda v: isinstance(v, int) and not isinstance(v, bool),
    "number": lambda v: isinstance(v, (int, float)) and not isinstance(v, bool),
}


class SchemaChecker:
    """Validate an instance against a draft-07 schema subset.

    Resolves local pointers (#/$defs/...) against the root schema and external
    file references against sibling files in the schema directory.
    """

    def __init__(self, root: dict[str, Any], schema_dir: Path) -> None:
        self._root = root
        self._schema_dir = schema_dir
        self._file_cache: dict[str, dict[str, Any]] = {}

    def check(self, instance: Any, schema: dict[str, Any], path: str) -> list[str]:
        """Return a list of validation error strings for instance vs schema."""
        if "$ref" in schema:
            return self._check_ref(instance, schema["$ref"], path)
        errors: list[str] = []
        errors += self._check_type(instance, schema, path)
        errors += self._check_const_enum(instance, schema, path)
        errors += self._check_scalar(instance, schema, path)
        if isinstance(instance, dict):
            errors += self._check_object(instance, schema, path)
        if isinstance(instance, list):
            errors += self._check_array(instance, schema, path)
        return errors

    def _check_ref(self, instance: Any, ref: str, path: str) -> list[str]:
        """Resolve a $ref (local pointer or sibling file) and validate against it."""
        if ref.startswith("#/"):
            target: Any = self._root
            for token in ref[2:].split("/"):
                target = target[token]
            return self.check(instance, target, path)
        sub_root = self._load_ref_file(ref)
        return SchemaChecker(sub_root, self._schema_dir).check(
            instance, sub_root, path
        )

    def _load_ref_file(self, ref: str) -> dict[str, Any]:
        """Load and cache an external schema file referenced by $ref.

        Guards against path traversal (CWE-22): the resolved path must stay
        inside ``self._schema_dir``. Although ``ref`` values come from
        in-repo schema files rather than untrusted input, anchoring the
        resolution defends against accidental or malicious ``..`` segments
        and absolute paths that would escape the schema directory.
        """
        if ref not in self._file_cache:
            schema_root = self._schema_dir.resolve()
            candidate = (self._schema_dir / ref).resolve()
            try:
                candidate.relative_to(schema_root)
            except ValueError as exc:
                raise ValueError(
                    f"Path traversal detected in $ref {ref!r}: "
                    f"resolved path {candidate} escapes schema directory "
                    f"{schema_root}"
                ) from exc
            text = candidate.read_text(encoding="utf-8")
            self._file_cache[ref] = json.loads(text)
        return self._file_cache[ref]

    @staticmethod
    def _check_type(instance: Any, schema: dict[str, Any], path: str) -> list[str]:
        """Validate the 'type' keyword."""
        expected = schema.get("type")
        if expected is None:
            return []
        if _TYPE_CHECKS[expected](instance):
            return []
        return [f"{path}: expected type {expected}, got {type(instance).__name__}"]

    @staticmethod
    def _check_const_enum(
        instance: Any, schema: dict[str, Any], path: str
    ) -> list[str]:
        """Validate the 'const' and 'enum' keywords."""
        errors: list[str] = []
        if "const" in schema and instance != schema["const"]:
            errors.append(f"{path}: expected const {schema['const']!r}")
        if "enum" in schema and instance not in schema["enum"]:
            errors.append(f"{path}: {instance!r} not in enum {schema['enum']}")
        return errors

    @staticmethod
    def _check_scalar(instance: Any, schema: dict[str, Any], path: str) -> list[str]:
        """Validate numeric and string range keywords."""
        errors: list[str] = []
        is_number = isinstance(instance, (int, float)) and not isinstance(
            instance, bool
        )
        if "minimum" in schema and is_number and instance < schema["minimum"]:
            errors.append(f"{path}: {instance} below minimum {schema['minimum']}")
        if "maximum" in schema and is_number and instance > schema["maximum"]:
            errors.append(f"{path}: {instance} above maximum {schema['maximum']}")
        if (
            "minLength" in schema
            and isinstance(instance, str)
            and len(instance) < schema["minLength"]
        ):
            errors.append(f"{path}: string shorter than {schema['minLength']}")
        if (
            "pattern" in schema
            and isinstance(instance, str)
            and not re.search(schema["pattern"], instance)
        ):
            errors.append(f"{path}: {instance!r} does not match {schema['pattern']}")
        return errors

    def _check_object(
        self, instance: dict[str, Any], schema: dict[str, Any], path: str
    ) -> list[str]:
        """Validate 'required', 'properties', and 'additionalProperties'."""
        errors: list[str] = []
        properties = schema.get("properties", {})
        for field in schema.get("required", []):
            if field not in instance:
                errors.append(f"{path}: missing required field {field!r}")
        additional = schema.get("additionalProperties", True)
        for key, value in instance.items():
            child = f"{path}.{key}"
            if key in properties:
                errors += self.check(value, properties[key], child)
            elif additional is False:
                errors.append(f"{path}: unexpected field {key!r}")
            elif isinstance(additional, dict):
                errors += self.check(value, additional, child)
        return errors

    def _check_array(
        self, instance: list[Any], schema: dict[str, Any], path: str
    ) -> list[str]:
        """Validate 'minItems' and 'items'."""
        errors: list[str] = []
        if "minItems" in schema and len(instance) < schema["minItems"]:
            errors.append(f"{path}: fewer than {schema['minItems']} items")
        item_schema = schema.get("items")
        if isinstance(item_schema, dict):
            for index, item in enumerate(instance):
                errors += self.check(item, item_schema, f"{path}[{index}]")
        return errors


def validate_against_schema(
    instance: Any, schema_path: Path
) -> list[str]:
    """Validate a JSON instance against the schema file at schema_path."""
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    checker = SchemaChecker(schema, schema_path.parent)
    return checker.check(instance, schema, schema_path.stem)


# --------------------------------------------------------------------------
# Referential-integrity checks
# --------------------------------------------------------------------------


def check_policy_integrity(policies_data: dict[str, Any]) -> list[str]:
    """Check derived counts and cross-references inside the policy registry."""
    errors: list[str] = []
    policies = policies_data.get("policies", [])
    known_ids = {policy.get("id") for policy in policies}
    for policy in policies:
        errors += _check_derived_counts(policy)
        errors += _check_policy_refs(policy, known_ids)
    return errors


def _check_derived_counts(policy: dict[str, Any]) -> list[str]:
    """Verify confirms / contradicts / application_count match the evidence."""
    errors: list[str] = []
    evidence = policy.get("evidence", [])
    confirms = round(
        sum(evidence_weight(e) for e in evidence if e.get("type") == "confirmed"), 4
    )
    contradicts = round(
        sum(evidence_weight(e) for e in evidence if e.get("type") == "contradicted"),
        4,
    )
    policy_id = policy.get("id")
    if round(float(policy.get("confirms", 0)), 4) != confirms:
        errors.append(
            f"{policy_id}: confirms={policy.get('confirms')} but evidence "
            f"recomputes to {confirms}"
        )
    if round(float(policy.get("contradicts", 0)), 4) != contradicts:
        errors.append(
            f"{policy_id}: contradicts={policy.get('contradicts')} but evidence "
            f"recomputes to {contradicts}"
        )
    if policy.get("application_count") != len(evidence):
        errors.append(
            f"{policy_id}: application_count={policy.get('application_count')} "
            f"but evidence has {len(evidence)} entries"
        )
    return errors


def _check_policy_refs(
    policy: dict[str, Any], known_ids: set[str | None]
) -> list[str]:
    """Verify policy cross-reference arrays point to real policy ids."""
    errors: list[str] = []
    policy_id = policy.get("id")
    for field in ("related_policies", "contradicts_policies", "supersedes"):
        for ref in policy.get(field, []):
            if ref not in known_ids:
                errors.append(
                    f"{policy_id}: {field} references unknown policy {ref!r}"
                )
    return errors


def check_tension_integrity(
    tensions_data: dict[str, Any], policies_data: dict[str, Any]
) -> list[str]:
    """Check that tensions reference real policies and resolve to paired policies."""
    errors: list[str] = []
    known_ids = {policy.get("id") for policy in policies_data.get("policies", [])}
    for tension in tensions_data.get("tensions", []):
        tension_id = tension.get("id")
        pair = {tension.get("policy_a"), tension.get("policy_b")}
        for ref in pair:
            if ref not in known_ids:
                errors.append(
                    f"{tension_id}: references unknown policy {ref!r}"
                )
        for context, resolution in tension.get("preferred_in_context", {}).items():
            if resolution.get("preferred") not in pair:
                errors.append(
                    f"{tension_id}: context {context!r} prefers "
                    f"{resolution.get('preferred')!r}, not one of the paired policies"
                )
    return errors


# --------------------------------------------------------------------------
# Driver
# --------------------------------------------------------------------------


def validate_skillbook(skillbook_dir: Path, schema_dir: Path) -> list[str]:
    """Validate every skillbook file. Return a list of all error strings."""
    errors: list[str] = []
    loaded: dict[str, Any] = {}
    for filename, schema_name in FILE_SCHEMA_MAP.items():
        file_path = skillbook_dir / filename
        schema_path = schema_dir / schema_name
        data = json.loads(file_path.read_text(encoding="utf-8"))
        loaded[filename] = data
        schema_errors = validate_against_schema(data, schema_path)
        errors += [f"[{filename}] {err}" for err in schema_errors]

    policies_data = loaded["policies.json"]
    tensions_data = loaded["tensions.json"]
    errors += [
        f"[policies.json] {err}" for err in check_policy_integrity(policies_data)
    ]
    errors += [
        f"[tensions.json] {err}"
        for err in check_tension_integrity(tensions_data, policies_data)
    ]
    return errors


def main(argv: list[str] | None = None) -> int:
    """Parse arguments and validate the skillbook files."""
    parser = argparse.ArgumentParser(
        description="Validate skillbook JSON files against their schemas."
    )
    parser.add_argument(
        "--skillbook-dir",
        type=Path,
        default=_PROJECT_ROOT / ".agents" / "skillbook",
        help="Directory holding policies/tensions/workflows JSON.",
    )
    parser.add_argument(
        "--schema-dir",
        type=Path,
        default=_PROJECT_ROOT / ".agents" / "schemas",
        help="Directory holding the JSON schema files.",
    )
    args = parser.parse_args(argv)

    try:
        errors = validate_skillbook(args.skillbook_dir, args.schema_dir)
    except FileNotFoundError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return EXIT_CONFIG
    except json.JSONDecodeError as exc:
        print(f"Error: invalid JSON: {exc}", file=sys.stderr)
        return EXIT_CONFIG
    except ValueError as exc:
        # Path-traversal guard in SchemaChecker._load_ref_file raises
        # ValueError when a $ref escapes the schema directory. ADR-035
        # classifies this as a configuration error (EXIT_CONFIG=2).
        print(f"Error: {exc}", file=sys.stderr)
        return EXIT_CONFIG
    except OSError as exc:
        # IsADirectoryError, PermissionError, and other I/O failures while
        # reading a $ref target. ADR-035: configuration error (2).
        print(f"Error: failed to read referenced schema: {exc}", file=sys.stderr)
        return EXIT_CONFIG

    if errors:
        print(f"Skillbook validation FAILED with {len(errors)} error(s):")
        for err in errors:
            print(f"  - {err}")
        return EXIT_LOGIC
    print("Skillbook validation passed: policies, tensions, workflows all valid.")
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
