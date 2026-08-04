"""Tests for two session-log integrity gaps (issues #4405 and #4415).

#4405: four checklist items the generator emits at ``"level": "MUST"`` were
absent from ``SESSION_START_REQUIRED_ITEMS``. Deleting one of those keys passed
validation while leaving it present-and-incomplete failed, so the gate was
strictly easier to satisfy by removing a checklist item than by doing the work
it names. The parity test below pins the generator and the validator together
so the two lists cannot drift apart again.

#4415: a log whose ``session.startingCommit`` equals its ``endingCommit``
claims a base that is also its tip. The episode extractor excludes the base
commit by design, so the session's only commit vanishes and the episode records
``metrics.commits`` 0, which the episode-store ratchet then rejects several
steps away from the field that was actually wrong.
"""

from __future__ import annotations

import copy
import sys
from pathlib import Path
from typing import Any

import pytest

from scripts.validate_session_json import (
    SESSION_END_REQUIRED_ITEMS,
    SESSION_START_REQUIRED_ITEMS,
    ValidationResult,
    validate_evidence_agrees_with_session,
    validate_session_start,
)

_SESSION_INIT = Path(__file__).resolve().parents[1] / ".claude" / "skills" / "session-init"
sys.path.insert(0, str(_SESSION_INIT))

from session_init.session_structure import build_session_log  # noqa: E402

_SHA_A = "1" * 40
_SHA_B = "2" * 40
_SAME_COMMIT_PREFIX = "startingCommit and endingCommit are the same commit"


def _generated_log() -> dict[str, Any]:
    return build_session_log(
        branch="feature/x",
        commit=_SHA_A,
        session_number=1,
        objective="probe",
        current_date="2026-08-03",
    )


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


def _must_items(log: dict[str, Any], section: str) -> set[str]:
    items = log["protocolCompliance"][section]
    return {
        name
        for name, body in items.items()
        if isinstance(body, dict) and body.get("level") == "MUST"
    }


class TestGeneratorValidatorParity:
    """Every MUST item the generator emits must be required by the validator.

    This is the regression guard for #4405. Without it, adding a MUST item to
    the generator silently widens the hole: the new key is unenforced, so a log
    that omits it validates clean.
    """

    @pytest.mark.parametrize(
        ("section", "required"),
        [
            ("sessionStart", SESSION_START_REQUIRED_ITEMS),
            ("sessionEnd", SESSION_END_REQUIRED_ITEMS),
        ],
    )
    def test_every_generator_must_item_is_required(
        self, section: str, required: frozenset[str]
    ) -> None:
        musts = _must_items(_generated_log(), section)
        assert musts, f"{section} emitted no MUST items; the probe is measuring nothing"
        missing = musts - set(required)
        assert not missing, (
            f"{section} MUST items absent from the validator's required set: "
            f"{sorted(missing)}. A log omitting any of these validates clean, "
            f"so the gate is easier to pass by deleting the item than by "
            f"completing it (issue #4405)."
        )

    @pytest.mark.parametrize("section", ["sessionStart", "sessionEnd"])
    def test_required_set_names_no_item_the_generator_omits(self, section: str) -> None:
        """The reverse direction: a required key the generator never emits would
        make every freshly generated log invalid on creation."""
        required = (
            SESSION_START_REQUIRED_ITEMS
            if section == "sessionStart"
            else SESSION_END_REQUIRED_ITEMS
        )
        emitted = set(_generated_log()["protocolCompliance"][section])
        assert not (set(required) - emitted)


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
