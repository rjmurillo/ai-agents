"""Tests for the skill_output module's producer-side functions.

Covers:
- get_output_format resolution
- write_skill_output JSON envelope structure
- write_skill_error JSON envelope structure, including the
  error_type/message guards it raises ValueError for
- the three-way contract check tying write_skill_error's VALID_ERROR_TYPES
  to validate_skill_output.py's copy and the schema's enum

validate_envelope's own field-by-field contract tests live in
test_validate_envelope.py, split out once this file crossed the 500-line
taste-lint gate (ADR-103 Round 5). CLI subprocess integration tests
(invalid JSON, path traversal, symlink attacks) live in
test_skill_output_cli.py, split out earlier for the same reason.
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

    def test_rejects_empty_message(self, capsys: pytest.CaptureFixture[str]) -> None:
        """skill-output.schema.json requires Error.Message "minLength": 1
        (ADR-103 Round 5), but before this fix nothing on the producer side
        prevented constructing one: `write_skill_error("", 1)` built a
        schema-invalid envelope and printed it. A no-arg exception
        (`str(Exception())` is `""`) reaching a bare `write_skill_error(str(exc),
        ...)` call site would have hit this silently. Guarding at the
        producer, the same way error_type is already guarded, closes the
        gap for real instead of leaving it as a documented, unenforced risk
        (adr-review critic seat, ADR-103 Round 5 convergence check).
        """
        with pytest.raises(ValueError, match="message must be non-empty"):
            write_skill_error("", 1, output_format="json")
        # The guard must fire before anything is printed: a partial or
        # malformed envelope on stdout would be worse than the exception.
        assert capsys.readouterr().out == ""

    def test_rejects_non_string_message(self, capsys: pytest.CaptureFixture[str]) -> None:
        """`if not message:` is a truthiness check, not a type check: a
        truthy non-string value (`123`, a list, an exception object
        passed by mistake instead of `str(exc)`) passed the emptiness
        guard and still reached `json.dumps`, producing
        `Error.Message: 123`, which both the schema ("type": "string")
        and validate_envelope reject. Same producer/schema disagreement
        class as test_rejects_empty_message and
        test_rejects_boolean_exit_code, one field over. Copilot review
        on PR #5283.
        """
        with pytest.raises(ValueError, match="message must be a string"):
            write_skill_error(123, 1, output_format="json")  # type: ignore[arg-type]
        assert capsys.readouterr().out == ""

    def test_rejects_boolean_exit_code(self, capsys: pytest.CaptureFixture[str]) -> None:
        """skill-output.schema.json types Error.Code as "type": "integer".
        `exit_code=True` type-checks under mypy (bool is-a int under PEP
        484 nominal subtyping) and passes a naive `isinstance(exit_code,
        int)` check (Python's bool subclasses int), but the schema and
        validate_skill_output.py both reject `Code: true` as not an
        integer. Same producer/schema disagreement class as
        test_rejects_empty_message above, found while re-checking for
        other instances (adr-review independent-thinker seat, ADR-103
        Round 5 convergence check, finding F1).
        """
        with pytest.raises(ValueError, match="exit_code must be an integer"):
            write_skill_error("test", True, output_format="json")
        assert capsys.readouterr().out == ""
