"""Independent JSON Schema Draft 7 validation of skill-output.schema.json.

test_skill_output.py exercises validate_envelope's hand-written checks.
Those checks are meant to enforce the same contract as
.agents/schemas/skill-output.schema.json, but nothing before this file ran
the schema itself: a regression that narrowed the schema's `required`
array (dropping "Data" or "Error", for example) would go undetected as
long as the hand-written validator still enforced the field, because no
test exercised the schema in isolation (Copilot review on PR #5283).

This file uses the `jsonschema` library (a real pyproject.toml dependency,
not test-only tooling) to validate fixture envelopes directly against the
committed schema file, independent of validate_envelope. A fixture here
that regresses validate_envelope but not the schema, or vice versa, is
exactly the drift this file exists to catch.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import jsonschema
import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

# isort: skip_file
from scripts.validate_skill_output import validate_envelope  # noqa: E402

_SCHEMA_PATH = REPO_ROOT / ".agents" / "schemas" / "skill-output.schema.json"
_SCHEMA = json.loads(_SCHEMA_PATH.read_text(encoding="utf-8"))


def _validate(instance: object) -> list[str]:
    """Return jsonschema's error messages for `instance`, or [] if valid."""
    validator = jsonschema.Draft7Validator(_SCHEMA)
    return [e.message for e in validator.iter_errors(instance)]


class TestSchemaAcceptsValidEnvelopes:
    def test_success_envelope_is_valid(self) -> None:
        envelope = {
            "Success": True,
            "Data": {"Result": "ok"},
            "Error": None,
            "Metadata": {"Script": "test.py", "Timestamp": "2026-03-08T12:00:00Z"},
        }
        assert _validate(envelope) == []

    def test_error_envelope_is_valid(self) -> None:
        envelope = {
            "Success": False,
            "Data": None,
            "Error": {"Message": "fail", "Code": 1, "Type": "General"},
            "Metadata": {"Script": "test.py", "Timestamp": "2026-03-08T12:00:00Z"},
        }
        assert _validate(envelope) == []

    def test_envelope_with_version_is_valid(self) -> None:
        envelope = {
            "Success": True,
            "Data": None,
            "Error": None,
            "Metadata": {
                "Script": "test.py",
                "Timestamp": "2026-03-08T12:00:00Z",
                "Version": "1.0.0",
            },
        }
        assert _validate(envelope) == []


class TestSchemaRejectsInvalidEnvelopes:
    """One case per required-field/type constraint in the schema, run
    directly against jsonschema rather than through validate_envelope.
    """

    def test_missing_data_key_is_rejected(self) -> None:
        envelope = {
            "Success": True,
            "Error": None,
            "Metadata": {"Script": "x", "Timestamp": "t"},
        }
        errors = _validate(envelope)
        assert any("'Data' is a required property" in e for e in errors)

    def test_missing_error_key_is_rejected(self) -> None:
        envelope = {
            "Success": True,
            "Data": None,
            "Metadata": {"Script": "x", "Timestamp": "t"},
        }
        errors = _validate(envelope)
        assert any("'Error' is a required property" in e for e in errors)

    def test_error_object_missing_type_is_rejected(self) -> None:
        """Error is `oneOf(null, object-with-required-Type)`. An object
        that fails the object branch and is not null fails the oneOf as a
        whole; jsonschema reports the top-level oneOf failure rather than
        surfacing the sub-schema's 'required property' message directly,
        so the assertion matches what a real caller actually sees.
        """
        envelope = {
            "Success": False,
            "Data": None,
            "Error": {"Message": "fail", "Code": 1},
            "Metadata": {"Script": "x", "Timestamp": "t"},
        }
        errors = _validate(envelope)
        assert any("not valid under any of the given schemas" in e for e in errors)

    def test_empty_error_message_is_rejected(self) -> None:
        """Pins schema minLength:1 on Error.Message independently of
        validate_envelope's truthiness check. Same oneOf-wrapping caveat
        as test_error_object_missing_type_is_rejected above.
        """
        envelope = {
            "Success": False,
            "Data": None,
            "Error": {"Message": "", "Code": 1, "Type": "General"},
            "Metadata": {"Script": "x", "Timestamp": "t"},
        }
        errors = _validate(envelope)
        assert any("not valid under any of the given schemas" in e for e in errors)

    def test_non_string_metadata_version_is_rejected(self) -> None:
        envelope = {
            "Success": True,
            "Data": None,
            "Error": None,
            "Metadata": {"Script": "x", "Timestamp": "t", "Version": 1},
        }
        errors = _validate(envelope)
        assert any("is not of type 'string'" in e for e in errors)

    def test_non_object_top_level_is_rejected(self) -> None:
        errors = _validate(["not", "an", "object"])
        assert any("is not of type 'object'" in e for e in errors)


class TestSchemaItselfIsValidDraft7:
    def test_schema_document_is_a_valid_draft7_schema(self) -> None:
        """Guards the schema file itself, not just fixture instances: a
        malformed schema (bad JSON Schema syntax) would make every other
        test in this file pass vacuously if jsonschema silently no-ops on
        an invalid schema instead of raising.
        """
        jsonschema.Draft7Validator.check_schema(_SCHEMA)


@pytest.mark.parametrize(
    "envelope",
    [
        {
            "Success": True,
            "Data": {"Result": "ok"},
            "Error": None,
            "Metadata": {"Script": "test.py", "Timestamp": "2026-03-08T12:00:00Z"},
        },
        {
            "Success": False,
            "Data": None,
            "Error": {"Message": "fail", "Code": 1, "Type": "General"},
            "Metadata": {"Script": "test.py", "Timestamp": "2026-03-08T12:00:00Z"},
        },
    ],
)
def test_schema_and_validate_envelope_agree_on_valid_fixtures(envelope: dict) -> None:
    """Cross-check: every fixture valid_envelope accepts must also be
    schema-valid. Imports validate_envelope directly rather than through
    test_skill_output.py to keep this file's dependency on that module
    explicit and minimal.
    """
    assert _validate(envelope) == []
    assert validate_envelope(envelope) == []
