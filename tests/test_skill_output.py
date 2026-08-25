"""Tests for skill_output module and validate_skill_output script.

Covers:
- get_output_format resolution
- write_skill_output JSON envelope structure
- write_skill_error JSON envelope structure
- validate_skill_output integration (valid, invalid, path traversal)
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from unittest import mock

import pytest

# Add scripts directory to path for imports
REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = REPO_ROOT / "scripts"
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


class TestValidateSkillOutputScript:
    """Integration tests for validate_skill_output.py CLI."""

    def _run_validator(self, json_input: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(SCRIPTS_DIR / "validate_skill_output.py")],
            input=json_input,
            capture_output=True,
            text=True, encoding="utf-8",
            timeout=30,
        )

    def test_validates_success_envelope(self) -> None:
        envelope = {
            "Success": True,
            "Data": {"Result": "ok"},
            "Error": None,
            "Metadata": {
                "Script": "test.py",
                "Version": "1.0.0",
                "Timestamp": "2026-03-08T12:00:00Z",
            },
        }
        result = self._run_validator(json.dumps(envelope))
        assert result.returncode == 0
        assert "PASS" in result.stdout

    def test_validates_error_envelope(self) -> None:
        envelope = {
            "Success": False,
            "Data": None,
            "Error": {"Message": "fail", "Code": 1, "Type": "General"},
            "Metadata": {
                "Script": "test.py",
                "Version": "1.0.0",
                "Timestamp": "2026-03-08T12:00:00Z",
            },
        }
        result = self._run_validator(json.dumps(envelope))
        assert result.returncode == 0

    def test_rejects_invalid_json(self) -> None:
        result = self._run_validator("not json")
        assert result.returncode == 1

    def test_rejects_path_traversal(self) -> None:
        traversal = str(REPO_ROOT / ".." / ".." / ".." / "etc" / "passwd")
        result = subprocess.run(
            [
                sys.executable,
                str(SCRIPTS_DIR / "validate_skill_output.py"),
                "--input-file",
                traversal,
            ],
            capture_output=True,
            text=True, encoding="utf-8",
            timeout=30,
        )
        assert result.returncode == 1
        assert "Path traversal attempt detected" in result.stdout

    @pytest.mark.skipif(sys.platform == "win32", reason="Symlinks require privileges on Windows")
    def test_rejects_symlink_traversal(self, external_tmp_path: Path) -> None:
        # Create external file outside repo
        external_file = external_tmp_path / "external.json"
        external_file.write_text('{"Success": true}')

        # Create symlink inside repo pointing outside
        symlink_path = REPO_ROOT / f"test-symlink-{os.getpid()}.json"
        try:
            symlink_path.symlink_to(external_file)
            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPTS_DIR / "validate_skill_output.py"),
                    "--input-file",
                    str(symlink_path),
                ],
                capture_output=True,
                text=True, encoding="utf-8",
                timeout=30,
            )
            assert result.returncode == 1
            assert "Path traversal attempt detected" in result.stdout
        finally:
            symlink_path.unlink(missing_ok=True)
