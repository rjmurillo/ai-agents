"""Tests for the external claims ledger validator (issue #5388).

The ``research`` skill runs ``claim_ledger.py`` before it writes a durable
artifact. Each test drives the validator on a real ledger, so each rule is an
assertion on output, not on prose. The six issue cases (vendor, statistic,
time-sensitive, secondary-only, internal-only, unavailable source) each have
a passing ledger and a failing variant.
"""

from __future__ import annotations

import copy
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

TESTS_SKILLS_DIR = str(Path(__file__).resolve().parents[1])
if TESTS_SKILLS_DIR not in sys.path:
    sys.path.insert(0, TESTS_SKILLS_DIR)

from claude_skills_import import import_skill_script

mod = import_skill_script(
    ".claude/skills/ai-agents-external-claims/scripts/claim_ledger.py",
    module_name="test_claim_ledger_mod",
)

PRIMARY = {
    "kind": "primary",
    "url": "https://kafka.apache.org/documentation/",
    "published": None,
    "accessed": "2026-09-25",
    "secondary_reason": None,
}


def _claim(**overrides: Any) -> dict[str, Any]:
    claim: dict[str, Any] = {
        "id": "C1",
        "claim": "Kafka consumers pause fetches when the buffer is full",
        "category": "vendor",
        "time_sensitive": False,
        "source": dict(PRIMARY),
        "confidence": "high",
        "disposition": "verified",
        "final_wording": "Kafka consumers pause fetches when the buffer is full",
        "gap": "",
    }
    claim.update(overrides)
    return claim


def _ledger(*claims: Any, decision: str = "activate") -> dict[str, Any]:
    return {
        "artifact": "analysis/queue-backpressure.md",
        "activation": {"decision": decision, "reason": "vendor and statistic claims"},
        "claims": list(claims),
    }


def _statistic() -> dict[str, Any]:
    return _claim(
        id="C2",
        claim="Over 1000 teams run the operator in production",
        category="statistic",
        source={
            "kind": "primary",
            "url": "https://api.github.com/repos/example/operator",
            "published": "2026-09-01",
            "accessed": "2026-09-25",
            "secondary_reason": None,
        },
        confidence="medium",
        disposition="narrowed",
        time_sensitive=True,
        final_wording="As of 2026-09-25 the operator repository lists 987 stars",
        gap="The source counts stars, not production teams.",
    )


def _secondary() -> dict[str, Any]:
    return _claim(
        id="C3",
        claim="Vendor X cut p99 latency by 40 percent",
        category="comparative",
        source={
            "kind": "secondary",
            "url": "https://blog.example.com/vendor-x-review",
            "published": "2026-08-10",
            "accessed": "2026-09-25",
            "secondary_reason": "Vendor X publishes no benchmark artifact.",
        },
        confidence="low",
        disposition="qualified",
        final_wording="A third-party review reports that Vendor X cut p99 latency",
        gap="No primary benchmark exists.",
    )


def _unavailable() -> dict[str, Any]:
    return _claim(
        id="C4",
        claim="The SDK supports ARM64 on every platform",
        category="api",
        source={
            "kind": "none",
            "url": None,
            "published": None,
            "accessed": None,
            "secondary_reason": None,
        },
        confidence="none",
        disposition="removed",
        final_wording="",
        gap="Browsing was unavailable, so the claim was removed.",
    )


def _errors(ledger: Any, artifact: str | None = None) -> list[str]:
    errors: list[str] = mod.validate(ledger, artifact)
    return errors


# Positive cases: one per issue category.


def test_vendor_claim_verified_passes() -> None:
    assert _errors(_ledger(_claim())) == []


def test_statistic_narrowed_passes() -> None:
    assert _errors(_ledger(_statistic())) == []


def test_secondary_only_qualified_passes() -> None:
    assert _errors(_ledger(_secondary())) == []


def test_unavailable_source_removed_passes() -> None:
    assert _errors(_ledger(_unavailable())) == []


def test_unavailable_source_qualified_passes() -> None:
    claim = _unavailable()
    claim.update(
        disposition="qualified",
        confidence="low",
        final_wording="The SDK documents ARM64 support for Linux; other platforms are unconfirmed",
    )
    assert _errors(_ledger(claim)) == []


def test_internal_only_skip_passes() -> None:
    ledger = _ledger(decision="skip")
    ledger["activation"]["reason"] = "Only repository facts from ADR-042 and tests."
    assert _errors(ledger) == []


def test_all_cases_together_pass() -> None:
    ledger = _ledger(_claim(), _statistic(), _secondary(), _unavailable())
    assert _errors(ledger) == []


# Activation rules.


def test_skip_with_claims_fails() -> None:
    assert any("skip" in e for e in _errors(_ledger(_claim(), decision="skip")))


def test_activate_without_claims_fails() -> None:
    assert any("activate" in e for e in _errors(_ledger()))


def test_unknown_decision_fails() -> None:
    assert any("decision" in e for e in _errors(_ledger(_claim(), decision="maybe")))


def test_empty_reason_fails() -> None:
    ledger = _ledger(decision="skip")
    ledger["activation"]["reason"] = "  "
    assert any("reason" in e for e in _errors(ledger))


@pytest.mark.parametrize("key", ["artifact", "activation", "claims"])
def test_missing_top_level_key_fails(key: str) -> None:
    ledger = _ledger(_claim())
    del ledger[key]
    assert any(key in e for e in _errors(ledger))


def test_ledger_not_an_object_fails() -> None:
    assert _errors([]) == ["ledger must be a JSON object"]


def test_claims_not_a_list_fails() -> None:
    ledger = _ledger(_claim())
    ledger["claims"] = {}
    assert any("claims" in e for e in _errors(ledger))


def test_claim_not_an_object_fails() -> None:
    assert any("object" in e for e in _errors(_ledger("C1")))


def test_activation_not_an_object_fails() -> None:
    ledger = _ledger(_claim())
    ledger["activation"] = "activate"
    assert any("activation" in e for e in _errors(ledger))


# Field rules.


@pytest.mark.parametrize(
    "field", ["id", "claim", "category", "confidence", "disposition", "source"]
)
def test_missing_claim_field_fails(field: str) -> None:
    claim = _claim()
    del claim[field]
    assert any(f"`{field}`" in e for e in _errors(_ledger(claim)))


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
    assert any(field in e for e in _errors(_ledger(_claim(**{field: value}))))


def test_bad_source_kind_fails() -> None:
    claim = _claim()
    claim["source"]["kind"] = "blog"
    assert any("source.kind" in e for e in _errors(_ledger(claim)))


def test_duplicate_id_fails() -> None:
    assert any("duplicate" in e for e in _errors(_ledger(_claim(), _claim())))


def test_empty_claim_text_fails() -> None:
    assert any("claim" in e for e in _errors(_ledger(_claim(claim=""))))


@pytest.mark.parametrize("value", ["25-09-2026", "2026-13-01", "yesterday", 20260925])
def test_bad_date_fails(value: object) -> None:
    claim = _claim()
    claim["source"]["accessed"] = value
    assert any("accessed" in e for e in _errors(_ledger(claim)))


@pytest.mark.parametrize("key", ["url", "accessed"])
def test_primary_source_needs_url_and_accessed(key: str) -> None:
    claim = _claim()
    claim["source"][key] = None
    assert any(key in e for e in _errors(_ledger(claim)))


def test_secondary_needs_reason() -> None:
    claim = _secondary()
    claim["source"]["secondary_reason"] = ""
    assert any("secondary_reason" in e for e in _errors(_ledger(claim)))


def test_secondary_caps_confidence() -> None:
    assert any("confidence" in e for e in _errors(_ledger(_secondary() | {"confidence": "high"})))


def test_verified_needs_primary_source() -> None:
    claim = _secondary() | {"disposition": "verified", "confidence": "medium", "gap": ""}
    assert any("verified" in e for e in _errors(_ledger(claim)))


def test_verified_needs_high_or_medium_confidence() -> None:
    assert any("verified" in e for e in _errors(_ledger(_claim(confidence="low"))))


@pytest.mark.parametrize("disposition", ["verified", "narrowed"])
def test_none_source_limits_disposition(disposition: str) -> None:
    claim = _unavailable() | {"disposition": disposition, "final_wording": "text"}
    assert any("source kind `none`" in e for e in _errors(_ledger(claim)))


def test_none_source_limits_confidence() -> None:
    assert any(
        "confidence" in e for e in _errors(_ledger(_unavailable() | {"confidence": "medium"}))
    )


def test_unverified_needs_gap() -> None:
    assert any("gap" in e for e in _errors(_ledger(_secondary() | {"gap": ""})))


def test_removed_needs_empty_wording() -> None:
    claim = _unavailable() | {"final_wording": "still here"}
    assert any("final_wording" in e for e in _errors(_ledger(claim)))


def test_kept_claim_needs_wording() -> None:
    assert any("final_wording" in e for e in _errors(_ledger(_claim(final_wording=""))))


def test_time_sensitive_needs_as_of() -> None:
    claim = _statistic() | {"final_wording": "The operator repository lists 987 stars"}
    assert any("as of" in e for e in _errors(_ledger(claim)))


def test_time_sensitive_needs_published_date() -> None:
    claim = copy.deepcopy(_statistic())
    claim["source"]["published"] = None
    assert any("published" in e for e in _errors(_ledger(claim)))


def test_time_sensitive_removed_skips_wording_rules() -> None:
    claim = _unavailable() | {"time_sensitive": True}
    assert _errors(_ledger(claim)) == []


def test_time_sensitive_none_source_needs_no_published_date() -> None:
    claim = _unavailable() | {
        "time_sensitive": True,
        "disposition": "qualified",
        "confidence": "low",
        "final_wording": "As of 2026-09-25 ARM64 support is unconfirmed",
    }
    assert _errors(_ledger(claim)) == []


# Artifact rules: the artifact carries the checked wording, not the draft.


def test_artifact_with_final_wording_passes() -> None:
    artifact = "Intro.\nKafka consumers pause fetches when the buffer is full.\n"
    assert _errors(_ledger(_claim()), artifact) == []


def test_artifact_missing_final_wording_fails() -> None:
    assert any("absent" in e for e in _errors(_ledger(_claim()), "Nothing here."))


def test_artifact_with_removed_claim_fails() -> None:
    artifact = "The SDK supports ARM64 on every platform."
    assert any("removed" in e for e in _errors(_ledger(_unavailable()), artifact))


def test_artifact_with_unqualified_draft_fails() -> None:
    claim = _statistic()
    artifact = f"{claim['final_wording']}. {claim['claim']}."
    assert any("draft" in e for e in _errors(_ledger(claim), artifact))


def test_artifact_match_ignores_whitespace_and_case() -> None:
    artifact = "KAFKA consumers pause\n  fetches when the buffer is full"
    assert _errors(_ledger(_claim()), artifact) == []


# CLI and exit codes.


def _write(tmp_path: Path, name: str, data: object) -> Path:
    path = tmp_path / name
    path.write_text(data if isinstance(data, str) else json.dumps(data), encoding="utf-8")
    return path


def test_main_pass_exit_0(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    ledger = _write(tmp_path, "ledger.json", _ledger(_claim(), _unavailable()))
    assert mod.main(["--ledger", str(ledger)]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["ok"] is True
    assert out["decision"] == "activate"
    assert out["claims"] == 2
    assert out["dispositions"] == {"removed": 1, "verified": 1}
    assert out["defects"] == []


def test_main_defects_exit_1(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    ledger = _write(tmp_path, "ledger.json", _ledger(_claim(confidence="low")))
    assert mod.main(["--ledger", str(ledger)]) == 1
    out = json.loads(capsys.readouterr().out)
    assert out["ok"] is False
    assert out["defects"]


def test_main_with_artifact(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    ledger = _write(tmp_path, "ledger.json", _ledger(_claim()))
    artifact = _write(tmp_path, "a.md", "Draft only.")
    assert mod.main(["--ledger", str(ledger), "--artifact", str(artifact)]) == 1
    assert "absent" in capsys.readouterr().out


def test_main_bad_json_exit_2(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    ledger = _write(tmp_path, "ledger.json", "{not json")
    assert mod.main(["--ledger", str(ledger)]) == 2
    assert "not valid JSON" in capsys.readouterr().err


def test_main_missing_file_exit_2(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert mod.main(["--ledger", str(tmp_path / "absent.json")]) == 2
    assert "cannot read" in capsys.readouterr().err


def test_main_missing_artifact_exit_2(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    ledger = _write(tmp_path, "ledger.json", _ledger(_claim()))
    assert mod.main(["--ledger", str(ledger), "--artifact", str(tmp_path / "x.md")]) == 2
    assert "cannot read" in capsys.readouterr().err


def test_main_bad_arguments_exit_2() -> None:
    with pytest.raises(SystemExit) as exc:
        mod.main([])
    assert exc.value.code == 2


@pytest.mark.parametrize("field", ["final_wording", "gap"])
def test_non_string_text_field_fails(field: str) -> None:
    assert any(f"`{field}`" in e for e in _errors(_ledger(_claim(**{field: None}))))


def test_source_not_an_object_fails() -> None:
    assert any("`source`" in e for e in _errors(_ledger(_claim(source="docs"))))


def test_script_runs_as_a_program(tmp_path: Path) -> None:
    ledger = _write(tmp_path, "ledger.json", _ledger(_claim()))
    result = subprocess.run(
        [sys.executable, mod.__file__, "--ledger", str(ledger)],
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )
    assert result.returncode == 0
    assert json.loads(result.stdout)["ok"] is True


def test_non_string_ids_do_not_crash() -> None:
    errors = _errors(_ledger(_claim(id=["C1"]), _claim(id=["C1"])))
    assert any("`id`" in e for e in errors)
