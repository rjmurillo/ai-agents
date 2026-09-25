"""Tests for the external claims ledger validator (issue #5388).

The ``research`` skill runs ``claim_ledger.py`` before it writes a durable
artifact. Each test drives the validator on a real ledger, so each rule is an
assertion on output, not on prose. The six issue cases (vendor, statistic,
time-sensitive, secondary-only, internal-only, unavailable source) each have
a passing ledger and a failing variant.
"""

from __future__ import annotations

import copy
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from claim_ledger_fixtures import (
    ledger_errors,
    make_claim,
    make_ledger,
    make_secondary,
    make_statistic,
    make_unavailable,
)

# Positive cases: one per issue category.


def test_vendor_claim_verified_passes() -> None:
    assert ledger_errors(make_ledger(make_claim())) == []


def test_statistic_narrowed_passes() -> None:
    assert ledger_errors(make_ledger(make_statistic())) == []


def test_secondary_only_qualified_passes() -> None:
    assert ledger_errors(make_ledger(make_secondary())) == []


def test_unavailable_source_removed_passes() -> None:
    assert ledger_errors(make_ledger(make_unavailable())) == []


def test_unavailable_source_qualified_passes() -> None:
    claim = make_unavailable()
    claim.update(
        disposition="qualified",
        confidence="low",
        final_wording="The SDK documents ARM64 support for Linux; other platforms are unconfirmed",
    )
    assert ledger_errors(make_ledger(claim)) == []


def test_internal_only_skip_passes() -> None:
    ledger = make_ledger(decision="skip")
    ledger["activation"]["reason"] = "Only repository facts from ADR-042 and tests."
    assert ledger_errors(ledger) == []


def test_all_cases_together_pass() -> None:
    ledger = make_ledger(make_claim(), make_statistic(), make_secondary(), make_unavailable())
    assert ledger_errors(ledger) == []


# Activation rules.


def test_skip_with_claims_fails() -> None:
    assert any("skip" in e for e in ledger_errors(make_ledger(make_claim(), decision="skip")))


def test_activate_without_claims_fails() -> None:
    assert any("activate" in e for e in ledger_errors(make_ledger()))


def test_unknown_decision_fails() -> None:
    assert any("decision" in e for e in ledger_errors(make_ledger(make_claim(), decision="maybe")))


def test_empty_reason_fails() -> None:
    ledger = make_ledger(decision="skip")
    ledger["activation"]["reason"] = "  "
    assert any("reason" in e for e in ledger_errors(ledger))


@pytest.mark.parametrize("key", ["artifact", "activation", "claims"])
def test_missing_top_level_key_fails(key: str) -> None:
    ledger = make_ledger(make_claim())
    del ledger[key]
    assert any(key in e for e in ledger_errors(ledger))


def test_ledger_not_an_object_fails() -> None:
    assert ledger_errors([]) == ["ledger must be a JSON object"]


def test_claims_not_a_list_fails() -> None:
    ledger = make_ledger(make_claim())
    ledger["claims"] = {}
    assert any("claims" in e for e in ledger_errors(ledger))


def test_claim_not_an_object_fails() -> None:
    assert any("object" in e for e in ledger_errors(make_ledger("C1")))


def test_activation_not_an_object_fails() -> None:
    ledger = make_ledger(make_claim())
    ledger["activation"] = "activate"
    assert any("activation" in e for e in ledger_errors(ledger))


# Field rules.


@pytest.mark.parametrize(
    "field", ["id", "claim", "category", "confidence", "disposition", "source"]
)
def test_missing_claim_field_fails(field: str) -> None:
    claim = make_claim()
    del claim[field]
    assert any(f"`{field}`" in e for e in ledger_errors(make_ledger(claim)))


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("category", "rumor"),
        ("confidence", "certain"),
        ("disposition", "trusted"),
        ("time_sensitive", "yes"),
    ],
)
def test_bad_enum_value_fails(field: str, value: str) -> None:
    assert any(field in e for e in ledger_errors(make_ledger(make_claim(**{field: value}))))


def test_bad_source_kind_fails() -> None:
    claim = make_claim()
    claim["source"]["kind"] = "blog"
    assert any("source.kind" in e for e in ledger_errors(make_ledger(claim)))


def test_duplicate_id_fails() -> None:
    assert any("duplicate" in e for e in ledger_errors(make_ledger(make_claim(), make_claim())))


def test_empty_claim_text_fails() -> None:
    assert any("claim" in e for e in ledger_errors(make_ledger(make_claim(claim=""))))


@pytest.mark.parametrize("value", ["25-09-2026", "2026-13-01", "yesterday", 20260925])
def test_bad_date_fails(value: object) -> None:
    claim = make_claim()
    claim["source"]["accessed"] = value
    assert any("accessed" in e for e in ledger_errors(make_ledger(claim)))


@pytest.mark.parametrize("key", ["url", "accessed"])
def test_primary_source_needs_url_and_accessed(key: str) -> None:
    claim = make_claim()
    claim["source"][key] = None
    assert any(key in e for e in ledger_errors(make_ledger(claim)))


def test_secondary_needs_reason() -> None:
    claim = make_secondary()
    claim["source"]["secondary_reason"] = ""
    assert any("secondary_reason" in e for e in ledger_errors(make_ledger(claim)))


def test_secondary_caps_confidence() -> None:
    assert any(
        "confidence" in e
        for e in ledger_errors(make_ledger(make_secondary() | {"confidence": "high"}))
    )


def test_verified_needs_primary_source() -> None:
    claim = make_secondary() | {"disposition": "verified", "confidence": "medium", "gap": ""}
    assert any("verified" in e for e in ledger_errors(make_ledger(claim)))


def test_verified_needs_high_or_medium_confidence() -> None:
    assert any("verified" in e for e in ledger_errors(make_ledger(make_claim(confidence="low"))))


@pytest.mark.parametrize("disposition", ["verified", "narrowed"])
def test_none_source_limits_disposition(disposition: str) -> None:
    claim = make_unavailable() | {"disposition": disposition, "final_wording": "text"}
    assert any("source kind `none`" in e for e in ledger_errors(make_ledger(claim)))


def test_none_source_limits_confidence() -> None:
    assert any(
        "confidence" in e
        for e in ledger_errors(make_ledger(make_unavailable() | {"confidence": "medium"}))
    )


def test_unverified_needs_gap() -> None:
    assert any("gap" in e for e in ledger_errors(make_ledger(make_secondary() | {"gap": ""})))


def test_removed_needs_empty_wording() -> None:
    claim = make_unavailable() | {"final_wording": "still here"}
    assert any("final_wording" in e for e in ledger_errors(make_ledger(claim)))


def test_kept_claim_needs_wording() -> None:
    assert any(
        "final_wording" in e for e in ledger_errors(make_ledger(make_claim(final_wording="")))
    )


def test_time_sensitive_needs_as_of() -> None:
    claim = make_statistic() | {"final_wording": "The operator repository lists 987 stars"}
    assert any("as of" in e for e in ledger_errors(make_ledger(claim)))


def test_time_sensitive_needs_published_date() -> None:
    claim = copy.deepcopy(make_statistic())
    claim["source"]["published"] = None
    assert any("published" in e for e in ledger_errors(make_ledger(claim)))


def test_time_sensitive_removed_skips_wording_rules() -> None:
    claim = make_unavailable() | {"time_sensitive": True}
    assert ledger_errors(make_ledger(claim)) == []


def test_time_sensitive_none_source_needs_no_published_date() -> None:
    claim = make_unavailable() | {
        "time_sensitive": True,
        "disposition": "qualified",
        "confidence": "low",
        "final_wording": "As of 2026-09-25 ARM64 support is unconfirmed",
    }
    assert ledger_errors(make_ledger(claim)) == []


@pytest.mark.parametrize("field", ["final_wording", "gap"])
def test_non_string_text_field_fails(field: str) -> None:
    errors = ledger_errors(make_ledger(make_claim(**{field: None})))
    assert any(f"`{field}`" in e for e in errors)


def test_source_not_an_object_fails() -> None:
    errors = ledger_errors(make_ledger(make_claim(source="docs")))
    assert any("`source`" in e for e in errors)


def test_non_string_ids_do_not_crash() -> None:
    errors = ledger_errors(make_ledger(make_claim(id=["C1"]), make_claim(id=["C1"])))
    assert any("`id`" in e for e in errors)
