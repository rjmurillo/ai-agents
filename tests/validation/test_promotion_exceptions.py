"""Promotion exception records: loader, fingerprint, and status rules.

ADR-113 decisions 6, 7, and 8, issue #5636. Each rule has a test that feeds it
the input the rule exists to refuse.
"""

from __future__ import annotations

import json
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any, cast

import pytest

from scripts.validation import promotion_exceptions
from scripts.validation.promotion_exceptions import (
    EXCEPTIONS_RELATIVE_PATH,
    MAX_FILE_BYTES,
    ExceptionsFileError,
    ExceptionStatus,
    PromotionException,
    deny_all_approvals,
    exception_status,
    finding_fingerprint,
    load_exceptions,
    parse_exceptions,
    utc_today,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
TODAY = date(2026, 10, 1)


def _entry(**overrides: Any) -> dict[str, Any]:
    entry: dict[str, Any] = {
        "validator": "pytest",
        "reason": "tests.failed",
        "scope": "tests/",
        "rationale": "Known flaky test tracked in a ticket.",
        "owner": "rjmurillo",
        "approval": {"pr": 100, "reviewer": "second-owner"},
        "expires": "2026-12-31",
        "remediate_by": "2026-11-30",
    }
    entry.update(overrides)
    return entry


def _doc(*entries: dict[str, Any]) -> dict[str, Any]:
    return {"schema_version": "1", "entries": list(entries)}


def _record(**overrides: Any) -> PromotionException:
    return parse_exceptions(_doc(_entry(**overrides)))[0]


def _approve(_record: PromotionException) -> bool:
    return True


class TestFingerprint:
    def test_same_inputs_give_the_same_fingerprint(self) -> None:
        assert finding_fingerprint("v", "r.x", "s", "i") == finding_fingerprint(
            "v", "r.x", "s", "i"
        )

    @pytest.mark.parametrize("field", range(4))
    def test_each_field_changes_the_fingerprint(self, field: int) -> None:
        base = ["v", "r.x", "s", "i"]
        changed = list(base)
        changed[field] += "2"
        assert finding_fingerprint(*base) != finding_fingerprint(*changed)

    def test_field_boundary_is_not_ambiguous(self) -> None:
        assert finding_fingerprint("a", "bc", "s") != finding_fingerprint("ab", "c", "s")

    def test_empty_item_is_the_default(self) -> None:
        assert finding_fingerprint("v", "r.x", "s") == finding_fingerprint("v", "r.x", "s", "")


class TestFingerprintCollisions:
    def test_unit_separator_in_scope_cannot_mimic_an_item(self) -> None:
        assert finding_fingerprint("v", "r.x", "a\x1fb") != finding_fingerprint(
            "v", "r.x", "a", "b"
        )


class TestParse:
    def test_valid_entry_builds_a_record(self) -> None:
        record = _record(item="a/b.py")
        assert record.validator == "pytest"
        assert record.item == "a/b.py"
        assert record.approval_pr == 100
        assert record.approver == "second-owner"
        assert record.expires == date(2026, 12, 31)
        assert record.fingerprint == finding_fingerprint(
            "pytest", "tests.failed", "tests/", "a/b.py"
        )

    def test_item_is_optional(self) -> None:
        assert _record().item == ""

    def test_empty_entries_list_is_valid(self) -> None:
        assert parse_exceptions(_doc()) == ()

    @pytest.mark.parametrize(
        "field",
        [
            "validator",
            "reason",
            "scope",
            "rationale",
            "owner",
            "approval",
            "expires",
            "remediate_by",
        ],
    )
    def test_each_required_field_is_required(self, field: str) -> None:
        entry = _entry()
        del entry[field]
        with pytest.raises(ExceptionsFileError, match="missing"):
            parse_exceptions(_doc(entry))

    @pytest.mark.parametrize("field", ["validator", "scope", "rationale", "reason"])
    @pytest.mark.parametrize("bad", ["", "   ", 5, None])
    def test_blank_or_nontext_fields_are_refused(self, field: str, bad: Any) -> None:
        entry = _entry()
        entry[field] = bad
        with pytest.raises(ExceptionsFileError, match=f"'{field}'"):
            parse_exceptions(_doc(entry))

    def test_control_character_in_text_is_refused(self) -> None:
        with pytest.raises(ExceptionsFileError, match="control character"):
            parse_exceptions(_doc(_entry(rationale="line\n::error::forged")))

    @pytest.mark.parametrize("bad", [None, 5, ["a"]])
    def test_present_item_must_be_a_string(self, bad: Any) -> None:
        with pytest.raises(ExceptionsFileError, match="'item'"):
            parse_exceptions(_doc(_entry(item=bad)))

    def test_item_with_control_character_is_refused(self) -> None:
        with pytest.raises(ExceptionsFileError, match="'item'"):
            parse_exceptions(_doc(_entry(item="a\tb")))

    def test_reason_must_be_a_dotted_slug(self) -> None:
        with pytest.raises(ExceptionsFileError, match="dotted lowercase slug"):
            parse_exceptions(_doc(_entry(reason="Tests Failed")))

    @pytest.mark.parametrize("bad", ["", "-x", "a b", "a/b", 7])
    def test_owner_must_be_a_handle(self, bad: Any) -> None:
        with pytest.raises(ExceptionsFileError, match="'owner'"):
            parse_exceptions(_doc(_entry(owner=bad)))

    @pytest.mark.parametrize("field", ["expires", "remediate_by"])
    @pytest.mark.parametrize("bad", ["", "2026-13-01", "2026-02-30", "10/01/2026", None, 20261001])
    def test_dates_must_be_real_iso_dates(self, field: str, bad: Any) -> None:
        entry = _entry()
        entry[field] = bad
        with pytest.raises(ExceptionsFileError, match=f"'{field}'"):
            parse_exceptions(_doc(entry))

    def test_remediation_after_expiry_is_refused(self) -> None:
        with pytest.raises(ExceptionsFileError, match="must not be after"):
            parse_exceptions(_doc(_entry(expires="2026-11-01", remediate_by="2026-11-02")))

    def test_remediation_on_the_expiry_day_is_allowed(self) -> None:
        assert _record(expires="2026-11-01", remediate_by="2026-11-01")

    @pytest.mark.parametrize(
        "approval",
        [
            "second-owner",
            {"pr": 1},
            {"reviewer": "x"},
            {"pr": 1, "reviewer": "x", "extra": 1},
            {"pr": 0, "reviewer": "x"},
            {"pr": True, "reviewer": "x"},
            {"pr": "1", "reviewer": "x"},
            {"pr": 1, "reviewer": "bad handle"},
        ],
    )
    def test_approval_shape_is_enforced(self, approval: Any) -> None:
        with pytest.raises(ExceptionsFileError, match="approval"):
            parse_exceptions(_doc(_entry(approval=approval)))

    def test_unknown_key_is_refused(self) -> None:
        with pytest.raises(ExceptionsFileError, match="unknown key"):
            parse_exceptions(_doc(_entry(extra="x")))

    def test_non_object_entry_is_refused(self) -> None:
        with pytest.raises(ExceptionsFileError, match="JSON object"):
            parse_exceptions({"schema_version": "1", "entries": ["x"]})

    def test_duplicate_finding_is_refused(self) -> None:
        with pytest.raises(ExceptionsFileError, match="same finding"):
            parse_exceptions(_doc(_entry(), _entry(rationale="again")))

    def test_every_bad_entry_is_named(self) -> None:
        with pytest.raises(ExceptionsFileError) as caught:
            parse_exceptions(_doc(_entry(owner=""), _entry(scope="")))
        assert "entries[0]" in str(caught.value)
        assert "entries[1]" in str(caught.value)

    @pytest.mark.parametrize(
        "document",
        [
            [],
            "x",
            None,
            {"schema_version": "2", "entries": []},
            {"schema_version": "1"},
            {"schema_version": "1", "entries": {}},
        ],
    )
    def test_bad_document_shape_is_refused(self, document: Any) -> None:
        with pytest.raises(ExceptionsFileError):
            parse_exceptions(document)


class TestLoad:
    def test_missing_file_excuses_nothing(self, tmp_path: Path) -> None:
        assert load_exceptions(tmp_path) == ()

    def test_valid_file_loads(self, tmp_path: Path) -> None:
        path = tmp_path / EXCEPTIONS_RELATIVE_PATH
        path.parent.mkdir(parents=True)
        path.write_text(json.dumps(_doc(_entry())), encoding="utf-8")
        assert len(load_exceptions(tmp_path)) == 1

    def test_malformed_json_fails_the_load(self, tmp_path: Path) -> None:
        path = tmp_path / EXCEPTIONS_RELATIVE_PATH
        path.parent.mkdir(parents=True)
        path.write_text("{not json", encoding="utf-8")
        with pytest.raises(ExceptionsFileError, match="cannot parse"):
            load_exceptions(tmp_path)

    def test_undecodable_bytes_fail_the_load(self, tmp_path: Path) -> None:
        path = tmp_path / EXCEPTIONS_RELATIVE_PATH
        path.parent.mkdir(parents=True)
        path.write_bytes(b"\xff\xfe\x00")
        with pytest.raises(ExceptionsFileError, match="cannot read"):
            load_exceptions(tmp_path)

    def test_unreadable_path_fails_the_load(self, tmp_path: Path) -> None:
        (tmp_path / EXCEPTIONS_RELATIVE_PATH).mkdir(parents=True)
        with pytest.raises(ExceptionsFileError, match="cannot read"):
            load_exceptions(tmp_path)

    def test_shipped_file_loads_and_is_empty(self) -> None:
        """Decision 7: with one code owner the shipped file excuses nothing."""
        assert load_exceptions(REPO_ROOT) == ()


class TestStatus:
    def test_active_when_unexpired_on_time_and_approved(self) -> None:
        assert exception_status(_record(), TODAY, _approve) is ExceptionStatus.ACTIVE

    def test_expiry_day_itself_is_still_active(self) -> None:
        record = _record(expires="2026-10-01", remediate_by="2026-10-01")
        assert exception_status(record, TODAY, _approve) is ExceptionStatus.ACTIVE

    def test_day_after_expiry_is_expired(self) -> None:
        record = _record(expires="2026-09-30", remediate_by="2026-09-30")
        assert exception_status(record, TODAY, _approve) is ExceptionStatus.EXPIRED

    def test_expired_wins_over_overdue_and_unapproved(self) -> None:
        record = _record(expires="2026-09-30", remediate_by="2026-09-01")
        assert exception_status(record, TODAY, deny_all_approvals) is ExceptionStatus.EXPIRED

    def test_open_finding_past_remediation_date_is_overdue(self) -> None:
        record = _record(remediate_by="2026-09-30", expires="2026-12-31")
        status = exception_status(record, TODAY, _approve)
        assert status is ExceptionStatus.REMEDIATION_OVERDUE

    def test_overdue_is_not_applied_to_a_closed_finding(self) -> None:
        record = _record(remediate_by="2026-09-30", expires="2026-12-31")
        status = exception_status(record, TODAY, _approve, finding_open=False)
        assert status is ExceptionStatus.ACTIVE

    def test_unproven_approval_licenses_nothing(self) -> None:
        status = exception_status(_record(), TODAY, deny_all_approvals)
        assert status is ExceptionStatus.UNAPPROVED

    def test_deny_all_refuses_every_record(self) -> None:
        assert deny_all_approvals(_record()) is False

    def test_verifier_receives_the_record(self) -> None:
        seen: list[PromotionException] = []

        def verifier(record: PromotionException) -> bool:
            seen.append(record)
            return True

        record = _record()
        exception_status(record, TODAY, verifier)
        assert seen == [record]


class TestSerialization:
    def test_to_dict_carries_every_governed_field(self) -> None:
        data = _record(item="x").to_dict()
        assert data["fingerprint"] == _record(item="x").fingerprint
        assert data["approval"] == {"pr": 100, "reviewer": "second-owner"}
        assert data["expires"] == "2026-12-31"
        assert data["remediate_by"] == "2026-11-30"
        assert data["owner"] == "rjmurillo"


class TestHardening:
    @pytest.mark.parametrize("bad", ["bob\n", "bob\u202e", "bob\x7f", "bo\u200bb"])
    def test_handles_reject_trailing_newline_and_format_characters(self, bad: str) -> None:
        with pytest.raises(ExceptionsFileError, match="'owner'"):
            parse_exceptions(_doc(_entry(owner=bad)))
        with pytest.raises(ExceptionsFileError, match="reviewer"):
            parse_exceptions(_doc(_entry(approval={"pr": 1, "reviewer": bad})))

    @pytest.mark.parametrize("bad", ["a\u202eb", "a\u2028b", "a\x85b", "a\u2029b"])
    def test_text_rejects_bidi_and_line_separators(self, bad: str) -> None:
        with pytest.raises(ExceptionsFileError, match="control character"):
            parse_exceptions(_doc(_entry(rationale=bad)))

    def test_date_with_trailing_newline_is_refused(self) -> None:
        with pytest.raises(ExceptionsFileError, match="'expires'"):
            parse_exceptions(_doc(_entry(expires="2026-12-31\n")))

    def test_reason_with_trailing_newline_is_refused(self) -> None:
        with pytest.raises(ExceptionsFileError, match="'reason'"):
            parse_exceptions(_doc(_entry(reason="tests.failed\n")))

    def test_duplicate_json_keys_fail_the_load(self, tmp_path: Path) -> None:
        path = tmp_path / EXCEPTIONS_RELATIVE_PATH
        path.parent.mkdir(parents=True)
        path.write_text('{"schema_version": "1", "entries": [], "entries": []}', encoding="utf-8")
        with pytest.raises(ExceptionsFileError, match="duplicate key"):
            load_exceptions(tmp_path)

    def test_many_distinct_keys_load_in_linear_time(self, tmp_path: Path) -> None:
        path = tmp_path / EXCEPTIONS_RELATIVE_PATH
        path.parent.mkdir(parents=True)
        body = ",".join(f'"k{i}": 1' for i in range(50000))
        path.write_text('{"schema_version": "1", "entries": [], ' + body + "}", encoding="utf-8")
        assert load_exceptions(tmp_path) == ()

    def test_symlinked_file_fails_the_load(self, tmp_path: Path) -> None:
        target = tmp_path / "real.json"
        target.write_text(json.dumps(_doc()), encoding="utf-8")
        link = tmp_path / EXCEPTIONS_RELATIVE_PATH
        link.parent.mkdir(parents=True)
        link.symlink_to(target)
        with pytest.raises(ExceptionsFileError, match="cannot read"):
            load_exceptions(tmp_path)

    def test_symlink_to_an_endless_device_does_not_hang(self, tmp_path: Path) -> None:
        link = tmp_path / EXCEPTIONS_RELATIVE_PATH
        link.parent.mkdir(parents=True)
        link.symlink_to("/dev/zero")
        with pytest.raises(ExceptionsFileError, match="cannot read"):
            load_exceptions(tmp_path)

    def test_oversized_file_fails_the_load(self, tmp_path: Path) -> None:
        path = tmp_path / EXCEPTIONS_RELATIVE_PATH
        path.parent.mkdir(parents=True)
        path.write_text(" " * (MAX_FILE_BYTES + 1), encoding="utf-8")
        with pytest.raises(ExceptionsFileError, match="larger than"):
            load_exceptions(tmp_path)

    def test_deeply_nested_json_fails_the_load(self, tmp_path: Path) -> None:
        path = tmp_path / EXCEPTIONS_RELATIVE_PATH
        path.parent.mkdir(parents=True)
        path.write_text("[" * 100000, encoding="utf-8")
        with pytest.raises(ExceptionsFileError, match="cannot parse"):
            load_exceptions(tmp_path)

    def test_verifier_that_raises_reads_as_unapproved(self) -> None:
        def broken(_record: PromotionException) -> bool:
            raise RuntimeError("api down")

        assert exception_status(_record(), TODAY, broken) is ExceptionStatus.UNAPPROVED

    def test_verifier_returning_a_truthy_non_bool_is_unapproved(self) -> None:
        def sloppy(_record: PromotionException) -> bool:
            return cast("bool", "error")

        assert exception_status(_record(), TODAY, sloppy) is ExceptionStatus.UNAPPROVED

    def test_utc_today_reads_the_clock_in_utc(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Freeze a moment where UTC and a UTC+14 clock disagree on the date."""
        seen: list[Any] = []
        frozen = datetime(2026, 10, 1, 23, 30, tzinfo=UTC)

        class FrozenClock:
            @staticmethod
            def now(tz: Any = None) -> datetime:
                seen.append(tz)
                return frozen.astimezone(tz)

        monkeypatch.setattr(promotion_exceptions, "datetime", FrozenClock)
        assert utc_today() == date(2026, 10, 1)
        assert seen == [UTC]
