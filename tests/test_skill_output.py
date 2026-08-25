"""Tests for the skill_output module and validate_skill_output's validate_envelope.

Covers:
- get_output_format resolution
- write_skill_output JSON envelope structure
- write_skill_error JSON envelope structure
- validate_envelope's field-by-field contract, in-process

CLI subprocess integration tests (invalid JSON, path traversal, symlink
attacks) live in test_skill_output_cli.py, split out once this file crossed
the 500-line taste-lint gate.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from unittest import mock

import pytest

# Add scripts directory to path for imports
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

# isort: skip_file
from scripts.github_core.output import (  # noqa: E402
    VALID_ERROR_TYPES,
    get_output_format,
    write_skill_error,
    write_skill_output,
)
from scripts.validate_skill_output import VALID_ERROR_TYPES as VALIDATOR_ERROR_TYPES  # noqa: E402
from scripts.validate_skill_output import validate_envelope  # noqa: E402

# Read the committed schema's Error.Type enum directly (ADR-103), not a
# hardcoded copy, so this test fails if the schema and write_skill_error's
# VALID_ERROR_TYPES tuple ever drift apart again.
_SCHEMA_PATH = REPO_ROOT / ".agents" / "schemas" / "skill-output.schema.json"
_SCHEMA = json.loads(_SCHEMA_PATH.read_text(encoding="utf-8"))
SCHEMA_ERROR_TYPE_ENUM = frozenset(
    _SCHEMA["properties"]["Error"]["oneOf"][1]["properties"]["Type"]["enum"]
)


class TestGetOutputFormat:
    """Tests for get_output_format function."""

    def test_returns_json_when_requested(self) -> None:
        assert get_output_format("json") == "json"
        assert get_output_format("JSON") == "json"

    def test_returns_human_when_requested(self) -> None:
        assert get_output_format("human") == "human"
        assert get_output_format("Human") == "human"

    @mock.patch.dict(os.environ, {"CI": "true"}, clear=False)
    def test_returns_json_when_ci_env_set(self) -> None:
        assert get_output_format("auto") == "json"

    @mock.patch.dict(os.environ, {"GITHUB_ACTIONS": "true"}, clear=False)
    def test_returns_json_when_github_actions_set(self) -> None:
        assert get_output_format("auto") == "json"

    @mock.patch.dict(os.environ, {"TF_BUILD": "true"}, clear=False)
    def test_returns_json_when_tf_build_set(self) -> None:
        assert get_output_format("auto") == "json"


class TestWriteSkillOutput:
    """Tests for write_skill_output function."""

    def test_produces_valid_json_envelope(self, capsys: pytest.CaptureFixture[str]) -> None:
        data = {"Number": 42, "Title": "Test PR"}
        result = write_skill_output(
            data, output_format="json", human_summary="Test", script_name="test.py"
        )
        assert result is not None
        envelope = json.loads(result)
        assert envelope["Success"] is True
        assert envelope["Data"]["Number"] == 42
        assert envelope["Error"] is None
        assert envelope["Metadata"]["Script"] == "test.py"
        assert envelope["Metadata"]["Timestamp"]

    def test_handles_null_data(self, capsys: pytest.CaptureFixture[str]) -> None:
        result = write_skill_output(None, output_format="json", script_name="test.py")
        assert result is not None
        envelope = json.loads(result)
        assert envelope["Success"] is True
        assert envelope["Data"] is None

    def test_handles_empty_dict_data(self, capsys: pytest.CaptureFixture[str]) -> None:
        result = write_skill_output({}, output_format="json", script_name="test.py")
        assert result is not None
        envelope = json.loads(result)
        assert envelope["Success"] is True
        assert envelope["Data"] == {}


class TestWriteSkillError:
    """Tests for write_skill_error function."""

    def test_produces_valid_error_envelope(self, capsys: pytest.CaptureFixture[str]) -> None:
        result = write_skill_error(
            "Not found",
            2,
            error_type="NotFound",
            output_format="json",
            script_name="test.py",
        )
        assert result is not None
        envelope = json.loads(result)
        assert envelope["Success"] is False
        assert envelope["Error"]["Message"] == "Not found"
        assert envelope["Error"]["Code"] == 2
        assert envelope["Error"]["Type"] == "NotFound"
        assert envelope["Metadata"]["Script"] == "test.py"

    def test_includes_extra_data(self, capsys: pytest.CaptureFixture[str]) -> None:
        result = write_skill_error(
            "API error",
            3,
            error_type="ApiError",
            output_format="json",
            script_name="test.py",
            extra={"Number": 99},
        )
        assert result is not None
        envelope = json.loads(result)
        assert envelope["Success"] is False
        assert envelope["Data"]["Number"] == 99

    @pytest.mark.parametrize("error_type", sorted(VALID_ERROR_TYPES))
    def test_validates_error_types(
        self, error_type: str, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Each error_type write_skill_error accepts must also pass validate_envelope
        and appear in the committed JSON schema's enum (ADR-103). The
        parametrize list is derived from output.py's own VALID_ERROR_TYPES
        constant (not a second hardcoded copy), so a type added there is
        automatically exercised here. Round-tripping through
        validate_envelope, and asserting membership in the schema's enum,
        covers the direction a same-list-both-places test cannot: a type
        added to the schema or the validator without also being added to
        write_skill_error's own VALID_ERROR_TYPES would not appear in this
        parametrize list at all, so test_error_type_contracts_stay_in_sync
        below closes that remaining gap with an explicit three-way equality
        check (Cursor Bugbot finding on PR #5283, commit 508917d4b).
        """
        result = write_skill_error(
            "test", 1, error_type=error_type, output_format="json", script_name="test.py"
        )
        assert result is not None
        envelope = json.loads(result)
        assert envelope["Error"]["Type"] == error_type

        assert validate_envelope(envelope) == []
        assert error_type in SCHEMA_ERROR_TYPE_ENUM

    def test_error_type_contracts_stay_in_sync(self) -> None:
        """Converse of test_validates_error_types: no contract copy may hold a
        value the other two lack.

        test_validates_error_types only proves each value write_skill_error
        accepts is also accepted by the schema and the validator; it does not
        prove the reverse. A value added only to the schema's enum, or only
        to validate_skill_output.py's VALID_ERROR_TYPES, would never appear
        in write_skill_error's own VALID_ERROR_TYPES and so would never be
        parametrized above, leaving that test green while the two artifacts
        silently disagreed. Asserting three-way set equality closes that gap.
        """
        assert frozenset(VALID_ERROR_TYPES) == SCHEMA_ERROR_TYPE_ENUM
        assert frozenset(VALID_ERROR_TYPES) == VALIDATOR_ERROR_TYPES

    def test_rejects_invalid_error_type(self) -> None:
        with pytest.raises(ValueError, match="error_type must be one of"):
            write_skill_error("test", 1, error_type="Invalid", output_format="json")


class TestValidateEnvelope:
    """Tests for validate_envelope function."""

    def test_valid_success_envelope(self) -> None:
        envelope = {
            "Success": True,
            "Data": {"Result": "ok"},
            "Error": None,
            "Metadata": {"Script": "test.py", "Timestamp": "2026-03-08T12:00:00Z"},
        }
        assert validate_envelope(envelope) == []

    def test_valid_error_envelope(self) -> None:
        envelope = {
            "Success": False,
            "Data": None,
            "Error": {"Message": "fail", "Code": 1, "Type": "General"},
            "Metadata": {"Script": "test.py", "Timestamp": "2026-03-08T12:00:00Z"},
        }
        assert validate_envelope(envelope) == []

    def test_missing_success_field(self) -> None:
        errors = validate_envelope({"Metadata": {"Script": "x", "Timestamp": "t"}})
        assert any("Missing required field: Success" in e for e in errors)

    def test_missing_data_field_is_rejected(self) -> None:
        """ADR-103 Decision item 1 (unchanged from ADR-056): every envelope
        MUST carry a Data key. Before this fix, neither
        skill-output.schema.json's top-level `required` array nor
        validate_envelope checked for it, the same documented-but-unenforced
        gap this ADR closed for Error.Type. Found by the independent-thinker
        seat during the ADR-103 adr-review debate on PR #5283.
        """
        envelope = {
            "Success": True,
            "Error": None,
            "Metadata": {"Script": "x", "Timestamp": "t"},
        }
        errors = validate_envelope(envelope)
        assert any("Missing required field: Data" in e for e in errors)

    def test_missing_error_type_is_rejected(self) -> None:
        """ADR-103: Error.Type is required, not merely valid-if-present.

        Before ADR-103, validate_envelope only checked Type against
        VALID_ERROR_TYPES when the field was truthy, so an envelope missing
        Type entirely passed validation even though write_skill_error can
        never construct one (error_type defaults to "General" and is never
        omitted). This asserts the gap is closed: a hand-built envelope with
        no Type is now rejected, matching skill-output.schema.json's
        required: ["Message", "Code", "Type"].
        """
        envelope = {
            "Success": False,
            "Data": None,
            "Error": {"Message": "fail", "Code": 1},
            "Metadata": {"Script": "test.py", "Timestamp": "2026-03-08T12:00:00Z"},
        }
        errors = validate_envelope(envelope)
        assert any("Error.Type is required" in e for e in errors)

    def test_empty_error_type_is_rejected(self) -> None:
        envelope = {
            "Success": False,
            "Data": None,
            "Error": {"Message": "fail", "Code": 1, "Type": ""},
            "Metadata": {"Script": "test.py", "Timestamp": "2026-03-08T12:00:00Z"},
        }
        errors = validate_envelope(envelope)
        assert any("Error.Type is required" in e for e in errors)

    def test_malformed_error_is_rejected_even_when_success_is_true(self) -> None:
        """skill-output.schema.json's Error property is oneOf(null, object)
        with Message/Code/Type required on the object branch, independent of
        Success (schema lines 16-39). Before this fix, validate_envelope only
        checked the Error object's internal shape inside `if Success is
        False`, so a Success=true envelope carrying a malformed Error (here,
        missing Type) passed validate_envelope while still failing the JSON
        schema. Caught by adr-review critic seat on PR #5283 (ADR-103).
        """
        envelope = {
            "Success": True,
            "Data": {"Result": "ok"},
            "Error": {"Message": "unexpected", "Code": 1},
            "Metadata": {"Script": "test.py", "Timestamp": "2026-03-08T12:00:00Z"},
        }
        errors = validate_envelope(envelope)
        assert any("Error.Type is required" in e for e in errors)

    def test_missing_metadata_field(self) -> None:
        errors = validate_envelope({"Success": True})
        assert any("Missing required field: Metadata" in e for e in errors)

    def test_non_object_metadata_is_rejected_without_crashing(self) -> None:
        """skill-output.schema.json requires Metadata to be an object. A
        non-dict value must produce a validation finding, not raise
        AttributeError.

        Before this fix, `metadata.get(...)` ran unconditionally on
        whatever `Metadata` held, so a string, array, or number crashed
        the validator with `'str' object has no attribute 'get'` instead
        of failing closed with a finding. Caught by the AI Spec Validator
        on PR #5283, commit 6bee062d8, the same class of gap already fixed
        for `Error` in this PR.
        """
        envelope = {
            "Success": True,
            "Data": None,
            "Error": None,
            "Metadata": "not-an-object",
        }
        errors = validate_envelope(envelope)  # must not raise
        assert any("Metadata must be an object" in e for e in errors)

    def test_invalid_error_type(self) -> None:
        envelope = {
            "Success": False,
            "Error": {"Message": "x", "Code": 1, "Type": "BadType"},
            "Metadata": {"Script": "x", "Timestamp": "t"},
        }
        errors = validate_envelope(envelope)
        assert any("not valid" in e for e in errors)

    def test_missing_error_when_success_false(self) -> None:
        envelope = {
            "Success": False,
            "Error": None,
            "Metadata": {"Script": "x", "Timestamp": "t"},
        }
        errors = validate_envelope(envelope)
        assert any("Error field is required" in e for e in errors)

    def test_non_object_error_is_rejected(self) -> None:
        """skill-output.schema.json's Error is oneOf(null, object): an array,
        string, or number is neither branch and must be rejected, not
        silently ignored.

        Before this fix, validate_envelope's shape check was gated on
        `isinstance(error_field, dict)` alone, with no companion branch for
        a non-null value that is also not a dict. Such a value matched
        neither `is None` nor `isinstance(..., dict)`, so no finding was
        appended at all and a schema-invalid envelope passed. Caught by
        Copilot review on PR #5283, commit 508917d4b.
        """
        envelope = {
            "Success": True,
            "Data": None,
            "Error": ["not", "an", "object"],
            "Metadata": {"Script": "test.py", "Timestamp": "2026-03-08T12:00:00Z"},
        }
        errors = validate_envelope(envelope)
        assert any("Error must be null or an object" in e for e in errors)

    def test_non_string_error_type_is_rejected_without_crashing(self) -> None:
        """A schema-invalid, unhashable Error.Type (a list) must produce a
        validation finding, not raise TypeError.

        VALID_ERROR_TYPES is a frozenset; `x in a_frozenset` raises
        TypeError when `x` is unhashable (a list or dict) rather than
        returning False. The prior `elif error_type not in
        VALID_ERROR_TYPES:` branch ran unconditionally on whatever `Type`
        held, so a list value would crash validate_envelope instead of
        reporting a finding, turning a data-validation problem into an
        unhandled exception. Caught by Copilot review on PR #5283, commit
        508917d4b.
        """
        envelope = {
            "Success": False,
            "Data": None,
            "Error": {"Message": "fail", "Code": 1, "Type": ["NotFound"]},
            "Metadata": {"Script": "test.py", "Timestamp": "2026-03-08T12:00:00Z"},
        }
        errors = validate_envelope(envelope)  # must not raise
        assert any("Error.Type must be a string" in e for e in errors)

    @pytest.mark.parametrize("top_level", [None, 1, "a string", ["an", "array"]])
    def test_non_dict_top_level_is_rejected_without_crashing(
        self, top_level: object
    ) -> None:
        """skill-output.schema.json's top level is "type": "object". The CLI
        passes json.loads()'s result straight through, and valid JSON such
        as null, a number, a string, or an array reaches validate_envelope
        unchanged.

        Before this fix, `"Success" not in data` raised TypeError for None
        or a number (not iterable), and an array reached `data["Metadata"]`
        and raised TypeError, instead of producing a finding and exit code
        1. Caught by Copilot review on PR #5283, commit 6639555b8.
        """
        errors = validate_envelope(top_level)  # must not raise
        assert any("Envelope must be a JSON object" in e for e in errors)

    def test_missing_error_key_is_rejected(self) -> None:
        """Error is a required key (ADR-103 Decision item 1), distinct from
        an explicit null value.

        `data.get("Error")` returns None for both a missing key and an
        explicit `"Error": null`, so a hand-built envelope that omits the
        key entirely was indistinguishable from one that carries it as
        null and passed validate_envelope either way. Only the latter
        satisfies the schema's `oneOf(null, object)`. Caught by Copilot
        review on PR #5283, commit 6639555b8.
        """
        envelope = {
            "Success": True,
            "Data": None,
            "Metadata": {"Script": "test.py", "Timestamp": "2026-03-08T12:00:00Z"},
        }
        errors = validate_envelope(envelope)
        assert any("Missing required field: Error" in e for e in errors)

    def test_non_string_metadata_fields_are_rejected(self) -> None:
        """skill-output.schema.json types Metadata.Script and
        Metadata.Timestamp as "type": "string". Checking only truthiness
        let {"Script": 1, "Timestamp": 1} pass silently, disagreeing with
        the schema. Caught by Copilot review on PR #5283, commit
        6639555b8.
        """
        envelope = {
            "Success": True,
            "Data": None,
            "Error": None,
            "Metadata": {"Script": 1, "Timestamp": 1},
        }
        errors = validate_envelope(envelope)
        assert any("Metadata.Script must be a string" in e for e in errors)
        assert any("Metadata.Timestamp must be a string" in e for e in errors)

    def test_non_string_error_message_is_rejected(self) -> None:
        """skill-output.schema.json types Error.Message as "type": "string".
        Caught by Copilot review on PR #5283, commit 6639555b8.
        """
        envelope = {
            "Success": False,
            "Data": None,
            "Error": {"Message": 123, "Code": 1, "Type": "General"},
            "Metadata": {"Script": "test.py", "Timestamp": "2026-03-08T12:00:00Z"},
        }
        errors = validate_envelope(envelope)
        assert any("Error.Message must be a string" in e for e in errors)

    def test_non_integer_error_code_is_rejected(self) -> None:
        """skill-output.schema.json types Error.Code as "type": "integer".
        Caught by Copilot review on PR #5283, commit 6639555b8.
        """
        envelope = {
            "Success": False,
            "Data": None,
            "Error": {"Message": "fail", "Code": "one", "Type": "General"},
            "Metadata": {"Script": "test.py", "Timestamp": "2026-03-08T12:00:00Z"},
        }
        errors = validate_envelope(envelope)
        assert any("Error.Code must be an integer" in e for e in errors)

    def test_boolean_error_code_is_rejected(self) -> None:
        """A JSON boolean is not a JSON integer, even though Python's `bool`
        subclasses `int` (`isinstance(True, int)` is `True`). A naive
        `isinstance(code, int)` check would accept `Code: true`.
        """
        envelope = {
            "Success": False,
            "Data": None,
            "Error": {"Message": "fail", "Code": True, "Type": "General"},
            "Metadata": {"Script": "test.py", "Timestamp": "2026-03-08T12:00:00Z"},
        }
        errors = validate_envelope(envelope)
        assert any("Error.Code must be an integer" in e for e in errors)

    def test_empty_error_message_is_rejected(self) -> None:
        """skill-output.schema.json types Error.Message with "minLength": 1.
        The `not message` truthiness check in
        _validate_error_message_and_code already rejects an empty string
        the same as a missing key (both are falsy), so this pins that the
        two stay aligned rather than adding a separate length branch.
        Copilot review on PR #5283.
        """
        envelope = {
            "Success": False,
            "Data": None,
            "Error": {"Message": "", "Code": 1, "Type": "General"},
            "Metadata": {"Script": "test.py", "Timestamp": "2026-03-08T12:00:00Z"},
        }
        errors = validate_envelope(envelope)
        assert any("Error.Message is required" in e for e in errors)

    def test_missing_metadata_version_is_valid(self) -> None:
        """skill-output.schema.json does not list Version in Metadata's
        required array (unlike Script and Timestamp), so an envelope with
        no Version must not be rejected.
        """
        envelope = {
            "Success": True,
            "Data": None,
            "Error": None,
            "Metadata": {"Script": "test.py", "Timestamp": "2026-03-08T12:00:00Z"},
        }
        assert validate_envelope(envelope) == []

    def test_non_string_metadata_version_is_rejected(self) -> None:
        """skill-output.schema.json types Metadata.Version as "type":
        "string" when present. Before this fix, nothing checked it, so a
        non-string value (for example `{"Version": 1}`) passed silently,
        disagreeing with the schema. Copilot review on PR #5283.
        """
        envelope = {
            "Success": True,
            "Data": None,
            "Error": None,
            "Metadata": {
                "Script": "test.py",
                "Timestamp": "2026-03-08T12:00:00Z",
                "Version": 1,
            },
        }
        errors = validate_envelope(envelope)
        assert any("Metadata.Version must be a string" in e for e in errors)

