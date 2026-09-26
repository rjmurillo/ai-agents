"""Path-shape and coverage-completeness tests for the decision-record validator (issue #5387).

These cover the gaps the first `/review` round found: a record with no targets
after the trigger fired, a changed path spelled with `./` or backslashes, a
policy source outside the repository, and defects that hid each other.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from validation_record_fixtures import (
    make_baseline_target,
    make_generated_target,
    make_record,
    make_target,
    make_vendor_target,
    mod,
    record_errors,
)

PROJECT_ROOT = Path(__file__).resolve().parents[3]


def test_activated_record_with_no_targets_fails() -> None:
    """AC1: an activated trigger with an empty record cannot clear the gate."""
    errors = record_errors(make_record(trigger={"decision": "activate"}))
    assert any("no targets" in e for e in errors)


def test_every_trigger_target_needs_a_record_target() -> None:
    """AC1: each path the trigger named must appear as a record target."""
    trigger = {
        "decision": "activate",
        "targets": [
            {"path": "scripts/validation/check_x.py"},
            {"path": "scripts/validation/other.py"},
        ],
    }
    errors = record_errors(make_record(make_target(), trigger=trigger))
    assert any("scripts/validation/other.py" in e for e in errors)
    assert not any("check_x.py" in e for e in errors)


def test_trigger_target_spelled_with_dot_slash_matches_the_record() -> None:
    """AC3: `./` and backslash spellings name the same target."""
    trigger = {"decision": "activate", "targets": [{"path": ".\\scripts\\validation\\check_x.py"}]}
    assert record_errors(make_record(make_target(), trigger=trigger)) == []


def test_dot_slash_changed_path_still_needs_a_record_target() -> None:
    """AC3: a `./` prefix does not hide a validator change from rule 8a."""
    trigger_mod = mod.load_trigger()
    record = make_record(make_target(target="scripts/validation/check_x.py"))
    errors = record_errors(
        record,
        changed_paths=("./scripts/validation/check_x.py", "./scripts/validation/other.py"),
        repo_root=PROJECT_ROOT,
        trigger_module=trigger_mod,
    )
    assert any("scripts/validation/other.py" in e for e in errors)
    assert not any("check_x.py" in e for e in errors)


def test_backslash_changed_vendor_target_is_refused() -> None:
    """AC4: a Windows spelling of a vendored path is still that path."""
    errors = record_errors(
        make_record(make_vendor_target()), changed_paths=("vendor\\lint\\rule.py",)
    )
    assert any("VENDOR or UPSTREAM" in e for e in errors)


def test_dot_slash_generated_mirror_with_canonical_change_passes() -> None:
    """AC4: normalized mirror and canonical paths reconcile."""
    errors = record_errors(
        make_record(make_generated_target()),
        changed_paths=(
            "./src/claude/skills/x/scripts/check_x.py",
            "./.claude/skills/x/scripts/check_x.py",
        ),
    )
    assert errors == []


def test_policy_source_relative_to_repo_root_passes(tmp_path: Path) -> None:
    """AC5: a policy file inside the repository satisfies the citation."""
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "policy.md").write_text("baseline policy", encoding="utf-8")
    record = make_record(make_baseline_target("docs/policy.md"))
    assert record_errors(record, repo_root=tmp_path) == []


def test_absolute_policy_source_is_refused(tmp_path: Path) -> None:
    """AC5: any file on disk is not a repository policy."""
    policy = tmp_path / "policy.md"
    policy.write_text("baseline policy", encoding="utf-8")
    errors = record_errors(make_record(make_baseline_target(str(policy))), repo_root=tmp_path)
    assert any("inside the repository" in e for e in errors)


def test_policy_source_escaping_the_repo_root_is_refused(tmp_path: Path) -> None:
    """AC5: a `..` path that leaves the repository is refused."""
    repo = tmp_path / "repo"
    repo.mkdir()
    (tmp_path / "policy.md").write_text("outside", encoding="utf-8")
    errors = record_errors(make_record(make_baseline_target("../policy.md")), repo_root=repo)
    assert any("inside the repository" in e for e in errors)


def test_target_and_coverage_defects_are_reported_together() -> None:
    """AC6: one run shows every defect, not one class at a time."""
    record = make_record(make_target(component=""), make_vendor_target())
    errors = record_errors(record, changed_paths=("vendor/lint/rule.py",))
    assert any("component" in e for e in errors)
    assert any("VENDOR or UPSTREAM" in e for e in errors)


def test_summary_counts_targets_by_category(tmp_path: Path) -> None:
    """REQ-041 Observability: the summary carries counts by category."""
    record_path = tmp_path / "record.json"
    record = make_record(make_target(), make_target(target="b.py"), make_vendor_target())
    record_path.write_text(json.dumps(record), encoding="utf-8")
    summary = mod._summary(record, [], record_path)
    assert summary["categories"] == {"LOCAL": 2, "VENDOR": 1}
