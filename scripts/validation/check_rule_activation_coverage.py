#!/usr/bin/env python3
"""Static coverage ratchet for rule and skill activation measurement.

The activation evaluator (`scripts/eval/eval-rule-activation.py`) only measures
the rules and skills you hand it via `--scenarios`. Nothing enumerates the full
rule and skill inventory, so 26 of 33 rules and every skill could go unmeasured
while the suite reports green. That is the fail-open at the heart of issue
#3457: a validator that reports PASS having measured almost nothing manufactures
false confidence.

This gate closes that gap without spending API budget. It enumerates every rule
(`.claude/rules/*.md`) and skill (`.claude/skills/*/SKILL.md`), maps each to its
activation scenario (rule scenarios under `tests/evals/rule-scenarios/`, skill
scenarios under `tests/evals/skill-scenarios/`), and ratchets the set of
uncovered artifacts against a committed baseline. New uncovered drift fails the
gate; a scenario pointing at a deleted artifact fails the gate.

Exit codes (every non-zero path is a hard failure; nothing here fails open):
  0  uncovered set is within the baseline, or --update-baseline rewrote it.
  1  ratchet regression: a rule or skill is uncovered now but not allowed by
     the baseline (a new artifact with no scenario, or coverage that vanished).
  2  config or structural error (see the enumeration below).

Fail-open vectors this gate refuses to treat as clean (all raise, none skip):
  1.  `.claude/rules/` missing or holds zero `.md` files            -> exit 2
  2.  `.claude/skills/` missing or holds zero `SKILL.md` files      -> exit 2
  3.  rule/skill scenario directory missing                         -> exit 2
  4.  baseline file missing                                         -> exit 2
  5.  baseline is not valid JSON                                    -> exit 2
  6.  baseline has the wrong shape (missing keys, non-list, non-str
      entry, or a duplicate entry)                                  -> exit 2
  7.  a scenario file is not valid JSON / not an object             -> exit 2
  8.  a scenario file sets neither or both of rule_path/skill_path  -> exit 2
      (exception: a rule-directory scenario carrying skill_path plus
      reference_path is an ADR-088 progressive-disclosure reference
      scenario; it is validated for existence and positive cases, then
      excluded from the rule ratchet universe)
  9.  a scenario file's target key is the wrong kind for its dir    -> exit 2
  10. a scenario target escapes the allowed artifact directory      -> exit 2
  11. a scenario target does not exist (ORPHAN, e.g. a deleted rule)-> exit 2
  12. a scenario file has an empty scenarios list                   -> exit 2
  13. a scenario file has no positive (non-negative) case, so it
      measures no activation                                        -> exit 2

A malformed or missing input is always a failure, never clean.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

# Import baseline-visibility guards from sibling module.  The same logic lives
# in portability_common.resolve_checked_baseline, but that function also
# resolves the path and requires a default-name parameter that is redundant
# here.  Importing the two atomic predicates keeps the dependency minimal.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from portability_baseline import (  # noqa: E402
    refuse_oversized_baseline,
    refuse_symlinked_baseline,
    refuse_undiffable_baseline,
)

RULES_SUBDIR = Path(".claude") / "rules"
SKILLS_SUBDIR = Path(".claude") / "skills"
RULE_SCENARIOS_SUBDIR = Path("tests") / "evals" / "rule-scenarios"
SKILL_SCENARIOS_SUBDIR = Path("tests") / "evals" / "skill-scenarios"
DEFAULT_BASELINE_NAME = "rule_activation_coverage_baseline.json"

BASELINE_RULE_KEY = "uncovered_rules"
BASELINE_SKILL_KEY = "uncovered_skills"

NEGATIVE_GATE = "skip-rule-not-applicable"

EXIT_OK = 0
EXIT_RATCHET = 1
EXIT_CONFIG = 2


class CoverageConfigError(Exception):
    """A structural or config problem that must fail the gate as exit 2."""


# ---------------------------------------------------------------------------
# Artifact and scenario discovery
# ---------------------------------------------------------------------------


def discover_rules(repo_root: Path) -> set[str]:
    """Return the id of every rule under .claude/rules/ (the file stem)."""
    rules_dir = repo_root / RULES_SUBDIR
    if not rules_dir.is_dir():
        raise CoverageConfigError(f"rules directory not found: {rules_dir}")
    ids = {p.stem for p in rules_dir.glob("*.md") if p.is_file()}
    if not ids:
        raise CoverageConfigError(f"no rule files found under {rules_dir}")
    return ids


def discover_skills(repo_root: Path) -> set[str]:
    """Return the id of every skill under .claude/skills/ (the directory name)."""
    skills_dir = repo_root / SKILLS_SUBDIR
    if not skills_dir.is_dir():
        raise CoverageConfigError(f"skills directory not found: {skills_dir}")
    ids = {p.parent.name for p in skills_dir.glob("*/SKILL.md") if p.is_file()}
    if not ids:
        raise CoverageConfigError(f"no SKILL.md files found under {skills_dir}")
    return ids


def _read_scenario_json(path: Path) -> dict[str, object]:
    """Parse a scenario file, raising CoverageConfigError on any read/shape fault."""
    try:
        raw = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise CoverageConfigError(f"cannot read scenario file {path}: {exc}") from exc
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise CoverageConfigError(f"invalid JSON in scenario file {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise CoverageConfigError(f"scenario file must be a JSON object: {path}")
    return data


def _validate_scenarios_measure(data: dict[str, object], path: Path) -> None:
    """Require a non-empty scenarios list with at least one positive case."""
    scenarios = data.get("scenarios")
    if not isinstance(scenarios, list) or not scenarios:
        raise CoverageConfigError(
            f"scenario file has no scenarios to measure: {path}"
        )
    positives = 0
    for item in scenarios:
        if not isinstance(item, dict):
            raise CoverageConfigError(
                f"scenario entry must be an object in {path}"
            )
        prompt = item.get("input")
        if not isinstance(prompt, str) or not prompt.strip():
            raise CoverageConfigError(
                f"scenario entry has an empty input in {path}"
            )
        if item.get("expected_gate") != NEGATIVE_GATE:
            positives += 1
    if positives == 0:
        raise CoverageConfigError(
            f"scenario file has no positive case, so it measures no "
            f"activation: {path}"
        )


def _resolve_target(
    repo_root: Path, target_str: str, artifact_dir: Path, kind: str
) -> str:
    """Resolve a scenario target under its artifact dir, returning the artifact id.

    Raises CoverageConfigError on traversal escape, a missing target (orphan),
    or the wrong file shape for the kind.
    """
    resolved = (repo_root / target_str).resolve()
    allowed_root = (repo_root / artifact_dir).resolve()
    try:
        resolved.relative_to(allowed_root)
    except ValueError as exc:
        raise CoverageConfigError(
            f"{kind}_path must stay under {artifact_dir}: {target_str}"
        ) from exc
    if kind == "rule":
        if resolved.suffix != ".md":
            raise CoverageConfigError(
                f"rule_path must be a .md file: {target_str}"
            )
        artifact_id = resolved.stem
    else:
        if resolved.name != "SKILL.md":
            raise CoverageConfigError(
                f"skill_path must be a SKILL.md file: {target_str}"
            )
        artifact_id = resolved.parent.name
    if not resolved.is_file():
        raise CoverageConfigError(
            f"{kind} scenario target does not exist (orphan): {target_str}"
        )
    return artifact_id


def _is_reference_scenario(repo_root: Path, data: Mapping[str, Any], path: Path) -> bool:
    """Whether a rule-directory scenario targets a skill reference (ADR-088).

    Recognized by a reference_path beside a skill_path and no rule_path. Both
    paths must exist in the tree; a dangling reference fails closed rather
    than silently dropping the scenario from the ratchet.
    """
    reference = data.get("reference_path")
    skill = data.get("skill_path")
    rule = data.get("rule_path")
    has_reference = isinstance(reference, str) and bool(reference.strip())
    has_skill = isinstance(skill, str) and bool(skill.strip())
    has_rule = isinstance(rule, str) and bool(rule.strip())
    if not (has_reference and has_skill and not has_rule):
        return False
    for ref in (reference.strip(), skill.strip()):
        target = (repo_root / ref).resolve()
        try:
            target.relative_to(repo_root.resolve())
        except ValueError as exc:
            raise CoverageConfigError(
                f"reference scenario {path} escapes the repository: {ref}"
            ) from exc
        if not target.is_file():
            raise CoverageConfigError(
                f"reference scenario {path} points at a missing file: {ref}"
            )
    _validate_scenarios_measure(data, path)
    return True


def covered_ids(repo_root: Path, kind: str) -> set[str]:
    """Return the set of artifact ids covered by a well-formed scenario.

    `kind` is "rule" or "skill". Every scenario file in the matching directory
    must parse, declare exactly its own kind of target, resolve to an existing
    artifact, and carry at least one positive case. Any deviation raises.
    """
    if kind == "rule":
        scenario_dir = repo_root / RULE_SCENARIOS_SUBDIR
        artifact_dir = RULES_SUBDIR
        target_key = "rule_path"
        other_key = "skill_path"
    else:
        scenario_dir = repo_root / SKILL_SCENARIOS_SUBDIR
        artifact_dir = SKILLS_SUBDIR
        target_key = "skill_path"
        other_key = "rule_path"

    if not scenario_dir.is_dir():
        raise CoverageConfigError(
            f"{kind} scenario directory not found: {scenario_dir}"
        )

    scenario_paths = sorted(scenario_dir.glob("*.json"))
    if not scenario_paths:
        raise CoverageConfigError(
            f"{kind} scenario directory has no scenarios, so the gate would "
            f"pass without measuring anything: {scenario_dir}"
        )

    covered: set[str] = set()
    for path in scenario_paths:
        data = _read_scenario_json(path)
        if kind == "rule" and _is_reference_scenario(repo_root, data, path):
            # Progressive-disclosure scenarios (ADR-088) measure a skill
            # reference, not a .claude/rules artifact, so they neither cover
            # nor orphan a rule id in this ratchet.
            continue
        target = data.get(target_key)
        other = data.get(other_key)
        target_ref = target.strip() if isinstance(target, str) else ""
        has_other = isinstance(other, str) and bool(other.strip())
        if not target_ref or has_other:
            raise CoverageConfigError(
                f"{kind} scenario {path} must set {target_key} and not "
                f"{other_key}"
            )
        _validate_scenarios_measure(data, path)
        artifact_id = _resolve_target(repo_root, target_ref, artifact_dir, kind)
        covered.add(artifact_id)
    return covered


# ---------------------------------------------------------------------------
# Baseline load, diff, write
# ---------------------------------------------------------------------------


def _load_id_list(files: dict[str, object], key: str, path: Path) -> set[str]:
    """Read one uncovered-id list from the baseline, raising on any bad shape."""
    if key not in files:
        raise CoverageConfigError(f"baseline missing key {key!r}: {path}")
    value = files[key]
    if not isinstance(value, list):
        raise CoverageConfigError(f"baseline {key!r} must be a list: {path}")
    ids: set[str] = set()
    for entry in value:
        if not isinstance(entry, str) or not entry.strip():
            raise CoverageConfigError(
                f"baseline {key!r} entries must be non-empty strings: {path}"
            )
        if entry in ids:
            raise CoverageConfigError(
                f"baseline {key!r} has a duplicate entry {entry!r}: {path}"
            )
        ids.add(entry)
    return ids


def load_baseline(path: Path) -> tuple[set[str], set[str]]:
    """Load the baseline uncovered rule and skill sets, failing closed on faults."""
    if not path.is_file():
        raise CoverageConfigError(f"baseline file not found: {path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise CoverageConfigError(f"baseline is not valid JSON: {path}: {exc}") from exc
    except (OSError, UnicodeDecodeError) as exc:
        raise CoverageConfigError(f"baseline is unreadable: {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise CoverageConfigError(f"baseline must be a JSON object: {path}")
    rules = _load_id_list(data, BASELINE_RULE_KEY, path)
    skills = _load_id_list(data, BASELINE_SKILL_KEY, path)
    return rules, skills


def diff_uncovered(current: set[str], baseline: set[str]) -> tuple[set[str], set[str]]:
    """Return (new_uncovered, resolved) for one artifact kind.

    new_uncovered: uncovered now but not allowed by the baseline (a regression).
    resolved: allowed uncovered by the baseline but covered now (report only).
    """
    new_uncovered = current - baseline
    resolved = baseline - current
    return new_uncovered, resolved


def build_baseline_payload(
    uncovered_rules: set[str], uncovered_skills: set[str]
) -> dict[str, object]:
    """Build the baseline JSON payload with sorted, deterministic id lists."""
    return {
        "_comment": (
            "Ratchet of rules and skills that lack an activation scenario. "
            "Each id here is allowed to stay uncovered; the gate fails when a "
            "rule or skill NOT listed here becomes uncovered. Shrink these "
            "lists by adding scenarios; never widen them to route around the "
            "gate. This is necessary-not-sufficient: a scenario proves a rule "
            "CAN be measured, not that routing to it works."
        ),
        BASELINE_RULE_KEY: sorted(uncovered_rules),
        BASELINE_SKILL_KEY: sorted(uncovered_skills),
    }


def write_baseline(
    path: Path, uncovered_rules: set[str], uncovered_skills: set[str]
) -> None:
    """Write the baseline payload with a trailing newline, failing closed."""
    payload = build_baseline_payload(uncovered_rules, uncovered_skills)
    try:
        path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    except OSError as exc:
        raise CoverageConfigError(f"baseline is not writable: {path}: {exc}") from exc


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------


def compute_uncovered(repo_root: Path) -> tuple[set[str], set[str]]:
    """Return (uncovered_rules, uncovered_skills) for the current tree."""
    rules = discover_rules(repo_root)
    skills = discover_skills(repo_root)
    covered_rules = covered_ids(repo_root, "rule")
    covered_skills = covered_ids(repo_root, "skill")
    return rules - covered_rules, skills - covered_skills


def _format_regressions(new_rules: set[str], new_skills: set[str]) -> list[str]:
    """Build human-readable lines for uncovered artifacts that broke the ratchet."""
    lines: list[str] = []
    for rid in sorted(new_rules):
        lines.append(
            f"  rule {rid!r} is uncovered and not in the baseline. Add a "
            f"scenario at {RULE_SCENARIOS_SUBDIR}/{rid}.json."
        )
    for sid in sorted(new_skills):
        lines.append(
            f"  skill {sid!r} is uncovered and not in the baseline. Add a "
            f"scenario at {SKILL_SCENARIOS_SUBDIR}/{sid}.json."
        )
    return lines


def run(repo_root: Path, baseline_path: Path, update: bool) -> int:
    """Execute the coverage gate. Return an exit code (never fails open)."""
    # Refuse a baseline whose diff attribute is unset: a hidden baseline lets
    # a lowered count land without review seeing it (issue #4249).
    if refuse_symlinked_baseline(repo_root, baseline_path):
        return EXIT_CONFIG
    if refuse_undiffable_baseline(repo_root, baseline_path):
        return EXIT_CONFIG
    if refuse_oversized_baseline(baseline_path):
        return EXIT_CONFIG

    uncovered_rules, uncovered_skills = compute_uncovered(repo_root)

    if update:
        write_baseline(baseline_path, uncovered_rules, uncovered_skills)
        print(
            f"Baseline written: {len(uncovered_rules)} uncovered rules, "
            f"{len(uncovered_skills)} uncovered skills."
        )
        return EXIT_OK

    base_rules, base_skills = load_baseline(baseline_path)
    new_rules, resolved_rules = diff_uncovered(uncovered_rules, base_rules)
    new_skills, resolved_skills = diff_uncovered(uncovered_skills, base_skills)

    if resolved_rules or resolved_skills:
        print(
            f"Coverage improved: {len(resolved_rules)} rule(s) and "
            f"{len(resolved_skills)} skill(s) now covered but still in the "
            "baseline. Run with --update-baseline to tighten the ratchet."
        )

    if new_rules or new_skills:
        print(
            "FAIL: rule/skill activation coverage regressed. A documented "
            "artifact has no activation scenario and is not baselined."
        )
        for line in _format_regressions(new_rules, new_skills):
            print(line)
        print(
            "A scenario proves an artifact CAN be measured, not that routing "
            "to it works (necessary, not sufficient)."
        )
        return EXIT_RATCHET

    print(
        f"OK: {len(uncovered_rules)} uncovered rule(s) and "
        f"{len(uncovered_skills)} uncovered skill(s), all within the baseline."
    )
    return EXIT_OK


def _resolve_repo_root(explicit: Path | None) -> Path:
    """Resolve the repo root from --repo-root or by walking up for .claude."""
    if explicit is not None:
        return explicit.resolve()
    here = Path(__file__).resolve()
    for ancestor in here.parents:
        if (ancestor / ".claude" / "rules").is_dir():
            return ancestor
    return here.parent


def main(argv: list[str] | None = None) -> int:
    """CLI entry point. Config faults return 2, ratchet regressions return 1."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=None)
    parser.add_argument("--baseline", type=Path, default=None)
    parser.add_argument(
        "--update-baseline",
        action="store_true",
        help="Rewrite the baseline to the current uncovered set and exit 0.",
    )
    args = parser.parse_args(argv)

    repo_root = _resolve_repo_root(args.repo_root)
    if args.baseline is not None:
        baseline_path = args.baseline
    else:
        baseline_path = repo_root / "scripts" / "validation" / DEFAULT_BASELINE_NAME

    try:
        return run(repo_root, baseline_path, args.update_baseline)
    except CoverageConfigError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return EXIT_CONFIG


if __name__ == "__main__":
    sys.exit(main())
