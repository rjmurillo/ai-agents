"""Inline NotFound envelopes keep the write_skill_error shape.

test_pr_merged.py and test_pr_merge_ready.py build their NotFound envelope by
hand, so their success output stays flat. Their docstrings claim the shape
matches write_skill_error. These tests hold that claim: a key added to or
dropped from either side fails here.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from tests.skills.claude_skills_import import import_skill_script

# Unique module names keep these copies out of sys.modules["test_pr_merged"],
# which other test files patch by that name.
_merged = import_skill_script(
    ".claude/skills/github/scripts/pr/test_pr_merged.py",
    module_name="_conformance_test_pr_merged",
)
_ready = import_skill_script(
    ".claude/skills/github/scripts/pr/test_pr_merge_ready.py",
    module_name="_conformance_test_pr_merge_ready",
)


def _shape(value: Any) -> Any:
    """Return the nested key structure of an envelope, without its values."""
    if isinstance(value, dict):
        return {key: _shape(item) for key, item in value.items()}
    return type(value).__name__


def _reference_shape(capsys: pytest.CaptureFixture[str], data: dict[str, Any]) -> Any:
    from github_core.output import write_skill_error

    write_skill_error(
        "PR #9 not found",
        3,
        error_type="NotFound",
        output_format="json",
        script_name="reference.py",
        extra=data,
    )
    envelope = json.loads(capsys.readouterr().out)
    return _shape(envelope)


def test_merged_envelope_matches_write_skill_error(capsys: pytest.CaptureFixture[str]) -> None:
    assert _merged._exit_not_found(9, "o", "r") == 3
    actual = json.loads(capsys.readouterr().out)

    assert actual["Error"]["Type"] == "NotFound"
    expected = _reference_shape(capsys, {"pull_request": 9, "owner": "o", "repo": "r"})
    assert _shape(actual) == expected


def test_merge_ready_envelope_matches_write_skill_error(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as exc_info:
        _ready._exit_pr_not_found("PR #9 not found", 9)
    assert exc_info.value.code == 3
    actual = json.loads(capsys.readouterr().out)

    assert actual["Error"]["Type"] == "NotFound"
    expected = _reference_shape(capsys, {"pull_request": 9})
    assert _shape(actual) == expected


def test_shape_comparison_catches_a_dropped_key(capsys: pytest.CaptureFixture[str]) -> None:
    """Negative control: a missing Metadata key must change the shape."""
    assert _merged._exit_not_found(9, "o", "r") == 3
    actual = json.loads(capsys.readouterr().out)
    del actual["Metadata"]["Version"]

    expected = _reference_shape(capsys, {"pull_request": 9, "owner": "o", "repo": "r"})
    assert _shape(actual) != expected
