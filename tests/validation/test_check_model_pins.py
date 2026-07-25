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
import time
from datetime import date
from pathlib import Path

import pytest
import yaml

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
    _skill(
        tmp_path,
        "nested",
        "name: nested\nmetadata:\n  version: 1.0.0\n  model: claude-opus-4-6",
    )
    report = _run(tmp_path, baseline={}, manifest=[])
    assert report.scanned == 1
    assert any("'claude-opus-4-6' under 'metadata.model'" in v for v in report.violations)


def test_nested_bare_alias_fails_even_with_rationale(tmp_path: Path) -> None:
    # A rationale cannot rescue a key no harness reads, so the cost exception
    # in ADR-080 rule 3 does not apply below the top level.
    _skill(
        tmp_path,
        "nested-alias",
        "name: nested-alias\nmetadata:\n  model: haiku\n  model-rationale: cheap lookups only",
    )
    report = _run(tmp_path, baseline={}, manifest=[])
    assert any("'haiku' under 'metadata.model'" in v for v in report.violations)


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
    assert any("'claude-opus-4-6' under 'metadata.model'" in v for v in report.violations)


def test_compliant_top_level_alias_does_not_hide_a_nested_pin(tmp_path: Path) -> None:
    # Otherwise the laundering path is one line: keep the versioned id below the
    # top level and satisfy the gate with a compliant alias above it. The
    # versioned id still ships in the mirrors and still rots on retirement.
    _skill(
        tmp_path,
        "both",
        "name: both\nmodel: haiku\nmodel-rationale: cheap lookups only\n"
        "metadata:\n  model: claude-opus-4-6",
    )
    report = _run(tmp_path, baseline={}, manifest=[])
    assert any("'claude-opus-4-6' under 'metadata.model'" in v for v in report.violations)


def test_every_nested_pin_is_reported_not_just_the_first(tmp_path: Path) -> None:
    # Reporting one at a time turns a single fix into a game of whack-a-mole and
    # lets the unreported id survive the commit that "fixed" the file.
    _skill(
        tmp_path,
        "two",
        "name: two\nalpha:\n  model: claude-opus-4-6\nbeta:\n  model: claude-sonnet-4-6",
    )
    report = _run(tmp_path, baseline={}, manifest=[])
    joined = " ".join(report.violations)
    assert "'claude-opus-4-6' under 'alpha.model'" in joined
    assert "'claude-sonnet-4-6' under 'beta.model'" in joined


def test_nested_pin_is_found_outside_metadata(tmp_path: Path) -> None:
    # The three real offenders all hid under metadata, so a detector that only
    # searched that key would pass every test written from them and still miss
    # the next one.
    _skill(tmp_path, "elsewhere", "name: elsewhere\nconfig:\n  runtime:\n    model: haiku")
    report = _run(tmp_path, baseline={}, manifest=[])
    assert any("'haiku' under 'config.runtime.model'" in v for v in report.violations)


def test_nested_pin_inside_a_list_is_found(tmp_path: Path) -> None:
    _skill(
        tmp_path,
        "listed",
        "name: listed\nvariants:\n  - name: fast\n  - name: slow\n    model: claude-opus-4-6",
    )
    report = _run(tmp_path, baseline={}, manifest=[])
    assert any("'claude-opus-4-6' under 'variants[1].model'" in v for v in report.violations)


def test_cyclic_yaml_alias_does_not_crash_the_gate(tmp_path: Path) -> None:
    # A self-referential anchor is valid YAML. An unguarded walk raises
    # RecursionError, which reads as a broken gate rather than a broken file.
    _skill(tmp_path, "cyclic", "name: cyclic\nloop: &a\n  self: *a\n  model: haiku")
    report = _run(tmp_path, baseline={}, manifest=[])
    assert any("'haiku' under 'loop.model'" in v for v in report.violations)


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


def test_nested_pin_not_grandfathered_by_baseline(tmp_path: Path) -> None:
    # A nested pin must not be grandfathered even when its unit/model pair matches
    # the baseline. The nested location was never checked before, so baseline
    # should not apply - it must be a hard violation, not backlog.
    unit = ".claude/skills/legacy/SKILL.md"
    _skill(
        tmp_path,
        "legacy",
        "name: legacy\nmetadata:\n  model: haiku",
    )
    report = _run(tmp_path, baseline={unit: "haiku"}, manifest=[])
    assert any("[nested pin]" in v for v in report.violations)
    assert report.backlog == []


def test_nested_pin_under_top_level_model_mapping_is_found(tmp_path: Path) -> None:
    # A top-level `model:` that is a mapping (not a scalar) must still have its
    # subtree walked to find nested pins like `model.model`. The blanket skip
    # was broader than needed and missed this case (issue #2840).
    _skill(tmp_path, "nested-model", "name: nested-model\nmodel:\n  model: claude-opus-4-6")
    report = _run(tmp_path, baseline={}, manifest=[])
    assert report.scanned == 1
    assert any("'claude-opus-4-6' under 'model.model'" in v for v in report.violations)


def test_quoted_top_level_model_key_is_not_a_bypass(tmp_path: Path) -> None:
    # The flat frontmatter view is a column-anchored line scan, so it misses
    # every alternate YAML spelling of the same key. A harness reading YAML
    # still sees the pin, so the gate must too (adversarial review of #2840).
    _skill(tmp_path, "quoted", "name: quoted\n'model': claude-opus-4-6")
    report = _run(tmp_path, baseline={}, manifest=[])
    assert report.scanned == 1
    assert any("claude-opus-4-6" in v for v in report.violations)


def test_explicit_and_tagged_top_level_model_keys_are_not_bypasses(tmp_path: Path) -> None:
    # `? model` (explicit key) and `!!str model` (tagged key) are the other two
    # spellings PyYAML accepts and the line scan drops.
    _skill(tmp_path, "explicit", "name: explicit\n? model\n: claude-opus-4-6")
    _skill(tmp_path, "tagged", "name: tagged\n!!str model: claude-opus-4-6")
    report = _run(tmp_path, baseline={}, manifest=[])
    assert report.scanned == 2
    assert len(report.violations) == 2


def test_alias_dag_does_not_expand_exponentially(tmp_path: Path) -> None:
    # A 32-line alias graph re-walked through every path took over five seconds
    # under the earlier recursion-path guard. Visiting each container once
    # bounds it at O(nodes). Depth 20 is 2**20 paths: a few seconds for the
    # unbounded walk, instant for the bounded one. Deeper would prove the same
    # thing by hanging, which burns a CI job instead of reporting a failure.
    lines = ["n0: &n0 {model: claude-opus-4-6}"]
    lines += [f"n{i}: &n{i} {{left: *n{i - 1}, right: *n{i - 1}}}" for i in range(1, 21)]
    lines.append("root: *n20")
    typed = yaml.safe_load("\n".join(lines))
    start = time.perf_counter()
    pins = cmp._nested_pins(typed)
    assert time.perf_counter() - start < 1.0
    assert len(pins) == 1


def test_one_anchor_reached_twice_is_reported_once(tmp_path: Path) -> None:
    # Two alias paths to the same node are one anchor in the source, so one
    # line to delete. Reporting it twice would send the author looking for a
    # second edit that does not exist.
    typed = yaml.safe_load("shared: &s {model: claude-opus-4-6}\nleft: *s\nright: *s\n")
    assert len(cmp._nested_pins(typed)) == 1


def test_two_lookalike_mappings_are_reported_separately(tmp_path: Path) -> None:
    # Distinct mappings that merely carry the same value are two edits, so the
    # visited-once rule must not collapse them.
    typed = yaml.safe_load("left:\n  model: claude-opus-4-6\nright:\n  model: claude-opus-4-6\n")
    assert cmp._nested_pins(typed) == (
        ("left.model", "claude-opus-4-6"),
        ("right.model", "claude-opus-4-6"),
    )


def test_nested_pins_are_sorted_regardless_of_insertion_order(tmp_path: Path) -> None:
    # Unsorted output makes the message order depend on YAML key order, which
    # turns a re-run into a spurious diff in CI logs.
    forward = cmp._nested_pins(yaml.safe_load("a:\n  model: x\nz:\n  model: y\n"))
    reverse = cmp._nested_pins(yaml.safe_load("z:\n  model: y\na:\n  model: x\n"))
    assert forward == reverse == (("a.model", "x"), ("z.model", "y"))


def test_pin_value_cannot_forge_a_status_line(tmp_path: Path) -> None:
    # A file-controlled value reaches human-readable CI output. Unescaped, a
    # newline lets it fake a passing line (CWE-117).
    unit = cmp.Unit(
        ".claude/skills/demo/SKILL.md", "skill", None, None, (("metadata.model", "v\nOK: forged"),)
    )
    message = cmp._unit_rule_failure(unit, {}, {}, tmp_path, TODAY, "claude-sonnet-4-6")
    assert message is not None
    assert "\n" not in message
    assert "\\n" in message


def test_long_pin_value_is_truncated_in_the_message(tmp_path: Path) -> None:
    # An overlong value would otherwise bury every other violation in the run.
    unit = cmp.Unit(
        ".claude/skills/demo/SKILL.md", "skill", None, None, (("metadata.model", "v" * 5000),)
    )
    message = cmp._unit_rule_failure(unit, {}, {}, tmp_path, TODAY, "claude-sonnet-4-6")
    assert message is not None
    assert len(message) < 300
    assert "..." in message


def test_write_baseline_round_trips_a_nested_only_tree(tmp_path: Path) -> None:
    # A unit with no top-level model used to be written with an empty path.
    # Reloading must yield the same pins and preserve the frozen count.
    _skill(tmp_path, "nested-only", "name: nested-only\nmetadata:\n  model: claude-opus-4-6")
    _skill(tmp_path, "pinned", "name: pinned\nmodel: claude-opus-4-6")
    out = tmp_path / "baseline.json"
    cmp.write_baseline(cmp.scan_units(tmp_path), out)
    pins, frozen = cmp.load_baseline(out)
    assert pins == {".claude/skills/pinned/SKILL.md": "claude-opus-4-6"}
    assert frozen == len(pins)


def test_quoted_model_rationale_key_is_read_from_typed_view(tmp_path: Path) -> None:
    # The flat frontmatter view misses alternate YAML key spellings like quoted
    # keys, but the typed view sees them. A valid cost rationale must not be
    # flagged as missing when it uses a quoted key (bug fix: issue #2840).
    _skill(tmp_path, "quoted-rationale", "name: quoted-rationale\nmodel: haiku\n'model-rationale': cheap lookups only")
    report = _run(tmp_path, baseline={}, manifest=[])
    assert report.violations == []
    assert report.backlog == []
