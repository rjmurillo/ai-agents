"""Tests for the build Phase 2b decision-record validator (issue #5387).

`validation_record.py` checks the provenance-and-authority record that
`analysis-provenance` and `validation-authority` write before `/build` Phase 3
edits a validation target. Each test drives the validator on a real record, so
each REQ-041 rule is an assertion on output, not on prose. The TASK-050
fixture table's seven rows are covered here on the record-validator side; the
trigger-activation half of each row lives in
``tests/skills/build/test_validation_trigger.py``.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from validation_record_fixtures import (
    make_baseline_target,
    make_generated_target,
    make_local_config_target,
    make_record,
    make_target,
    make_unknown_owner_target,
    make_upstream_target,
    make_vendor_target,
    mod,
    record_errors,
)

PROJECT_ROOT = Path(__file__).resolve().parents[3]
SKILLS_ROOT = PROJECT_ROOT / ".claude" / "skills"
COPILOT_SKILLS_ROOT = PROJECT_ROOT / "src" / "copilot-cli" / "skills"
_TIMEOUT_S = 60

# Positive cases: one per TASK-050 fixture-table row that expects exit 0.


def test_local_validator_change_passes() -> None:
    assert record_errors(make_record(make_target())) == []


def test_local_config_fix_passes() -> None:
    assert record_errors(make_record(make_local_config_target())) == []


def test_generated_target_with_canonical_source_matching_passes() -> None:
    assert record_errors(make_record(make_generated_target())) == []


def test_vendor_target_with_a_local_override_location_passes() -> None:
    assert record_errors(make_record(make_vendor_target())) == []


def test_upstream_target_with_escalation_passes() -> None:
    assert record_errors(make_record(make_upstream_target())) == []


def test_baseline_update_with_an_existing_policy_source_passes(tmp_path: Path) -> None:
    policy = tmp_path / "policy.md"
    policy.write_text("baseline policy", encoding="utf-8")
    record = make_record(make_baseline_target(str(policy)))
    assert record_errors(record) == []


def test_all_cases_together_pass(tmp_path: Path) -> None:
    policy = tmp_path / "policy.md"
    policy.write_text("baseline policy", encoding="utf-8")
    record = make_record(
        make_target(),
        make_local_config_target(),
        make_generated_target(),
        make_vendor_target(),
        make_upstream_target(),
        make_baseline_target(str(policy)),
    )
    assert record_errors(record) == []


# TASK-050 fixture-table rows expecting a defect (record exit 1).


def test_vendored_validator_target_at_its_own_location_fails() -> None:
    """Fixture row: vendored validator, permitted location equals the target."""
    target = make_vendor_target(authority={"permitted_change_location": "vendor/lint/rule.py"})
    assert any("VENDOR" in e or "vendor" in e for e in record_errors(make_record(target)))


def test_generated_mirror_changed_without_its_canonical_source_fails() -> None:
    """Fixture row: generated mirror changed alone."""
    record = make_record(make_generated_target())
    errors = record_errors(record, changed_paths=("src/claude/skills/x/scripts/check_x.py",))
    assert any("canonical source" in e for e in errors)


def test_unjustified_baseline_refresh_fails() -> None:
    """Fixture row: baseline-update with no justification."""
    target = make_target(authority={"diagnosis": "baseline-update"})
    assert any("baseline_justification" in e for e in record_errors(make_record(target)))


def test_unknown_owner_fails() -> None:
    """Fixture row: category UNKNOWN."""
    errors = record_errors(make_record(make_unknown_owner_target()))
    assert any("stop semantic edits" in e for e in errors)


# Top-level shape.


def test_record_not_an_object_fails() -> None:
    assert record_errors([]) == ["record must be a JSON object"]


@pytest.mark.parametrize("key", ["trigger", "targets"])
def test_missing_top_level_key_fails(key: str) -> None:
    record = make_record(make_target())
    del record[key]
    assert any(key in e for e in record_errors(record))


def test_targets_not_a_list_fails() -> None:
    record = make_record(make_target())
    record["targets"] = {}
    assert any("targets" in e for e in record_errors(record))


def test_empty_targets_list_passes() -> None:
    """A record with a real `trigger` skip decision needs no targets."""
    assert record_errors(make_record(trigger={"decision": "skip"})) == []


def test_target_not_an_object_fails() -> None:
    assert any("object" in e for e in record_errors(make_record("not-a-dict")))


@pytest.mark.parametrize("key", ["target", "component", "provenance", "authority"])
def test_missing_target_field_fails(key: str) -> None:
    target = make_target()
    del target[key]
    assert any(f"`{key}`" in e for e in record_errors(make_record(target)))


def test_empty_target_path_fails() -> None:
    assert any("target" in e for e in record_errors(make_record(make_target(target=""))))


def test_empty_component_fails() -> None:
    assert any("component" in e for e in record_errors(make_record(make_target(component=""))))


def test_provenance_not_an_object_fails() -> None:
    target = make_target()
    target["provenance"] = "LOCAL"
    assert any("provenance" in e for e in record_errors(make_record(target)))


def test_authority_not_an_object_fails() -> None:
    target = make_target()
    target["authority"] = "trust it"
    assert any("authority" in e for e in record_errors(make_record(target)))


# Provenance field rules.


def test_bad_category_fails() -> None:
    target = make_target(provenance={"category": "MYSTERY"})
    assert any("category" in e for e in record_errors(make_record(target)))


def test_empty_owner_fails() -> None:
    target = make_target(provenance={"owner": ""})
    assert any("owner" in e for e in record_errors(make_record(target)))


def test_empty_evidence_fails() -> None:
    target = make_target(provenance={"evidence": ""})
    assert any("evidence" in e for e in record_errors(make_record(target)))


# Authority field rules.


def test_bad_diagnosis_fails() -> None:
    target = make_target(authority={"diagnosis": "mystery"})
    assert any("diagnosis" in e for e in record_errors(make_record(target)))


def test_empty_contract_fails() -> None:
    target = make_target(authority={"contract": ""})
    assert any("contract" in e for e in record_errors(make_record(target)))


def test_empty_permitted_change_location_fails() -> None:
    target = make_target(authority={"permitted_change_location": ""})
    assert any("permitted_change_location" in e for e in record_errors(make_record(target)))


# Blocking defects (AC6): UNKNOWN category or unknown diagnosis.


def test_unknown_diagnosis_is_a_blocking_defect() -> None:
    target = make_target(authority={"diagnosis": "unknown"})
    errors = record_errors(make_record(target))
    assert any("stop semantic edits" in e for e in errors)


# GENERATED rules (AC4).


def test_generated_without_canonical_source_fails() -> None:
    target = make_generated_target(provenance={"canonical_source": ""})
    assert any("canonical_source" in e for e in record_errors(make_record(target)))


def test_generated_permitted_location_must_equal_canonical_source() -> None:
    target = make_generated_target(authority={"permitted_change_location": "somewhere/else.py"})
    assert any("canonical_source" in e for e in record_errors(make_record(target)))


# VENDOR / UPSTREAM rules (AC4).


def test_vendor_permitted_location_must_not_equal_target() -> None:
    target = make_vendor_target(authority={"permitted_change_location": "vendor/lint/rule.py"})
    assert any("must not equal" in e for e in record_errors(make_record(target)))


def test_upstream_permitted_location_must_not_equal_target() -> None:
    target = make_upstream_target(
        authority={"permitted_change_location": "node_modules/eslint/lib/rule.js"}
    )
    assert any("must not equal" in e for e in record_errors(make_record(target)))


def test_upstream_defect_needs_escalation() -> None:
    target = make_upstream_target(authority={"escalation": ""})
    assert any("escalation" in e for e in record_errors(make_record(target)))


def test_upstream_defect_escalation_required_even_off_upstream_category() -> None:
    """The escalation rule keys on diagnosis, independent of category."""
    target = make_target(
        provenance={"category": "VENDOR"},
        authority={"diagnosis": "upstream-defect", "escalation": ""},
    )
    assert any("escalation" in e for e in record_errors(make_record(target)))


# Baseline-update rules (AC5).


def test_baseline_update_needs_baseline_justification() -> None:
    target = make_target(authority={"diagnosis": "baseline-update"})
    assert "baseline_justification" not in target
    assert any("baseline_justification" in e for e in record_errors(make_record(target)))


def test_baseline_justification_needs_a_reason() -> None:
    target = make_baseline_target("policy.md")
    target["baseline_justification"]["reason"] = ""
    assert any("reason" in e for e in record_errors(make_record(target)))


def test_baseline_policy_source_must_exist_on_disk() -> None:
    target = make_baseline_target("does/not/exist/policy.md")
    errors = record_errors(make_record(target))
    assert any("policy_source" in e for e in errors)


def test_baseline_empty_policy_source_fails() -> None:
    target = make_baseline_target("")
    errors = record_errors(make_record(target))
    assert any("non-empty string" in e and "policy_source" in e for e in errors)


def test_baseline_added_entry_needs_justification() -> None:
    target = make_baseline_target("policy.md")
    target["baseline_justification"]["added_entries"] = [{"path": "x.py", "justification": ""}]
    errors = record_errors(make_record(target))
    assert any("justification" in e for e in errors)


def test_baseline_added_entries_must_be_a_list() -> None:
    target = make_baseline_target("policy.md")
    target["baseline_justification"]["added_entries"] = "all of them"
    errors = record_errors(make_record(target))
    assert any("added_entries" in e for e in errors)


def test_baseline_source_resolves_relative_to_repo_root(tmp_path: Path) -> None:
    policy = tmp_path / "policy.md"
    policy.write_text("policy", encoding="utf-8")
    target = make_baseline_target("policy.md")
    errors = record_errors(make_record(target), repo_root=tmp_path)
    assert errors == []


# Changed-path coverage rules (AC7/AC10, rule 8).


def test_vendor_target_that_was_itself_changed_fails() -> None:
    """Rule 8b: a VENDOR target must not appear in the changed-path list."""
    record = make_record(make_vendor_target())
    errors = record_errors(record, changed_paths=("vendor/lint/rule.py",))
    assert any("must not be a changed path" in e for e in errors)


def test_upstream_target_that_was_itself_changed_fails() -> None:
    record = make_record(make_upstream_target())
    errors = record_errors(record, changed_paths=("node_modules/eslint/lib/rule.js",))
    assert any("must not be a changed path" in e for e in errors)


def test_generated_target_changed_with_its_source_passes() -> None:
    record = make_record(make_generated_target())
    errors = record_errors(
        record,
        changed_paths=(
            "src/claude/skills/x/scripts/check_x.py",
            ".claude/skills/x/scripts/check_x.py",
        ),
    )
    assert errors == []


def test_local_target_not_in_changed_paths_is_unaffected() -> None:
    """Rules 8b/8c only apply to targets that were actually changed."""
    record = make_record(make_vendor_target(), make_generated_target())
    errors = record_errors(record, changed_paths=("README.md",))
    assert errors == []


def test_every_flagged_changed_path_needs_a_record_target(tmp_path: Path) -> None:
    """Rule 8a: a path the trigger would flag must be a record target."""
    trigger_mod = mod.load_trigger()
    record = make_record(make_target(target="scripts/validation/check_x.py"))
    errors = record_errors(
        record,
        changed_paths=("scripts/validation/check_x.py", "scripts/validation/other_check.py"),
        repo_root=PROJECT_ROOT,
        trigger_module=trigger_mod,
    )
    assert any("scripts/validation/other_check.py" in e for e in errors)


def test_a_changed_path_the_trigger_would_not_flag_needs_no_target() -> None:
    trigger_mod = mod.load_trigger()
    record = make_record(make_target())
    errors = record_errors(
        record,
        changed_paths=("scripts/validation/check_x.py", "src/app/feature.py"),
        repo_root=PROJECT_ROOT,
        trigger_module=trigger_mod,
    )
    assert errors == []


def test_rule_8a_is_skipped_when_no_trigger_module_is_supplied() -> None:
    """8b/8c still run without a trigger module; only 8a needs it."""
    record = make_record(make_target(target="scripts/validation/check_x.py"))
    errors = record_errors(
        record, changed_paths=("scripts/validation/check_x.py", "scripts/validation/other.py")
    )
    assert errors == []
