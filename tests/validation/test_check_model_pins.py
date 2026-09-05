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


def test_model_sequence_pins_are_found(tmp_path: Path) -> None:
    _skill(
        tmp_path,
        "sequence",
        "name: sequence\nmetadata:\n  model:\n    - claude-opus-4-6\n    - claude-sonnet-4-6",
    )
    report = _run(tmp_path, baseline={}, manifest=[])
    joined = " ".join(report.violations)
    assert "'claude-opus-4-6' under 'metadata.model[0]'" in joined
    assert "'claude-sonnet-4-6' under 'metadata.model[1]'" in joined


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


def test_frontmatter_parser_exposes_nested_structure(monkeypatch: pytest.MonkeyPatch) -> None:
    # The flat view collapses a nested mapping to an empty string; the typed
    # view is what makes the nested pin visible at all.
    # syspath_prepend, not sys.path.insert: an unrestored insert leaks into
    # every later test in the process and turns an import failure elsewhere
    # into an order-dependent mystery.
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "scripts" / "validation"))
    from skill_frontmatter import parse_frontmatter

    parsed = parse_frontmatter("---\nname: x\nmetadata:\n  model: claude-opus-4-6\n---\nbody\n")
    assert parsed.frontmatter["metadata"] == ""
    assert parsed.typed["metadata"] == {"model": "claude-opus-4-6"}


def test_non_string_yaml_key_still_surfaces_its_nested_pin(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # YAML allows non-string scalar keys, so 'true:' parses to the bool True.
    # If the parser normalised keys to str or rejected the document, a pin
    # hidden under such a key would ship unseen. That is the evasion the
    # dict[object, object] annotation on FrontmatterResult.typed exists to keep
    # honest, so the walk has to reach it.
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "scripts" / "validation"))
    from skill_frontmatter import parse_frontmatter

    parsed = parse_frontmatter("---\nname: x\ntrue:\n  model: claude-opus-4-6\n---\nbody\n")
    assert True in parsed.typed
    assert cmp._nested_pins(parsed.typed) == (("True.model", "claude-opus-4-6"),)


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
    assert any("[unsupported model-bearing value]" in v for v in report.violations)
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


def test_alias_dag_does_not_expand_exponentially(monkeypatch: pytest.MonkeyPatch) -> None:
    # A 32-line alias graph re-walked through every path took over five seconds
    # under the earlier recursion-path guard. Visiting each container once
    # bounds it at O(nodes). Depth 20 is 2**20 distinct paths.
    #
    # Count the visits rather than the seconds. A wall-clock assertion measures
    # the runner as much as the algorithm, so it goes red on a loaded CI box
    # and gets marked flaky and then skipped. The visit count is the property
    # the fix actually established: bounded is ~65 calls, unbounded is 2**20,
    # so any threshold in between separates them by four orders of magnitude
    # and never depends on how busy the machine is.
    lines = ["n0: &n0 {model: claude-opus-4-6}"]
    lines += [f"n{i}: &n{i} {{left: *n{i - 1}, right: *n{i - 1}}}" for i in range(1, 21)]
    lines.append("root: *n20")
    typed = yaml.safe_load("\n".join(lines))

    original = cmp._collect_nested_pins
    calls = 0

    def counting(node: object, prefix: str, seen: set[int], out: list[tuple[str, str]]) -> None:
        nonlocal calls
        calls += 1
        # Recursion resolves _collect_nested_pins as a module global at call
        # time, so patching the attribute counts the inner calls too.
        original(node, prefix, seen, out)

    monkeypatch.setattr(cmp, "_collect_nested_pins", counting)
    pins = cmp._nested_pins(typed)
    assert calls < 1000
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


class TestDrainedRatchet:
    """The baseline reached zero (issue #5605), which made two write paths load-bearing.

    Before the drain, ``frozen_count`` was never zero, so the branch that reads
    zero as "no baseline yet" was unreachable and nothing guarded a rise.
    """

    def test_update_baseline_on_a_compliant_tree_stays_at_zero(self, tmp_path: Path) -> None:
        """A drained ratchet must not re-derive its ceiling from the tree.

        The compliant haiku pin is a pin, so the old code counted it, wrote
        frozen_count 1, and restored grandfathering for it.
        """
        _skill(tmp_path, "cheap", "name: cheap\nmodel: haiku\nmodel-rationale: cost.")
        out = tmp_path / "baseline.json"
        out.write_text(
            json.dumps({"schema_version": "1", "frozen_count": 0, "pins": {}}) + "\n",
            encoding="utf-8",
        )

        written = cmp.write_baseline(cmp.scan_units(tmp_path), out)

        pins, frozen = cmp.load_baseline(out)
        assert written == 0
        assert pins == {}
        assert frozen == 0

    def test_update_baseline_refuses_to_raise_the_frozen_count(self, tmp_path: Path) -> None:
        """A rise is refused, not written. The ratchet may only fall."""
        _skill(tmp_path, "new-debt", "name: new-debt\nmodel: claude-opus-4-6")
        out = tmp_path / "baseline.json"
        out.write_text(
            json.dumps({"schema_version": "1", "frozen_count": 0, "pins": {}}) + "\n",
            encoding="utf-8",
        )

        with pytest.raises(cmp.BaselineWouldRise):
            cmp.write_baseline(cmp.scan_units(tmp_path), out)

        pins, frozen = cmp.load_baseline(out)
        assert pins == {}
        assert frozen == 0

    def test_first_write_with_no_baseline_file_seeds_the_count(self, tmp_path: Path) -> None:
        """Keying on file existence must not break a genuine first write."""
        _skill(tmp_path, "debt", "name: debt\nmodel: claude-opus-4-6")
        out = tmp_path / "baseline.json"
        assert not out.is_file()

        cmp.write_baseline(cmp.scan_units(tmp_path), out)

        pins, frozen = cmp.load_baseline(out)
        assert pins == {".claude/skills/debt/SKILL.md": "claude-opus-4-6"}
        assert frozen == 1

    def test_a_drained_baseline_makes_a_new_pin_a_hard_violation(self, tmp_path: Path) -> None:
        """The point of zero: nothing is grandfathered, so nothing lands as backlog."""
        _agent(tmp_path, "fresh", "name: fresh\nmodel: opus")
        report = _run(tmp_path, baseline={}, manifest=[])
        assert report.backlog == []
        assert len(report.violations) == 1
        assert "[new pin]" in report.violations[0]


class TestHandAuthoredTreesAreScanned:
    """src/claude and .github/prompts are hand-authored, so a pin there ships unseen."""

    def test_src_claude_agent_pin_is_scanned(self, tmp_path: Path) -> None:
        path = tmp_path / "src" / "claude" / "rogue.md"
        _write(path, "name: rogue\nmodel: claude-opus-4-6")

        report = _run(tmp_path, baseline={}, manifest=[])

        assert any("src/claude/rogue.md" in v for v in report.violations)

    def test_github_prompt_pin_is_scanned(self, tmp_path: Path) -> None:
        path = tmp_path / ".github" / "prompts" / "rogue.prompt.md"
        _write(path, "name: rogue\nmodel: Claude Opus 4.5 (copilot)")

        report = _run(tmp_path, baseline={}, manifest=[])

        assert any("rogue.prompt.md" in v for v in report.violations)

    def test_generated_mirrors_stay_out_of_scope(self, tmp_path: Path) -> None:
        """A mirror pin is a copy of a source pin, so reporting it twice misleads."""
        _write(tmp_path / "src" / "copilot-cli" / "skills" / "m" / "SKILL.md", "model: opus")
        _write(tmp_path / "src" / "vs-code-agents" / "m.agent.md", "model: opus")

        report = _run(tmp_path, baseline={}, manifest=[])

        assert report.violations == []
        assert report.scanned == 0


def test_quoted_model_rationale_key_is_read_from_typed_view(tmp_path: Path) -> None:
    # The flat frontmatter view misses alternate YAML key spellings like quoted
    # keys, but the typed view sees them. A valid cost rationale must not be
    # flagged as missing when it uses a quoted key (bug fix: issue #2840).
    _skill(
        tmp_path,
        "quoted-rationale",
        "name: quoted-rationale\nmodel: haiku\n'model-rationale': cheap lookups only",
    )
    report = _run(tmp_path, baseline={}, manifest=[])
    assert report.violations == []
    assert report.backlog == []


class TestPreferTyped:
    """The typed-over-flat rule is shared by model and model-rationale.

    It was duplicated once per field, and the two copies had already drifted:
    model preferred the typed view while model-rationale read only the flat
    one, so a rationale written with a quoted or explicit YAML key read as
    missing. Testing the rule directly keeps a future third caller honest.
    """

    def test_typed_wins_when_it_is_a_non_blank_string(self) -> None:
        assert cmp._prefer_typed("typed", "flat") == "typed"

    def test_flat_wins_when_typed_is_absent(self) -> None:
        assert cmp._prefer_typed(None, "flat") == "flat"

    @pytest.mark.parametrize("blank", ["", "   ", "\n", "\t"])
    def test_flat_wins_when_typed_is_blank(self, blank: str) -> None:
        assert cmp._prefer_typed(blank, "flat") == "flat"

    @pytest.mark.parametrize("wrong", [123, True, ["a"], {"k": "v"}, 1.5])
    def test_flat_wins_when_typed_is_not_a_string(self, wrong: object) -> None:
        assert cmp._prefer_typed(wrong, "flat") == "flat"

    def test_returns_none_when_neither_view_has_the_key(self) -> None:
        assert cmp._prefer_typed(None, None) is None

    def test_does_not_strip_the_value_it_returns(self) -> None:
        """Blankness gates selection; it must not mutate the payload."""
        assert cmp._prefer_typed("  typed  ", "flat") == "  typed  "


class TestBlankRationaleNormalisation:
    """A whitespace-only rationale is an absent rationale.

    ``model`` already normalised blank to None. ``rationale`` kept the empty
    string, which gave the field a third state that no reader distinguishes
    from None. The rule check treats both as falsy today, so the fix is about
    the contract rather than the verdict: one less state to reason about the
    next time someone adds a branch on ``unit.rationale``.
    """

    @pytest.mark.parametrize(
        "line",
        [
            "model-rationale:",
            "model-rationale: ",
            # A quoted key the flat line scan cannot match, so only the typed
            # view sees it and the blank has to normalise on that path too.
            "'model-rationale':",
        ],
    )
    def test_blank_rationale_reads_as_absent(self, tmp_path: Path, line: str) -> None:
        _skill(tmp_path, "s", f"name: s\nmodel: haiku\n{line}\n")
        unit = cmp._classify_and_read(
            tmp_path / ".claude" / "skills" / "s" / "SKILL.md", "skill", tmp_path
        )
        assert unit is not None
        assert unit.rationale is None

    def test_real_rationale_survives_stripping(self, tmp_path: Path) -> None:
        _skill(tmp_path, "s", "name: s\nmodel: haiku\nmodel-rationale: '  cheap  '\n")
        unit = cmp._classify_and_read(
            tmp_path / ".claude" / "skills" / "s" / "SKILL.md", "skill", tmp_path
        )
        assert unit is not None
        assert unit.rationale == "cheap"


class TestDisplayBound:
    """The cap has to measure the string that gets printed.

    ``repr`` escapes, and escaping expands: one newline renders as two
    characters. Capping the raw value first bounded a string nobody sees and
    let the printed token run to roughly twice the stated limit, which is
    exactly the report-burying the cap exists to prevent.
    """

    def test_escape_expansion_cannot_exceed_the_cap(self) -> None:
        rendered = cmp._display("\n" * cmp._MAX_DISPLAY_CHARS)
        assert len(rendered) <= cmp._MAX_DISPLAY_CHARS + len("...")

    def test_padded_value_cannot_exceed_the_cap(self) -> None:
        rendered = cmp._display("x" * (cmp._MAX_DISPLAY_CHARS * 10))
        assert len(rendered) <= cmp._MAX_DISPLAY_CHARS + len("...")

    def test_short_value_is_rendered_whole_and_unmarked(self) -> None:
        assert cmp._display("haiku") == "'haiku'"

    def test_control_characters_are_still_escaped(self) -> None:
        # CWE-117: a raw newline in the report forges a status line. The cap
        # change must not reintroduce one by slicing after the escape.
        assert "\n" not in cmp._display("a\nb")
        assert "\\n" in cmp._display("a\nb")


class TestGitHubAgentsGlobCoverage:
    """Issue #4938: .github/agents/ must be under _UNIT_GLOBS so model drift is gated."""

    def test_github_agents_glob_is_present(self) -> None:
        """Positive: the glob tuple includes .github/agents/*.md."""
        patterns = [g for _, g in cmp._UNIT_GLOBS]
        assert ".github/agents/*.md" in patterns

    def test_github_agents_file_without_model_passes(self, tmp_path: Path) -> None:
        """Positive: agent file with no model: line is valid (inherit state)."""
        agents_dir = tmp_path / ".github" / "agents"
        agents_dir.mkdir(parents=True)
        (agents_dir / "clean.agent.md").write_text(
            "---\nname: clean\ndescription: no model\n---\n# Clean\n"
        )
        units = cmp.scan_units(tmp_path)
        # No model means not collected as a pin
        assert not any(u.path.endswith("clean.agent.md") for u in units)

    def test_github_agents_file_with_display_name_model_violates(self, tmp_path: Path) -> None:
        """Negative: display-name format is not a valid versioned id or alias."""
        agents_dir = tmp_path / ".github" / "agents"
        agents_dir.mkdir(parents=True)
        (agents_dir / "bad.agent.md").write_text(
            "---\nname: bad\ndescription: x\nmodel: Claude Opus 4.6 (copilot)\n---\n# Bad\n"
        )
        units = cmp.scan_units(tmp_path)
        assert any(u.path.endswith("bad.agent.md") for u in units)
        unit = next(u for u in units if u.path.endswith("bad.agent.md"))
        tier_map: dict[str, str] = {}
        msg = cmp._unit_rule_failure(unit, {}, tier_map, tmp_path, TODAY, cmp.DEFAULT_MODEL)
        assert msg is not None
        assert "neither a rolling alias nor a versioned id" in msg

    def test_github_agents_file_with_bare_alias_without_rationale_violates(
        self, tmp_path: Path
    ) -> None:
        """Edge: bare alias without model-rationale is a violation."""
        agents_dir = tmp_path / ".github" / "agents"
        agents_dir.mkdir(parents=True)
        (agents_dir / "cheap.agent.md").write_text(
            "---\nname: cheap\ndescription: x\nmodel: sonnet\n---\n# Cheap\n"
        )
        units = cmp.scan_units(tmp_path)
        unit = next(u for u in units if u.path.endswith("cheap.agent.md"))
        msg = cmp._unit_rule_failure(unit, {}, {}, tmp_path, TODAY, cmp.DEFAULT_MODEL)
        assert msg is not None
        assert "lacks a model-rationale field" in msg


class TestNoModelLinesInGitHubAgents:
    """Issue #4938: regression gate ensuring no model: lines exist in .github/agents/."""

    def test_no_model_lines_in_shipped_github_agents(self) -> None:
        """Positive: all .github/agents/ files on disk have no model: line."""
        repo_root = Path(__file__).resolve().parents[2]
        agents_dir = repo_root / ".github" / "agents"
        violations = []
        for f in sorted(agents_dir.glob("*.md")):
            for i, line in enumerate(f.read_text().splitlines(), 1):
                if line.startswith("model:"):
                    violations.append(f"{f.name}:{i}: {line}")
        assert violations == [], "model: lines found:\n" + "\n".join(violations)


# ---------------------------------------------------------------------------
# Issue #4936: subagent_model detection
# ---------------------------------------------------------------------------


class TestSubagentModelDetection:
    """Issue #4936: MODEL_BEARING_KEYS must include subagent_model."""

    def test_nested_subagent_model_pin_is_violation(self, tmp_path: Path) -> None:
        """Positive: a versioned subagent_model is caught by enforce mode."""
        _skill(
            tmp_path,
            "orchestrator",
            "metadata:\n  subagent_model: claude-opus-4-6",
        )
        report = _run(tmp_path, {}, [])
        assert report.violations, "subagent_model pin must be flagged"
        assert any(
            "subagent_model" in v for v in report.violations
        )

    def test_subagent_model_bare_alias_is_detected(self, tmp_path: Path) -> None:
        """Edge: a bare alias under subagent_model is still seen as a pin.

        Nested pins never reach the baseline/backlog path (``run_check`` calls
        ``report.fail`` unconditionally whenever ``unit.nested_pins`` is
        non-empty, before the baseline lookup that could defer it), so this
        must be a hard violation with an empty backlog, not either-or.
        """
        _skill(
            tmp_path,
            "orchestrator",
            "metadata:\n  subagent_model: opus",
        )
        report = _run(tmp_path, {}, [])
        assert report.violations, "bare alias under subagent_model must be flagged"
        assert not report.backlog, "a nested pin must never be merely grandfathered"

    def test_no_subagent_model_passes(self, tmp_path: Path) -> None:
        """Negative control: skill without subagent_model passes cleanly."""
        _skill(tmp_path, "clean", "metadata:\n  version: 1.0")
        report = _run(tmp_path, {}, [])
        assert not report.violations
        assert not report.backlog

    def test_model_bearing_keys_constant_is_authoritative(self) -> None:
        """Edge: the constant contains both known model keys."""
        assert "model" in cmp.MODEL_BEARING_KEYS
        assert "subagent_model" in cmp.MODEL_BEARING_KEYS

    def test_top_level_subagent_model_also_detected(self, tmp_path: Path) -> None:
        """Edge: subagent_model at frontmatter top level is also caught.

        Same reasoning as the bare-alias case above: a nested pin is always a
        hard violation, never backlog.
        """
        _skill(tmp_path, "flat", "subagent_model: claude-opus-4-6")
        report = _run(tmp_path, {}, [])
        assert report.violations, "top-level subagent_model must be flagged"
        assert not report.backlog

    def test_top_level_subagent_model_list_is_detected(self, tmp_path: Path) -> None:
        """Regression: a list-valued model-bearing key must not bypass detection.

        Before this guard, ``_nested_pins`` handled only the scalar-string
        shape for a model-bearing key at the frontmatter top level and fell
        through to an untyped recursive walk for anything else, including a
        list. That walk has no key context left, so each list entry reached
        ``_collect_nested_pins`` as a bare string with no enclosing
        model-bearing key to match, and the pin went unrecorded while the
        enforcing gate reported the unit clean.
        """
        _skill(
            tmp_path,
            "listed",
            'subagent_model: ["claude-opus-4-6"]',
        )
        report = _run(tmp_path, {}, [])
        assert report.violations, "list-valued subagent_model pin must be flagged"
        assert any("subagent_model[0]" in v for v in report.violations)

    @pytest.mark.parametrize(
        "frontmatter, expected_path",
        (
            ("subagent_model:\n  id: claude-opus-4-6", "subagent_model.id"),
            (
                "metadata:\n  subagent_model:\n    id: claude-opus-4-6",
                "metadata.subagent_model.id",
            ),
        ),
    )
    def test_mapping_valued_subagent_model_is_detected(
        self, tmp_path: Path, frontmatter: str, expected_path: str
    ) -> None:
        """Regression: mappings preserve their model-bearing key context."""
        _skill(tmp_path, "mapped", frontmatter)

        report = _run(tmp_path, {}, [])

        assert report.violations, "mapping-valued subagent_model pin must be flagged"
        assert any(expected_path in violation for violation in report.violations)
        assert any(
            "unsupported model-bearing key value(s)" in violation
            for violation in report.violations
        )
        assert all("nested below the top level" not in violation for violation in report.violations)

    def test_model_bearing_alias_is_detected_after_non_model_alias(
        self, tmp_path: Path
    ) -> None:
        """Regression: generic traversal order must not suppress model context."""
        _skill(
            tmp_path,
            "aliased",
            "shared: &candidate\n"
            "  id: claude-opus-4-6\n"
            "metadata:\n"
            "  ordinary: *candidate\n"
            "  subagent_model: *candidate",
        )

        report = _run(tmp_path, {}, [])

        assert any(
            "metadata.subagent_model.id" in violation
            for violation in report.violations
        )
