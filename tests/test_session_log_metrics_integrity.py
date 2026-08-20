"""Tests for two session-log integrity gaps (issues #4405 and #4415).

#4405: four checklist items a session log needs at ``"level": "MUST"`` were
absent from ``SESSION_START_REQUIRED_ITEMS``. Deleting one of those keys passed
validation while leaving it present-and-incomplete failed, so the gate was
strictly easier to satisfy by removing a checklist item than by doing the work
it names.

#4415: a log whose ``session.startingCommit`` equals its ``endingCommit``
claims a base that is also its tip. The episode extractor excludes the base
commit by design, so the session's only commit vanishes and the episode records
``metrics.commits`` 0, which the episode-store ratchet then rejects several
steps away from the field that was actually wrong.

Fixtures build a session log by hand against ``SESSION_START_REQUIRED_ITEMS``/
``SESSION_END_REQUIRED_ITEMS`` directly. A generator (``new_session_log_json.py``,
under the session-init skill) used to produce this shape and a parity test
pinned the two together; both were deleted with the skill (issue #5138), and
session logs are now written by hand, so these required-items sets are the
sole source of truth for the checklist shape.
"""

from __future__ import annotations

import copy
from typing import Any

import pytest

from scripts.validate_session_json import (
    SESSION_END_REQUIRED_ITEMS,
    SESSION_START_REQUIRED_ITEMS,
    ValidationResult,
    validate_evidence_agrees_with_session,
    validate_session_start,
)

_SHA_A = "1" * 40
_SHA_B = "2" * 40
_SAME_COMMIT_PREFIX = "startingCommit and endingCommit are the same commit"


def _generated_log() -> dict[str, Any]:
    """A hand-built session log with every checklist item incomplete.

    Mirrors the shape the deleted generator used to produce: every required
    sessionStart/sessionEnd item at its documented level, plus one SHOULD
    item (``gitStatusVerified``) so tests have a non-MUST control.
    """
    session_start = {
        name: {"Complete": False, "Evidence": "", "level": "MUST"}
        for name in SESSION_START_REQUIRED_ITEMS
    }
    session_start["gitStatusVerified"] = {
        "Complete": False,
        "Evidence": "",
        "level": "SHOULD",
    }
    session_end = {
        name: {"Complete": False, "Evidence": "", "level": "MUST"}
        for name in SESSION_END_REQUIRED_ITEMS
    }
    return {
        "schemaVersion": "1.0",
        "session": {
            "number": 1,
            "date": "2026-08-03",
            "branch": "feature/x",
            "startingCommit": _SHA_A,
            "objective": "probe",
        },
        "protocolCompliance": {
            "sessionStart": session_start,
            "sessionEnd": session_end,
        },
        "workLog": [],
        "endingCommit": "",
        "nextSteps": [],
    }


def _set_complete(item: dict[str, Any], value: bool) -> None:
    """Set an item's completion flag under whichever spelling it already uses.

    The generator emits ``Complete``; the validator reads either case. Writing
    a second lowercase key would leave two flags disagreeing, and the validator
    would answer from the one it found first rather than the one the test set.
    """
    key = "Complete" if "Complete" in item else "complete"
    item[key] = value


def _completed_log() -> dict[str, Any]:
    """A generated log with every checklist item marked complete.

    A freshly generated log has every item at ``Complete: False`` by design, so
    it is expected to fail validation. Tests that assert an absence of errors
    need a log that is otherwise clean, or they measure the template rather
    than the change under test.
    """
    log = _generated_log()
    for section in log["protocolCompliance"].values():
        for item in section.values():
            if isinstance(item, dict):
                _set_complete(item, True)
                if not item.get("Evidence"):
                    item["Evidence"] = "verified"
    return log


class TestSessionStartRequiredItems:
    def test_the_four_added_keys_are_required(self) -> None:
        for name in (
            "skillScriptsListed",
            "usageMandatoryRead",
            "constraintsRead",
            "memoriesLoaded",
        ):
            assert name in SESSION_START_REQUIRED_ITEMS

    @pytest.mark.parametrize(
        "deleted",
        ["skillScriptsListed", "usageMandatoryRead", "constraintsRead", "memoriesLoaded"],
    )
    def test_deleting_a_must_item_is_caught(self, deleted: str) -> None:
        section = copy.deepcopy(_generated_log()["protocolCompliance"]["sessionStart"])
        assert deleted in section
        del section[deleted]
        result = ValidationResult()
        validate_session_start(section, result)
        assert any(deleted in error for error in result.errors), (
            f"deleting {deleted} produced no error naming it: {result.errors}"
        )

    def test_deleting_a_should_item_stays_silent(self) -> None:
        """Negative control. ``gitStatusVerified`` is SHOULD, not MUST, so its
        absence must remain tolerated. Without this the test above would pass
        for a validator that simply rejects every missing key."""
        section = copy.deepcopy(_completed_log()["protocolCompliance"]["sessionStart"])
        should = sorted(
            name
            for name, body in section.items()
            if isinstance(body, dict) and body.get("level") != "MUST"
        )
        assert should, "no SHOULD item to use as a control"
        del section[should[0]]
        result = ValidationResult()
        validate_session_start(section, result)
        assert not result.errors

    def test_an_intact_section_validates_clean(self) -> None:
        result = ValidationResult()
        validate_session_start(_completed_log()["protocolCompliance"]["sessionStart"], result)
        assert not result.errors


def _log_with_commits(starting: str, ending: str, *, committed: bool = True) -> dict[str, Any]:
    log = _completed_log()
    log["session"]["startingCommit"] = starting
    log["endingCommit"] = ending
    _set_complete(log["protocolCompliance"]["sessionEnd"]["changesCommitted"], committed)
    return log


def _same_commit_errors(log: dict[str, Any]) -> list[str]:
    result = ValidationResult()
    validate_evidence_agrees_with_session(log, result)
    return [error for error in result.errors if error.startswith(_SAME_COMMIT_PREFIX)]


class TestStartingCommitIsNotAlsoEnding:
    def test_identical_shas_are_rejected(self) -> None:
        errors = _same_commit_errors(_log_with_commits(_SHA_A, _SHA_A))
        assert len(errors) == 1
        assert "4415" in errors[0]

    def test_distinct_shas_are_accepted(self) -> None:
        assert not _same_commit_errors(_log_with_commits(_SHA_B, _SHA_A))

    def test_abbreviation_does_not_evade_the_check(self) -> None:
        """``_same_commit`` treats a 7-char prefix as the same commit, so a log
        abbreviating one field and not the other must still be caught."""
        assert _same_commit_errors(_log_with_commits(_SHA_A[:7], _SHA_A))

    def test_silent_when_nothing_was_committed(self) -> None:
        """A session that committed nothing legitimately ends where it began."""
        assert not _same_commit_errors(_log_with_commits(_SHA_A, _SHA_A, committed=False))

    def test_silent_when_ending_commit_is_absent(self) -> None:
        log = _log_with_commits(_SHA_A, _SHA_A)
        log["endingCommit"] = ""
        assert not _same_commit_errors(log)

    def test_silent_when_starting_commit_is_absent(self) -> None:
        log = _log_with_commits(_SHA_A, _SHA_A)
        log["session"]["startingCommit"] = ""
        assert not _same_commit_errors(log)

    def test_message_names_the_field_to_change(self) -> None:
        """The value of this error is that it points at ``startingCommit``. A
        message that only reported the symptom would send the reader to the
        extractor, which is behaving correctly."""
        errors = _same_commit_errors(_log_with_commits(_SHA_A, _SHA_A))
        assert "startingCommit" in errors[0]
        assert "parent" in errors[0]
