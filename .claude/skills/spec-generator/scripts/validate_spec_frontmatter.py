#!/usr/bin/env python3
"""Validate spec frontmatter against the canonical spec schema enums.

Canonical source: ``.agents/governance/spec-schemas.md`` (S-003 requirement,
S-004 design, S-005 task). This validator mirrors that document's enum
contracts verbatim. The enum sets below are copied character-for-character
from the schema's "Field Definitions" tables; keep them in sync if the schema
changes (canonical-source-mirror rule).

Verbatim contract from spec-schemas.md:

    requirement.status : draft | review | approved | implemented | rejected
    design.status      : draft | review | approved | implemented | rejected
    task.status        : todo | in-progress | blocked | done | cancelled
    priority (all)     : P0 | P1 | P2
    requirement.category : functional | non-functional | constraint
    task.complexity      : XS | S | M | L | XL
    id patterns        : REQ-\\d{3} | DESIGN-\\d{3} | TASK-\\d{3}

Stricter/looser/different than canonical: this validator checks frontmatter
enum membership, required-field presence, and id pattern only. It does NOT
check cross-file traceability (orphan detection), date ordering, or section
completeness; those remain the responsibility of the spec author and the
existing traceability tooling. It is therefore looser than the full schema and
never blocks on anything the schema marks optional.

Exit codes (AGENTS.md contract): 0 = all valid, 1 = one or more validation
failures (logic), 2 = configuration error (no input, unreadable file).

Usage:
    validate_spec_frontmatter.py FILE [FILE ...]
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field

# --- Verbatim enum contracts from .agents/governance/spec-schemas.md ---------

_STATUS_BY_TYPE: dict[str, frozenset[str]] = {
    "requirement": frozenset({"draft", "review", "approved", "implemented", "rejected"}),
    "design": frozenset({"draft", "review", "approved", "implemented", "rejected"}),
    "task": frozenset({"todo", "in-progress", "blocked", "done", "cancelled"}),
}
_PRIORITY = frozenset({"P0", "P1", "P2"})
_CATEGORY = frozenset({"functional", "non-functional", "constraint"})
_COMPLEXITY = frozenset({"XS", "S", "M", "L", "XL"})
_ID_PATTERN: dict[str, re.Pattern[str]] = {
    "requirement": re.compile(r"^REQ-\d{3}$"),
    "design": re.compile(r"^DESIGN-\d{3}$"),
    "task": re.compile(r"^TASK-\d{3}$"),
}

# Required frontmatter fields per type (schema "Required = Yes" rows).
_REQUIRED: dict[str, tuple[str, ...]] = {
    "requirement": ("type", "id", "title", "status", "priority", "category", "created", "updated"),
    "design": ("type", "id", "title", "status", "priority", "related", "created", "updated"),
    "task": ("type", "id", "title", "status", "priority", "complexity", "related", "created", "updated"),
}

_VALID_TYPES = frozenset(_STATUS_BY_TYPE)
_FRONTMATTER_DELIM = "---"


@dataclass
class SpecValidation:
    """Result of validating one spec file's frontmatter."""

    path: str
    errors: list[str] = field(default_factory=list)
    config_error: bool = False

    @property
    def ok(self) -> bool:
        return not self.errors


def _strip_scalar(value: str) -> str:
    """Normalize a scalar frontmatter value.

    A quoted value is returned with its quotes removed and its contents intact,
    so an inner ``#`` (e.g. ``title: "Spec #2001"``) is preserved. An unquoted
    value has a trailing `` # inline comment`` stripped.
    """
    if value and value[0] in "\"'":
        quote = value[0]
        end = value.find(quote, 1)
        if end != -1:
            return value[1:end]
    return re.sub(r"\s+#.*$", "", value).strip()


def extract_frontmatter(text: str) -> dict[str, str] | None:
    """Return the leading YAML frontmatter as a flat key->scalar map.

    Only scalar (single-line ``key: value``) fields are captured; list fields
    such as ``related`` are recorded as present with a sentinel non-empty value
    so required-field checks pass. Returns None when no frontmatter block is
    found (the file does not open with a ``---`` fence).
    """
    lines = text.splitlines()
    if not lines or lines[0].strip() != _FRONTMATTER_DELIM:
        return None
    fields: dict[str, str] = {}
    current_key: str | None = None
    for line in lines[1:]:
        if line.strip() == _FRONTMATTER_DELIM:
            return fields
        if re.match(r"^[ \t]*-\s+", line) and current_key is not None:
            # A list item under the most recent key: mark the key present.
            fields.setdefault(current_key, "[]")
            fields[current_key] = "[present]"
            continue
        match = re.match(r"^([A-Za-z_][A-Za-z0-9_]*):[ \t]*(.*)$", line)
        if not match:
            continue
        key, value = match.group(1), match.group(2).strip()
        # Strip surrounding quotes and (for unquoted values) inline comments.
        value = _strip_scalar(value)
        current_key = key
        fields[key] = value
    # Unterminated frontmatter (no closing fence): treat as malformed.
    return None


def _check_enum(result: SpecValidation, fields: dict[str, str], key: str, allowed: frozenset[str]) -> None:
    value = fields.get(key, "")
    if not value or value == "[]":
        return  # presence handled by required-field check
    if value == "[present]":
        result.errors.append(f"{key} must be a scalar value, not a list; allowed: {', '.join(sorted(allowed))}")
        return
    if value not in allowed:
        result.errors.append(
            f"{key}={value!r} is not a valid value; allowed: {', '.join(sorted(allowed))}"
        )


def validate_fields(path: str, fields: dict[str, str]) -> SpecValidation:
    """Validate a parsed frontmatter map against the per-type schema."""
    result = SpecValidation(path=path)
    spec_type = fields.get("type", "")
    if spec_type not in _VALID_TYPES:
        result.errors.append(
            f"type={spec_type!r} is not a valid spec type; allowed: {', '.join(sorted(_VALID_TYPES))}"
        )
        return result  # cannot validate type-specific rules without a valid type

    for required in _REQUIRED[spec_type]:
        value = fields.get(required, "")
        if not value or value == "[]" or value == "null":
            result.errors.append(f"missing required field {required!r} for type {spec_type!r}")

    _check_enum(result, fields, "status", _STATUS_BY_TYPE[spec_type])
    _check_enum(result, fields, "priority", _PRIORITY)
    if spec_type == "requirement":
        _check_enum(result, fields, "category", _CATEGORY)
    if spec_type == "task":
        _check_enum(result, fields, "complexity", _COMPLEXITY)

    spec_id = fields.get("id", "")
    if spec_id and not _ID_PATTERN[spec_type].match(spec_id):
        result.errors.append(
            f"id={spec_id!r} does not match {_ID_PATTERN[spec_type].pattern} for type {spec_type!r}"
        )
    return result


def validate_file(path: str) -> SpecValidation:
    """Read and validate one spec file."""
    result = SpecValidation(path=path)
    try:
        with open(path, encoding="utf-8") as handle:
            text = handle.read()
    except OSError as exc:
        # Unreadable input is a configuration error (exit 2), not a logic
        # failure (exit 1), per the module exit-code contract above.
        result.errors.append(f"cannot read file: {exc}")
        result.config_error = True
        return result
    fields = extract_frontmatter(text)
    if fields is None:
        result.errors.append("no YAML frontmatter block found (file must open with a --- fence)")
        return result
    return validate_fields(path, fields)


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args:
        print("usage: validate_spec_frontmatter.py FILE [FILE ...]", file=sys.stderr)
        return 2

    any_failed = False
    any_config_error = False
    for path in args:
        result = validate_file(path)
        if result.ok:
            print(f"[PASS] {path}")
        else:
            if result.config_error:
                any_config_error = True
            else:
                any_failed = True
            for err in result.errors:
                print(f"[FAIL] {path}: {err}")
    if any_config_error:
        return 2
    return 1 if any_failed else 0


if __name__ == "__main__":
    sys.exit(main())
