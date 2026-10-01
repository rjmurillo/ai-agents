"""Conformance test: validate_spec_frontmatter enums equal the schema document.

Canonical source: .agents/governance/spec-schemas.md. The validator keeps its
enum constants, and this test reads the schema and fails when they differ, so
the validator docstring no longer needs a hand-copied table (issue #5399).
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / ".claude" / "skills" / "spec-generator" / "scripts"))

import validate_spec_frontmatter as validator

SCHEMA = REPO_ROOT / ".agents" / "governance" / "spec-schemas.md"

_TYPE_LINE = re.compile(r"^type: (requirement|design|task)\s*$")
_ENUM_LINE = re.compile(r"^(status|priority|category|complexity): (.+\|.+)$")
_ID_ROW = re.compile(r"Pattern: `((?:REQ|DESIGN|TASK)-\\d\{\d+\})`")
_ID_TYPES = {"REQ": "requirement", "DESIGN": "design", "TASK": "task"}


def schema_enums(text: str) -> dict[str, dict[str, frozenset[str]]]:
    """Return {doc_type: {field: values}} from the schema front matter templates."""
    result: dict[str, dict[str, frozenset[str]]] = {}
    current: dict[str, frozenset[str]] | None = None
    for line in text.splitlines():
        type_match = _TYPE_LINE.match(line)
        if type_match:
            current = result.setdefault(type_match.group(1), {})
            continue
        enum_match = _ENUM_LINE.match(line)
        if enum_match and current is not None:
            values = frozenset(v.strip() for v in enum_match.group(2).split("|"))
            current[enum_match.group(1)] = values
    return result


def schema_id_patterns(text: str) -> dict[str, str]:
    """Return {doc_type: regex source} from the Field Definitions id rows."""
    return {_ID_TYPES[m.group(1).split("-")[0]]: m.group(1) for m in _ID_ROW.finditer(text)}


def validator_enums() -> dict[str, dict[str, frozenset[str]]]:
    """Return the validator constants in the same shape as schema_enums."""
    return {
        "requirement": {
            "status": validator._STATUS_BY_TYPE["requirement"],
            "priority": validator._PRIORITY,
            "category": validator._CATEGORY,
        },
        "design": {
            "status": validator._STATUS_BY_TYPE["design"],
            "priority": validator._PRIORITY,
        },
        "task": {
            "status": validator._STATUS_BY_TYPE["task"],
            "priority": validator._PRIORITY,
            "complexity": validator._COMPLEXITY,
        },
    }


def test_enums_equal_schema() -> None:
    assert schema_enums(SCHEMA.read_text(encoding="utf-8")) == validator_enums()


def test_id_patterns_equal_schema() -> None:
    expected = schema_id_patterns(SCHEMA.read_text(encoding="utf-8"))
    actual = {t: rx.pattern.strip("^$") for t, rx in validator._ID_PATTERN.items()}
    assert expected == actual


def test_negative_control_detects_a_drifted_schema() -> None:
    drifted = SCHEMA.read_text(encoding="utf-8").replace(
        "priority: P0 | P1 | P2", "priority: P0 | P1 | P2 | P3", 1
    )
    assert schema_enums(drifted) != validator_enums()


def test_negative_control_detects_a_drifted_id_pattern() -> None:
    drifted = SCHEMA.read_text(encoding="utf-8").replace(r"`REQ-\d{3}`", r"`REQ-\d{4}`", 1)
    actual = {t: rx.pattern.strip("^$") for t, rx in validator._ID_PATTERN.items()}
    assert schema_id_patterns(drifted) != actual
