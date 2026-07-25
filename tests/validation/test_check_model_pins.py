"""Tests for the ADR-080 model-pin governance check (issue #2840).

Covers the ADR-080 acceptance criteria: positive (compliant pins pass),
negative (each rule violation fails), and edge (doc examples ignored, stale and
traversal manifest entries rejected, grandfathering versus new/changed pins,
warn-vs-enforce exit codes).
"""

from __future__ import annotations

import importlib.util
import json
import sys
from datetime import date
from pathlib import Path

import pytest

_MODULE_PATH = (
    Path(__file__).resolve().parents[2] / "scripts" / "validation" / "check_model_pins.py"
)
_spec = importlib.util.spec_from_file_location("check_model_pins", _MODULE_PATH)
assert _spec is not None and _spec.loader is not None
cmp = importlib.util.module_from_spec(_spec)
# Register before exec so dataclass introspection can resolve the module.
sys.modules["check_model_pins"] = cmp
_spec.loader.exec_module(cmp)

TODAY = date(2026, 7, 15)


# ---------------------------------------------------------------------------
# Tree builders
# ---------------------------------------------------------------------------


def _write(path: Path, frontmatter: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"---\n{frontmatter}\n---\nbody\n", encoding="utf-8")


def _skill(root: Path, name: str, fm: str) -> Path:
    p = root / ".claude" / "skills" / name / "SKILL.md"
    _write(p, fm)
    return p


def _agent(root: Path, name: str, fm: str) -> Path:
    p = root / ".claude" / "agents" / f"{name}.md"
    _write(p, fm)
    return p


def _command(root: Path, name: str, fm: str) -> Path:
    p = root / ".claude" / "commands" / f"{name}.md"
    _write(p, fm)
    return p


def _tiers_file(root: Path) -> Path:
    p = root / "templates" / "platforms" / "copilot-cli.yaml"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(
        "agents:\n"
        "  model_tiers:\n"
        '    opus: "claude-opus-4.6"\n'
        '    sonnet: "claude-sonnet-4.6"\n'
        '    haiku: "claude-haiku-4.5"\n',
        encoding="utf-8",
    )
    return p


def _baseline_file(root: Path, pins: dict[str, str]) -> Path:
    p = root / "baseline.json"
    p.write_text(json.dumps({"schema_version": "1", "pins": pins}), encoding="utf-8")
    return p


def _manifest_file(root: Path, entries: list[dict[str, object]]) -> Path:
    p = root / "manifest.json"
    p.write_text(json.dumps({"schema_version": "1", "pins": entries}), encoding="utf-8")
    return p


def _run(root: Path, baseline: dict[str, str], manifest: list[dict[str, object]]):
    return cmp.run_check(
        repo_root=root,
        baseline_path=_baseline_file(root, baseline),
        manifest_path=_manifest_file(root, manifest),
        tiers_path=_tiers_file(root),
        default_model="claude-sonnet-4-6",
        today=TODAY,
    )


def _keep_entry(root: Path, unit: str, model: str, **over: object) -> dict[str, object]:
    artifact = root / "evidence.json"
    artifact.write_text("{}", encoding="utf-8")
    entry: dict[str, object] = {
        "unit": unit,
        "model": model,
        "decision": "KEEP_PIN",
        "artifact": "evidence.json",
        "fixtures_sha": "abc123",
        "default_model": "claude-sonnet-4-6",
        "date": "2026-07-15",
    }
    entry.update(over)
    return entry


# ---------------------------------------------------------------------------
# Positive
# ---------------------------------------------------------------------------


def test_agent_versioned_pin_with_valid_manifest_passes(tmp_path: Path) -> None:
    unit = ".claude/agents/critic.md"
    _agent(tmp_path, "critic", "model: claude-opus-4-6")
    report = _run(
        tmp_path,
        baseline={},
        manifest=[_keep_entry(tmp_path, unit, "claude-opus-4-6")],
    )
    assert report.violations == []
    assert report.backlog == []


def test_bare_alias_with_below_default_cost_rationale_passes(tmp_path: Path) -> None:
    _skill(tmp_path, "cheap", "model: haiku\nmodel-rationale: cheap lookups only")
    report = _run(tmp_path, baseline={}, manifest=[])
    assert report.violations == []
    assert report.backlog == []


def test_no_model_line_passes(tmp_path: Path) -> None:
    _skill(tmp_path, "plain", "name: plain")
    report = _run(tmp_path, baseline={}, manifest=[])
    assert report.scanned == 0
    assert report.violations == []


# ---------------------------------------------------------------------------
# Negative
# ---------------------------------------------------------------------------


def test_versioned_skill_pin_fails(tmp_path: Path) -> None:
    _skill(tmp_path, "hard", "model: claude-opus-4-6")
    report = _run(tmp_path, baseline={}, manifest=[])
    assert any("may not pin a version" in v for v in report.violations)


def test_versioned_command_pin_fails(tmp_path: Path) -> None:
    _command(tmp_path, "deploy", "model: claude-sonnet-4-6")
    report = _run(tmp_path, baseline={}, manifest=[])
    assert any("may not pin a version" in v for v in report.violations)


def test_versioned_agent_without_manifest_fails(tmp_path: Path) -> None:
    _agent(tmp_path, "critic", "model: claude-opus-4-6")
    report = _run(tmp_path, baseline={}, manifest=[])
    assert any("no manifest evidence entry" in v for v in report.violations)


def test_manifest_wrong_decision_fails(tmp_path: Path) -> None:
    unit = ".claude/agents/critic.md"
    _agent(tmp_path, "critic", "model: claude-opus-4-6")
    report = _run(
        tmp_path,
        baseline={},
        manifest=[_keep_entry(tmp_path, unit, "claude-opus-4-6", decision="DROP_PIN")],
    )
    assert any("decision is not KEEP_PIN" in v for v in report.violations)


def test_manifest_wrong_model_fails(tmp_path: Path) -> None:
    unit = ".claude/agents/critic.md"
    _agent(tmp_path, "critic", "model: claude-opus-4-6")
    report = _run(
        tmp_path,
        baseline={},
        manifest=[_keep_entry(tmp_path, unit, "claude-opus-4-8")],
    )
    assert any("model does not match" in v for v in report.violations)


def test_manifest_missing_artifact_fails(tmp_path: Path) -> None:
    unit = ".claude/agents/critic.md"
    _agent(tmp_path, "critic", "model: claude-opus-4-6")
    entry = _keep_entry(tmp_path, unit, "claude-opus-4-6")
    del entry["artifact"]
    report = _run(tmp_path, baseline={}, manifest=[entry])
    assert any("missing artifact" in v for v in report.violations)


def test_bare_alias_without_rationale_fails(tmp_path: Path) -> None:
    _skill(tmp_path, "aliasonly", "model: opus")
    report = _run(tmp_path, baseline={}, manifest=[])
    assert any("lacks a model-rationale" in v for v in report.violations)


def test_cost_rationale_on_not_cheaper_alias_fails(tmp_path: Path) -> None:
    # opus prices above the sonnet default, so a cost rationale is invalid.
    _skill(tmp_path, "pricey", "model: opus\nmodel-rationale: I want the big one")
    report = _run(tmp_path, baseline={}, manifest=[])
    assert any("does not price below the default" in v for v in report.violations)


# ---------------------------------------------------------------------------
# Edge
# ---------------------------------------------------------------------------


def test_doc_example_files_are_ignored(tmp_path: Path) -> None:
    # A CLAUDE.md under the commands glob must be skipped as a doc example.
    p = tmp_path / ".claude" / "commands" / "CLAUDE.md"
    _write(p, "model: claude-opus-4-6")
    report = _run(tmp_path, baseline={}, manifest=[])
    assert report.scanned == 0
    assert report.violations == []


def test_stale_manifest_entry_fails(tmp_path: Path) -> None:
    unit = ".claude/agents/critic.md"
    _agent(tmp_path, "critic", "model: claude-opus-4-6")
    entry = _keep_entry(tmp_path, unit, "claude-opus-4-6", date="2025-01-01")
    report = _run(tmp_path, baseline={}, manifest=[entry])
    assert any("stale" in v for v in report.violations)


def test_manifest_default_model_mismatch_fails(tmp_path: Path) -> None:
    unit = ".claude/agents/critic.md"
    _agent(tmp_path, "critic", "model: claude-opus-4-6")
    entry = _keep_entry(tmp_path, unit, "claude-opus-4-6", default_model="claude-haiku-4-5")
    report = _run(tmp_path, baseline={}, manifest=[entry])
    assert any("different default model" in v for v in report.violations)


def test_path_traversal_artifact_rejected(tmp_path: Path) -> None:
    unit = ".claude/agents/critic.md"
    _agent(tmp_path, "critic", "model: claude-opus-4-6")
    entry = _keep_entry(tmp_path, unit, "claude-opus-4-6", artifact="../../etc/passwd")
    report = _run(tmp_path, baseline={}, manifest=[entry])
    assert any("escapes the repository" in v for v in report.violations)


def test_grandfathered_pin_is_backlog_not_violation(tmp_path: Path) -> None:
    unit = ".claude/skills/legacy/SKILL.md"
    _skill(tmp_path, "legacy", "model: claude-opus-4-6")
    report = _run(tmp_path, baseline={unit: "claude-opus-4-6"}, manifest=[])
    assert report.violations == []
    assert any("may not pin a version" in b for b in report.backlog)


def test_new_noncompliant_pin_is_hard_violation(tmp_path: Path) -> None:
    _skill(tmp_path, "fresh", "model: claude-opus-4-6")
    report = _run(tmp_path, baseline={}, manifest=[])
    assert any("[new pin]" in v for v in report.violations)


def test_changed_baselined_pin_is_hard_violation(tmp_path: Path) -> None:
    unit = ".claude/skills/legacy/SKILL.md"
    _skill(tmp_path, "legacy", "model: claude-opus-4-8")
    report = _run(tmp_path, baseline={unit: "claude-opus-4-6"}, manifest=[])
    assert any("[changed pin]" in v for v in report.violations)


def test_warn_mode_exits_zero_enforce_nonzero(monkeypatch: pytest.MonkeyPatch) -> None:
    # Isolate main()'s exit-code contract from tree scanning: a report carrying a
    # hard violation must exit 0 in warn mode and 1 in enforce mode.
    def _stub(**_: object) -> cmp.CheckReport:
        report = cmp.CheckReport(scanned=1)
        report.fail(".claude/skills/x/SKILL.md", "[new pin] versioned skill")
        return report

    monkeypatch.setattr(cmp, "run_check", _stub)
    assert cmp.main(["--mode", "warn"]) == 0
    assert cmp.main(["--mode", "enforce"]) == 1


def test_enforce_mode_clean_report_exits_zero(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cmp, "run_check", lambda **_: cmp.CheckReport(scanned=3))
    assert cmp.main(["--mode", "enforce"]) == 0


def test_alias_prices_below_default_helper(tmp_path: Path) -> None:
    tiers = cmp.load_tier_map(_tiers_file(tmp_path))
    assert cmp.alias_prices_below_default("haiku", tiers, "claude-sonnet-4-6") is True
    assert cmp.alias_prices_below_default("opus", tiers, "claude-sonnet-4-6") is False
    assert cmp.alias_prices_below_default("sonnet", tiers, "claude-sonnet-4-6") is False


# ---------------------------------------------------------------------------
# Nested pins (issue #2840): a pin below the top level is invisible to the flat
# frontmatter view, ships to customers in the mirrors, and rots on retirement.
# ---------------------------------------------------------------------------


def test_nested_versioned_skill_pin_fails(tmp_path: Path) -> None:
    _skill(tmp_path, "nested", "name: nested\nmetadata:\n  version: 1.0.0\n  model: claude-opus-4-6")
    report = _run(tmp_path, baseline={}, manifest=[])
    assert report.scanned == 1
    assert any("nested under 'metadata'" in v for v in report.violations)


def test_nested_bare_alias_fails_even_with_rationale(tmp_path: Path) -> None:
    # A rationale cannot rescue a key no harness reads, so the cost exception
    # in ADR-080 rule 3 does not apply below the top level.
    _skill(
        tmp_path,
        "nested-alias",
        "name: nested-alias\nmetadata:\n  model: haiku\n  model-rationale: cheap lookups only",
    )
    report = _run(tmp_path, baseline={}, manifest=[])
    assert any("nested under 'metadata'" in v for v in report.violations)


def test_nested_agent_pin_fails_despite_valid_manifest(tmp_path: Path) -> None:
    # Evidence is keyed to the unit, but a nested key never reaches the harness,
    # so a KEEP_PIN entry must not launder it into compliance.
    unit = ".claude/agents/critic.md"
    _agent(tmp_path, "critic", "name: critic\nmetadata:\n  model: claude-opus-4-6")
    report = _run(
        tmp_path,
        baseline={},
        manifest=[_keep_entry(tmp_path, unit, "claude-opus-4-6")],
    )
    assert any("nested under 'metadata'" in v for v in report.violations)


def test_top_level_pin_wins_over_nested(tmp_path: Path) -> None:
    # The harness reads the top-level key, so that is the pin under policy; the
    # nested value must not shadow it or the failure message would misattribute.
    _skill(
        tmp_path,
        "both",
        "name: both\nmodel: haiku\nmodel-rationale: cheap lookups only\nmetadata:\n  model: claude-opus-4-6",
    )
    report = _run(tmp_path, baseline={}, manifest=[])
    assert report.violations == []


def test_nested_non_model_keys_do_not_register_a_pin(tmp_path: Path) -> None:
    _skill(tmp_path, "quiet", "name: quiet\nmetadata:\n  version: 1.0.0\n  tier: integration")
    report = _run(tmp_path, baseline={}, manifest=[])
    assert report.scanned == 0
    assert report.violations == []


def test_frontmatter_parser_exposes_nested_structure() -> None:
    # The flat view collapses a nested mapping to an empty string; the typed
    # view is what makes the nested pin visible at all.
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts" / "validation"))
    from skill_frontmatter import parse_frontmatter

    parsed = parse_frontmatter("---\nname: x\nmetadata:\n  model: claude-opus-4-6\n---\nbody\n")
    assert parsed.frontmatter["metadata"] == ""
    assert parsed.typed["metadata"] == {"model": "claude-opus-4-6"}
