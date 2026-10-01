"""Promotion evidence: strict parsing and two-tier binding to the candidate.

ADR-113 decisions 2 and 4, issue #5636. A record that does not name the
candidate must be rejected, and every rejection must stay visible.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

import pytest

from scripts.validation.evidence import EvidenceState
from scripts.validation.promotion_evidence import (
    MAX_EVIDENCE_BYTES,
    REASON_CANDIDATE_DIGEST_ABSENT,
    REASON_DIGEST_MISMATCH,
    REASON_DIGEST_MISSING,
    REASON_MALFORMED,
    REASON_REVISION_MISMATCH,
    REASON_UNREADABLE,
    BindingTier,
    Candidate,
    EvidenceError,
    bind_records,
    binding_problem,
    load_evidence_dir,
    parse_evidence,
)

SHA = "a" * 40
OTHER_SHA = "b" * 40
DIGEST = "c" * 64
OTHER_DIGEST = "d" * 64


def _doc(**overrides: Any) -> dict[str, Any]:
    doc: dict[str, Any] = {
        "validator": "pytest",
        "state": "PASS",
        "revision": SHA,
        "scope": "tests/",
        "reason": "",
        "detail": "",
        "examined": 10,
        "findings": 0,
        "duration_seconds": 1.5,
    }
    doc.update(overrides)
    return doc


def _record(**overrides: Any):
    return parse_evidence(_doc(**overrides), "x.json")


class TestCandidate:
    def test_accepts_a_full_sha_with_and_without_digest(self) -> None:
        assert Candidate(SHA).digest == ""
        assert Candidate(SHA, DIGEST).digest == DIGEST

    @pytest.mark.parametrize("sha", ["", "abc123", "A" * 40, "g" * 40, "a" * 41, " " + "a" * 39])
    def test_rejects_a_bad_sha(self, sha: str) -> None:
        with pytest.raises(ValueError, match="40-character"):
            Candidate(sha)

    @pytest.mark.parametrize("digest", ["abc", "C" * 64, "c" * 63, "z" * 64])
    def test_rejects_a_bad_digest(self, digest: str) -> None:
        with pytest.raises(ValueError, match="64 lowercase"):
            Candidate(SHA, digest)


class TestParse:
    def test_valid_pass_record(self) -> None:
        record = _record()
        assert record.outcome.state is EvidenceState.PASS
        assert record.outcome.revision == SHA
        assert record.source == "x.json"

    def test_round_trips_check_outcome_to_dict(self) -> None:
        original = _record().outcome
        assert parse_evidence(original.to_dict()).outcome == original

    def test_digest_and_items_are_carried(self) -> None:
        record = _record(digest=DIGEST, items=["a.py", "b.py"], state="FAIL", reason="x.y")
        assert record.digest == DIGEST
        assert record.items == ("a.py", "b.py")

    def test_fail_record_needs_a_reason(self) -> None:
        with pytest.raises(EvidenceError, match="reason"):
            _record(state="FAIL", reason="")

    def test_fail_record_with_reason_parses(self) -> None:
        assert _record(state="FAIL", reason="tests.failed", findings=2).outcome.findings == 2

    def test_pass_without_revision_is_refused(self) -> None:
        with pytest.raises(EvidenceError, match="revision"):
            _record(revision="")

    @pytest.mark.parametrize("document", [[], "x", None, 5])
    def test_non_object_is_refused(self, document: Any) -> None:
        with pytest.raises(EvidenceError, match="JSON object"):
            parse_evidence(document)

    def test_unknown_key_is_refused(self) -> None:
        with pytest.raises(EvidenceError, match="unknown key"):
            _record(trusted=True)

    @pytest.mark.parametrize("state", ["pass", "OK", "", 1, None])
    def test_bad_state_is_refused(self, state: Any) -> None:
        with pytest.raises(EvidenceError, match="state"):
            _record(state=state)

    @pytest.mark.parametrize("key", ["validator", "revision", "scope", "reason", "detail"])
    def test_text_fields_must_be_strings(self, key: str) -> None:
        with pytest.raises(EvidenceError):
            _record(**{key: 5})

    @pytest.mark.parametrize("key", ["examined", "findings"])
    @pytest.mark.parametrize("bad", ["1", True, 1.5, -1])
    def test_counts_must_be_non_negative_ints(self, key: str, bad: Any) -> None:
        with pytest.raises(EvidenceError):
            _record(**{key: bad})

    def test_counts_may_be_null(self) -> None:
        assert _record(examined=None, findings=None).outcome.examined is None

    @pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf")])
    def test_duration_must_be_finite(self, bad: float) -> None:
        with pytest.raises(EvidenceError, match="finite"):
            _record(duration_seconds=bad)

    def test_pass_must_not_list_items(self) -> None:
        with pytest.raises(EvidenceError, match="PASS must not list"):
            _record(items=["a.py"])

    def test_unknown_key_message_is_sanitized(self) -> None:
        with pytest.raises(EvidenceError) as caught:
            _record(**{"bad\n::error::x": 1})
        assert "\n" not in str(caught.value)

    @pytest.mark.parametrize("bad", ["fast", True, None, [1]])
    def test_duration_must_be_a_number(self, bad: Any) -> None:
        with pytest.raises(EvidenceError, match="duration"):
            _record(duration_seconds=bad)

    @pytest.mark.parametrize("bad", ["C" * 64, "c" * 63, "xyz", 5])
    def test_digest_must_be_hex64(self, bad: Any) -> None:
        with pytest.raises(EvidenceError, match="digest"):
            _record(digest=bad)

    @pytest.mark.parametrize("bad", ["a.py", [1], {"a": 1}, None])
    def test_items_must_be_a_list_of_strings(self, bad: Any) -> None:
        with pytest.raises(EvidenceError, match="items"):
            _record(items=bad)


class TestBindingProblem:
    def test_commit_tier_accepts_matching_sha(self) -> None:
        assert binding_problem(_record(), Candidate(SHA), BindingTier.COMMIT) is None

    def test_commit_tier_ignores_digest(self) -> None:
        record = _record(digest=OTHER_DIGEST)
        assert binding_problem(record, Candidate(SHA, DIGEST), BindingTier.COMMIT) is None

    @pytest.mark.parametrize("revision", [OTHER_SHA, "WORKING_TREE", "main", SHA[:7]])
    def test_other_revision_is_rejected(self, revision: str) -> None:
        record = _record(state="FAIL", reason="x.y", revision=revision)
        problem = binding_problem(record, Candidate(SHA), BindingTier.COMMIT)
        assert problem == REASON_REVISION_MISMATCH

    def test_non_pass_without_revision_is_rejected(self) -> None:
        record = _record(state="UNKNOWN", reason="x.y", revision="")
        assert binding_problem(record, Candidate(SHA), BindingTier.COMMIT) == (
            REASON_REVISION_MISMATCH
        )

    def test_build_tier_accepts_matching_sha_and_digest(self) -> None:
        record = _record(digest=DIGEST)
        assert binding_problem(record, Candidate(SHA, DIGEST), BindingTier.BUILD) is None

    def test_build_tier_rejects_other_digest(self) -> None:
        record = _record(digest=OTHER_DIGEST)
        problem = binding_problem(record, Candidate(SHA, DIGEST), BindingTier.BUILD)
        assert problem == REASON_DIGEST_MISMATCH

    def test_build_tier_rejects_missing_digest(self) -> None:
        problem = binding_problem(_record(), Candidate(SHA, DIGEST), BindingTier.BUILD)
        assert problem == REASON_DIGEST_MISSING

    def test_build_tier_rejects_when_candidate_has_no_digest(self) -> None:
        problem = binding_problem(_record(digest=DIGEST), Candidate(SHA), BindingTier.BUILD)
        assert problem == REASON_CANDIDATE_DIGEST_ABSENT

    def test_build_tier_still_checks_sha_first(self) -> None:
        record = _record(revision=OTHER_SHA, digest=DIGEST)
        problem = binding_problem(record, Candidate(SHA, DIGEST), BindingTier.BUILD)
        assert problem == REASON_REVISION_MISMATCH


class TestBindRecords:
    def test_splits_bound_from_rejected(self) -> None:
        good = _record(validator="a")
        stale = _record(validator="b", revision=OTHER_SHA)
        result = bind_records((good, stale), Candidate(SHA), frozenset())
        assert result.bound == (good,)
        assert [r.validator for r in result.rejected] == ["b"]
        assert result.rejected[0].reason == REASON_REVISION_MISMATCH

    def test_build_validators_bind_on_digest(self) -> None:
        pack = _record(validator="pack-size", digest=OTHER_DIGEST)
        result = bind_records((pack,), Candidate(SHA, DIGEST), frozenset({"pack-size"}))
        assert result.bound == ()
        assert result.rejected[0].reason == REASON_DIGEST_MISMATCH

    def test_non_build_validator_is_not_held_to_the_digest(self) -> None:
        result = bind_records((_record(validator="pytest"),), Candidate(SHA, DIGEST), frozenset())
        assert len(result.bound) == 1

    def test_empty_input_gives_empty_output(self) -> None:
        result = bind_records((), Candidate(SHA), frozenset())
        assert result.bound == () and result.rejected == ()

    def test_rejection_to_dict(self) -> None:
        stale = _record(validator="b", revision=OTHER_SHA)
        data = bind_records((stale,), Candidate(SHA), frozenset()).rejected[0].to_dict()
        assert data["source"] == "x.json"
        assert data["validator"] == "b"
        assert data["reason"] == REASON_REVISION_MISMATCH


class TestLoadDir:
    def _write(self, directory: Path, name: str, content: str | dict[str, Any]) -> None:
        text = content if isinstance(content, str) else json.dumps(content)
        (directory / name).write_text(text, encoding="utf-8")

    def test_loads_every_json_file_in_name_order(self, tmp_path: Path) -> None:
        self._write(tmp_path, "b.json", _doc(validator="b"))
        self._write(tmp_path, "a.json", _doc(validator="a"))
        self._write(tmp_path, "ignored.txt", "not json")
        records, rejected = load_evidence_dir(tmp_path)
        assert [r.outcome.validator for r in records] == ["a", "b"]
        assert rejected == ()

    def test_empty_directory_loads_nothing(self, tmp_path: Path) -> None:
        assert load_evidence_dir(tmp_path) == ((), ())

    def test_malformed_json_is_rejected_not_skipped(self, tmp_path: Path) -> None:
        self._write(tmp_path, "bad.json", "{nope")
        records, rejected = load_evidence_dir(tmp_path)
        assert records == ()
        assert rejected[0].reason == REASON_MALFORMED
        assert rejected[0].source == "bad.json"

    def test_malformed_record_keeps_its_validator_name(self, tmp_path: Path) -> None:
        self._write(tmp_path, "r.json", _doc(validator="pytest", state="bogus"))
        _, rejected = load_evidence_dir(tmp_path)
        assert rejected[0].validator == "pytest"
        assert rejected[0].reason == REASON_MALFORMED

    def test_duplicate_keys_are_rejected(self, tmp_path: Path) -> None:
        self._write(tmp_path, "d.json", '{"validator": "x", "validator": "y"}')
        _, rejected = load_evidence_dir(tmp_path)
        assert rejected[0].reason == REASON_MALFORMED

    def test_deep_nesting_is_rejected(self, tmp_path: Path) -> None:
        self._write(tmp_path, "n.json", "[" * 100000)
        _, rejected = load_evidence_dir(tmp_path)
        assert rejected[0].reason == REASON_MALFORMED

    def test_undecodable_bytes_are_unreadable(self, tmp_path: Path) -> None:
        (tmp_path / "u.json").write_bytes(b"\xff\xfe\x00")
        _, rejected = load_evidence_dir(tmp_path)
        assert rejected[0].reason == REASON_UNREADABLE

    def test_oversized_file_is_unreadable(self, tmp_path: Path) -> None:
        (tmp_path / "big.json").write_text(" " * (MAX_EVIDENCE_BYTES + 1), encoding="utf-8")
        _, rejected = load_evidence_dir(tmp_path)
        assert rejected[0].reason == REASON_UNREADABLE

    def test_symlink_is_unreadable(self, tmp_path: Path) -> None:
        target = tmp_path / "target.txt"
        target.write_text(json.dumps(_doc()), encoding="utf-8")
        (tmp_path / "link.json").symlink_to(target)
        records, rejected = load_evidence_dir(tmp_path)
        assert records == ()
        assert rejected[0].reason == REASON_UNREADABLE

    def test_directory_named_json_is_unreadable(self, tmp_path: Path) -> None:
        (tmp_path / "dir.json").mkdir()
        _, rejected = load_evidence_dir(tmp_path)
        assert rejected[0].reason == REASON_UNREADABLE

    def test_missing_directory_raises(self, tmp_path: Path) -> None:
        with pytest.raises(NotADirectoryError):
            load_evidence_dir(tmp_path / "absent")

    def test_a_file_in_place_of_the_directory_raises(self, tmp_path: Path) -> None:
        (tmp_path / "f").write_text("x", encoding="utf-8")
        with pytest.raises(NotADirectoryError):
            load_evidence_dir(tmp_path / "f")


class TestHardening:
    def test_default_tier_is_not_assumed(self) -> None:
        with pytest.raises(TypeError):
            cast("Any", bind_records)((_record(),), Candidate(SHA))

    def test_conflicting_bound_records_both_survive(self) -> None:
        ok = _record(validator="v", scope="a")
        bad = _record(validator="v", scope="b", state="FAIL", reason="x.y")
        result = bind_records((ok, bad), Candidate(SHA), frozenset())
        assert result.bound == (ok, bad)

    def test_a_rejected_record_does_not_cancel_a_bound_one(self) -> None:
        fresh = _record(validator="v")
        stale = _record(validator="v", revision=OTHER_SHA, state="FAIL", reason="x.y")
        result = bind_records((fresh, stale), Candidate(SHA), frozenset())
        assert result.bound == (fresh,)
        assert len(result.rejected) == 1

    def test_nan_in_file_is_rejected(self, tmp_path: Path) -> None:
        text = json.dumps(_doc()).replace("1.5", "NaN")
        (tmp_path / "n.json").write_text(text, encoding="utf-8")
        _, rejected = load_evidence_dir(tmp_path)
        assert rejected[0].reason == REASON_MALFORMED

    def test_many_distinct_keys_do_not_stall(self, tmp_path: Path) -> None:
        body = ",".join(f'"k{i}": 1' for i in range(50000))
        (tmp_path / "many.json").write_text("{" + body + "}", encoding="utf-8")
        _, rejected = load_evidence_dir(tmp_path)
        assert rejected[0].reason == REASON_MALFORMED

    def test_uppercase_extension_is_not_loaded(self, tmp_path: Path) -> None:
        (tmp_path / "x.JSON").write_text(json.dumps(_doc()), encoding="utf-8")
        assert load_evidence_dir(tmp_path) == ((), ())

    def test_file_name_with_control_character_is_cleaned(self, tmp_path: Path) -> None:
        (tmp_path / "a\nb.json").write_text("{nope", encoding="utf-8")
        _, rejected = load_evidence_dir(tmp_path)
        assert "\n" not in rejected[0].source

    def test_long_validator_hint_is_truncated(self, tmp_path: Path) -> None:
        name = "v" * 1000
        (tmp_path / "l.json").write_text(
            json.dumps(_doc(validator=name, state="x")), encoding="utf-8"
        )
        _, rejected = load_evidence_dir(tmp_path)
        assert len(rejected[0].validator) < 300

    def test_non_string_validator_gives_no_hint(self, tmp_path: Path) -> None:
        (tmp_path / "h.json").write_text(json.dumps(_doc(validator=5)), encoding="utf-8")
        _, rejected = load_evidence_dir(tmp_path)
        assert rejected[0].validator == ""

    def test_unparseable_text_gives_no_hint(self, tmp_path: Path) -> None:
        (tmp_path / "h.json").write_text("[1,", encoding="utf-8")
        _, rejected = load_evidence_dir(tmp_path)
        assert rejected[0].validator == ""
